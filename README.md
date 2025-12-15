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

---

### Requirements

- Python 3.11+ (for `tomllib` alternative not needed here; we use JSON)
- Navidrome running and reachable (default `http://localhost:4533`)
- Subsonic-compatible account on Navidrome (create an admin/user)
- `pip install -r requirements.txt`

---

### Repository layout

spotify-csv-to-navidrome/
├─ README.md
├─ requirements.txt
├─ .gitignore
├─ config.json # non-secret app config
├─ .secrets.env # secrets (NOT committed)
├─ csv2pl.py # main script
└─ samples/
└─ playlist_example.csv

### Config

{
  "base_url": "http://localhost:4533/rest",
  "client_name": "csv2pl",
  "api_version": "1.16.1",

  "csv_path": "C:/path/to/playlist.csv",
  "csv_artist_col": "artist",
  "csv_title_col": "title",
  "csv_album_col": "album",

  "playlist_name": "My Spotify Sync",
  "dedupe": true,
  "upsert": true,
  "replace_contents": true
}

### .secretes.env
Please note: 
- Preferred: token auth
- If you set PASSWORD + SALT, the script computes token=md5(PASSWORD+SALT) automatically.
- Or provide the token directly (skip PASSWORD below):
- SUBSONIC_TOKEN=md5hex_of_password_plus_salt
- SUBSONIC_SALT=random16chars

SUBSONIC_USER=your_user
SUBSONIC_PASSWORD=your_password
SUBSONIC_SALT=random16chars


