import os, csv, hashlib, requests, tomllib
from urllib.parse import urlencode

# --- load config ---
with open("config.toml", "rb") as f:
    CFG = tomllib.load(f)

BASE = CFG["base_url"].rstrip("/")  # e.g., http://localhost:4533/rest
API  = CFG.get("api_version", "1.16.1")
CLIENT = CFG.get("client_name", "csv2pl")

CSV_PATH = CFG["csv_path"]
COL_ART  = CFG.get("csv_artist_col", "artist")
COL_TITLE= CFG.get("csv_title_col", "title")
COL_ALBUM= CFG.get("csv_album_col", "album") or None

PL_NAME  = CFG["playlist_name"]
DEDUPE   = bool(CFG.get("dedupe", True))
UPSERT   = bool(CFG.get("upsert", True))
REPLACE  = bool(CFG.get("replace_contents", True))

# --- auth params (Subsonic) ---
U = os.getenv("SUBSONIC_USER")
P = os.getenv("SUBSONIC_PASSWORD")
T = os.getenv("SUBSONIC_TOKEN")
SALT = os.getenv("SUBSONIC_SALT")

def auth_params():
    if T and SALT and U:
        return {"u": U, "t": T, "s": SALT, "v": API, "c": CLIENT, "f": "json"}
    if P and SALT and U:
        token = hashlib.md5((P + SALT).encode("utf-8")).hexdigest()
        return {"u": U, "t": token, "s": SALT, "v": API, "c": CLIENT, "f": "json"}
    if U and P:
        return {"u": U, "p": P, "v": API, "c": CLIENT, "f": "json"}
    raise SystemExit("Auth not configured. Set SUBSONIC_USER and either SUBSONIC_PASSWORD (+ optional SUBSONIC_SALT) or SUBSONIC_TOKEN+SUBSONIC_SALT.")

def _get(path, **params):
    r = requests.get(f"{BASE}/{path}", params={**auth_params(), **params}, timeout=30)
    r.raise_for_status()
    j = r.json()["subsonic-response"]
    if j.get("status") != "ok":
        raise RuntimeError(j)
    return j

def _post(path, **params):
    r = requests.post(f"{BASE}/{path}", params={**auth_params(), **params}, timeout=60)
    r.raise_for_status()
    j = r.json()["subsonic-response"]
    if j.get("status") != "ok":
        raise RuntimeError(j)
    return j

def search_track(artist: str, title: str, album: str | None = None) -> str | None:
    q = f"{artist} {title}" + (f" {album}" if album else "")
    res = _get("search2", query=q)
    songs = res.get("searchResult2", {}).get("song", []) or []
    if not songs:
        return None
    # prefer exact artist+title
    al = artist.lower()
    tl = title.lower()
    for s in songs:
        if s.get("artist","").lower() == al and s.get("title","").lower() == tl:
            return s["id"]
    return songs[0]["id"]

def read_csv_ids(path: str) -> list[str]:
    ids = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            artist = row.get(COL_ART, "") or ""
            title  = row.get(COL_TITLE, "") or ""
            album  = row.get(COL_ALBUM) if COL_ALBUM else None
            if not artist or not title:
                continue
            tid = search_track(artist, title, album)
            if tid:
                ids.append(tid)
    if DEDUPE:
        seen, deduped = set(), []
        for i in ids:
            if i not in seen:
                seen.add(i)
                deduped.append(i)
        return deduped
    return ids

def find_playlist_id_by_name(name: str) -> str | None:
    res = _get("getPlaylists")
    lists = res.get("playlists", {}).get("playlist", []) or []
    for pl in lists:
        if pl.get("name") == name:
            return str(pl["id"])
    return None

def create_playlist(name: str, song_ids: list[str]) -> str:
    params = {"name": name}
    for sid in song_ids:
        params.setdefault("songId", []).append(sid)
    res = _post("createPlaylist", **params)
    # Subsonic doesn't always return the ID here; refetch
    pid = find_playlist_id_by_name(name)
    if not pid:
        raise RuntimeError("Created but could not retrieve playlist ID")
    return pid

def update_playlist(playlist_id: str, song_ids: list[str], replace: bool = True) -> None:
    params = {"playlistId": playlist_id}
    if replace:
        # clear by sending no songId and specifying to replace via 'songIndexToRemove' for all existing
        # simpler: delete+recreate
        _post("deletePlaylist", playlistId=playlist_id)
        create_playlist(PL_NAME, song_ids)
        return
    for sid in song_ids:
        params.setdefault("songIdToAdd", []).append(sid)
    _post("updatePlaylist", **params)

def main():
    ids = read_csv_ids(CSV_PATH)
    if not ids:
        raise SystemExit("No tracks resolved from CSV.")
    pid = find_playlist_id_by_name(PL_NAME)
    if UPSERT and pid:
        update_playlist(pid, ids, replace=REPLACE)
        print(f"Updated playlist '{PL_NAME}' with {len(ids)} tracks.")
    else:
        pid = create_playlist(PL_NAME, ids)
        print(f"Created playlist '{PL_NAME}' with {len(ids)} tracks. ID={pid}")

if __name__ == "__main__":
    main()
