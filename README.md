## csv2pl — Convert Spotify CSV snapshots into Navidrome playlists

Create/update Navidrome playlists from CSV files without duplicating audio. Uses the Subsonic API to resolve tracks and build server-side playlists you can play in any Subsonic client (Ultrasonic/DSub) and cache offline on Android. This is designed to
work with my other scripts I have made on my github profile as the structure of the csv/excel spreadsheet matters.

---

### Features

- CSV → playlist on your Navidrome server (no file copies)
- Exact match preference (artist + title), with fallback
- Idempotent “upsert” mode: replace or append playlist contents
- Config in **JSON**, secrets via **env file** (kept out of Git)
- Dedupe identical tracks before upload
- First run initializes from the latest snapshot folder; subsequent runs apply `.xlsx` diffs automatically
- Supports filtering which playlists to process via `include_playlists`

---

### Requirements

- Python 3.11+ (JSON only; no toml required)
- Navidrome running and reachable (default `http://localhost:4533`)
- Subsonic-compatible account on Navidrome (create an admin/user)
- `pip install -r requirements.txt`

---

### Repository layout

```
spotify-csv-to-navidrome/
├─ README.md
├─ requirements.txt
├─ .gitignore
├─ config.json                 # non-secret app config
├─ .secrets.env                # secrets (NOT committed)
├─ sync_playlists.py           # main script (init from CSV, then apply XLSX diffs)
└─ samples/
   └─ playlist_example.csv
```

### Notes
Notes:
- exports_root must point to a folder containing timestamped subfolders like 13-12-25_2254, each with one .csv per playlist. CSV columns: Track name, Album name, and Artist names as a single field joined by artist_1;artist_2.
- diffs_root must point to a folder with .xlsx files produced by your diff script. The sheet must have the “Added” block (columns: Added, Artist, Album) and the “Removed” block (columns: Removed, Artist, Album). If your spreadsheet duplicates headers, the script also reads Artist.1/Album.1 on the right-hand side.
- include_playlists is a case-insensitive substring filter. ["*"] means “process all playlists”. Example: ["Gym","Study"] processes only playlists whose names contain “gym” or “study”.
- csv_headers are zero-based indices for the three CSV columns.
- csv_artist_sep is the delimiter used to split multiple artists in the third CSV column; only the first artist is used for matching.
- Set "dry_run": true to print what would happen without changing anything.