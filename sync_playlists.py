import os, re, csv, json, hashlib, glob, time
from pathlib import Path
from datetime import datetime
import pandas as pd
import requests

# ---------- config & auth ----------
with open("config.json","r",encoding="utf-8") as f:
    CFG = json.load(f)

BASE   = CFG["base_url"].rstrip("/")
API    = CFG.get("api_version","1.16.1")
CLIENT = CFG.get("client_name","csv2pl")

EXPORTS_ROOT = Path(CFG["exports_root"])
DIFFS_ROOT   = Path(CFG["diffs_root"])
INCLUDE      = CFG.get("include_playlists", ["*"])

CSV_HEADERS = CFG.get("csv_headers", {"track":0,"album":1,"artists":2})
ARTIST_SEP  = CFG.get("csv_artist_sep",";")
DEDUPE      = bool(CFG.get("dedupe",True))
PREFER_EXACT= bool(CFG.get("prefer_exact_artist_title",True))
DRY_RUN     = bool(CFG.get("dry_run",False))

U    = os.getenv("SUBSONIC_USER")
P    = os.getenv("SUBSONIC_PASSWORD")
T    = os.getenv("SUBSONIC_TOKEN")
SALT = os.getenv("SUBSONIC_SALT")

def auth_params():
    if T and SALT and U:
        return {"u":U,"t":T,"s":SALT,"v":API,"c":CLIENT,"f":"json"}
    if P and SALT and U:
        token = hashlib.md5((P+SALT).encode("utf-8")).hexdigest()
        return {"u":U,"t":token,"s":SALT,"v":API,"c":CLIENT,"f":"json"}
    if U and P:
        return {"u":U,"p":P,"v":API,"c":CLIENT,"f":"json"}
    raise SystemExit("Auth not configured (SUBSONIC_USER + PASSWORD or TOKEN).")

def _get(path, **params):
    r = requests.get(f"{BASE}/{path}", params={**auth_params(), **params}, timeout=30)
    r.raise_for_status()
    j = r.json()["subsonic-response"]
    if j.get("status")!="ok": raise RuntimeError(j)
    return j

def _post(path, **params):
    if DRY_RUN: return {"dry_run":True,"path":path,"params":params}
    r = requests.post(f"{BASE}/{path}", params={**auth_params(), **params}, timeout=60)
    r.raise_for_status()
    j = r.json()["subsonic-response"]
    if j.get("status")!="ok": raise RuntimeError(j)
    return j

# ---------- helpers: filesystem discovery ----------
TS_RE = re.compile(r"(?P<dd>\d{2})-(?P<mm>\d{2})-(?P<yy>\d{2})_(?P<hhmm>\d{4})$")

def parse_ts(name: str) -> datetime | None:
    m = TS_RE.search(name)
    if not m: return None
    dd,mm,yy,hhmm = int(m["dd"]), int(m["mm"]), int(m["yy"]), m["hhmm"]
    HH,MM = int(hhmm[:2]), int(hhmm[2:])
    # assume 20xx for yy
    year = 2000 + yy
    try:
        return datetime(year, mm, dd, HH, MM)
    except ValueError:
        return None

def latest_snapshot_folder(root: Path) -> Path:
    candidates = []
    for p in root.iterdir():
        if p.is_dir():
            ts = parse_ts(p.name)
            if ts: candidates.append((ts,p))
    if not candidates:
        raise SystemExit(f"No timestamped snapshot folders found in {root}")
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def list_csvs(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.csv"))

def include_this(name: str) -> bool:
    if INCLUDE == ["*"]: return True
    lowered = name.lower()
    return any(fn.lower() in lowered for fn in INCLUDE)

def most_recent_diff_for(playlist_name: str) -> Path | None:
    # choose latest .xlsx whose filename contains the playlist name (case-insensitive)
    matches = []
    for p in DIFFS_ROOT.glob("*.xlsx"):
        if playlist_name.lower() in p.stem.lower():
            matches.append((p.stat().st_mtime, p))
    if not matches: return None
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0][1]

# ---------- Subsonic / Navidrome ----------
def find_playlist_id_by_name(name: str) -> str | None:
    lists = _get("getPlaylists").get("playlists",{}).get("playlist",[]) or []
    for pl in lists:
        if pl.get("name")==name:
            return str(pl["id"])
    return None

def get_playlist_tracks(playlist_id: str) -> list[dict]:
    pl = _get("getPlaylist", id=playlist_id).get("playlist",{})
    return pl.get("entry",[]) or []

def create_playlist(name: str, song_ids: list[str]) -> str:
    params = {"name":name}
    for sid in song_ids:
        params.setdefault("songId", []).append(sid)
    _post("createPlaylist", **params)
    pid = find_playlist_id_by_name(name)
    if not pid: raise RuntimeError("Playlist created but ID not found")
    return pid

def add_songs(playlist_id: str, song_ids: list[str]) -> None:
    if not song_ids: return
    params = {"playlistId": playlist_id}
    for sid in song_ids:
        params.setdefault("songIdToAdd", []).append(sid)
    _post("updatePlaylist", **params)

def remove_songs_by_id(playlist_id: str, song_ids: list[str]) -> int:
    if not song_ids: return 0
    current = get_playlist_tracks(playlist_id)
    # build indices of songs to remove (Subsonic removes by index)
    to_remove_idx = []
    for idx, entry in enumerate(current):
        if str(entry.get("id")) in song_ids:
            to_remove_idx.append(idx)
    if not to_remove_idx: return 0
    params = {"playlistId": playlist_id}
    for i in to_remove_idx:
        params.setdefault("songIndexToRemove", []).append(i)
    _post("updatePlaylist", **params)
    return len(to_remove_idx)

# ---------- resolution ----------
def search_track(artist: str, title: str, album: str | None = None) -> str | None:
    q = f"{artist} {title}" + (f" {album}" if album else "")
    res = _get("search2", query=q)
    songs = res.get("searchResult2",{}).get("song",[]) or []
    if not songs: return None
    if PREFER_EXACT:
        al, tl = artist.lower(), title.lower()
        for s in songs:
            if s.get("artist","").lower()==al and s.get("title","").lower()==tl:
                return str(s["id"])
    return str(songs[0]["id"])

def resolve_many(rows: list[tuple[str,str,str|None]]) -> list[str]:
    ids=[]
    for artist,title,album in rows:
        tid = search_track(artist,title,album)
        if tid: ids.append(tid)
    if DEDUPE:
        seen=set(); out=[]
        for i in ids:
            if i not in seen:
                seen.add(i); out.append(i)
        return out
    return ids

# ---------- parse inputs ----------
def read_snapshot_csv(csv_path: Path) -> list[tuple[str,str,str|None]]:
    # columns: 0=track,1=album,2=artists "a1;a2"
    rows=[]
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)  # skip header if present
        for r in reader:
            if not r: continue
            track = (r[CSV_HEADERS["track"]]  or "").strip()
            album = (r[CSV_HEADERS["album"]]  or "").strip()
            arts  = (r[CSV_HEADERS["artists"]] or "").strip()
            artist = arts.split(ARTIST_SEP)[0].strip() if arts else ""
            if track and artist:
                rows.append((artist, track, album or None))
    return rows

def read_diff_xlsx(xlsx_path: Path) -> tuple[list[tuple[str,str,str|None]], list[tuple[str,str,str|None]]]:
    # Expect structure like screenshot:
    # Added:  A=track, B=artist, C=album
    # Removed:F=track, G=artist, H=album
    df = pd.read_excel(xlsx_path, engine="openpyxl")
    adds, rems = [], []
    # Added
    for _,row in df.iterrows():
        t = str(row.get("Added") or "").strip()
        a = str(row.get("Artist") or "").strip()
        al= str(row.get("Album") or "").strip()
        if t and a:
            adds.append((a, t, al or None))
    # Removed block might share column names; if your sheet duplicates headers, prefer the right side by suffix
    if "Removed" in df.columns:
        # Right-side “Removed/Artist/Album” columns may be duplicated; try with .get plus fallback
        for _,row in df.iterrows():
            t = str(row.get("Removed") or "").strip()
            a = str(row.get("Artist.1") or row.get("Artist") or "").strip()
            al= str(row.get("Album.1")  or row.get("Album")  or "").strip()
            if t and a:
                rems.append((a, t, al or None))
    return adds, rems

# ---------- main flows ----------
def initialize_from_latest_snapshot():
    latest = latest_snapshot_folder(EXPORTS_ROOT)
    for csv_path in list_csvs(latest):
        name = csv_path.stem
        if not include_this(name): continue
        if find_playlist_id_by_name(name):
            continue  # already exists; leave for incremental updates
        rows = read_snapshot_csv(csv_path)
        ids  = resolve_many(rows)
        if not ids:
            print(f"[init] {name}: no resolvable tracks, skipping")
            continue
        if DRY_RUN:
            print(f"[init] would create '{name}' with {len(ids)} tracks")
        else:
            pid = create_playlist(name, ids)
            print(f"[init] created '{name}' ({len(ids)} tracks) id={pid}")

def apply_latest_diff_updates():
    # For each existing playlist (optionally filtered), apply most recent diff if available
    pls = _get("getPlaylists").get("playlists",{}).get("playlist",[]) or []
    for pl in pls:
        name = pl.get("name")
        if not include_this(name): continue
        pid = str(pl["id"])
        diff_path = most_recent_diff_for(name)
        if not diff_path:
            continue
        adds,rems = read_diff_xlsx(diff_path)
        add_ids = resolve_many(adds)
        rem_ids = resolve_many(rems)
        # remove first, then add
        removed = remove_songs_by_id(pid, rem_ids)
        if add_ids:
            add_songs(pid, add_ids)
        print(f"[diff] {name}: -{removed} +{len(add_ids)} (file: {diff_path.name})")

def main():
    initialize_from_latest_snapshot()
    apply_latest_diff_updates()

if __name__=="__main__":
    main()
