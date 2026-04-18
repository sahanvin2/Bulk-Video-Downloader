# Bulk Video Downloader

A Python downloader for video links using `yt-dlp`.

This repo includes:
- `video_downloader.py`: GUI app (Tkinter) for interactive downloading
- `headless_downloader.py`: command-line bulk downloader for many link files/folders

## What Was Updated

- Added folder-based bulk input in `headless_downloader.py`
- Added default workflow paths:
  - Input folder: `C:/Users/User/Downloads/Test`
  - Output folder: `D:/Yobunny/Test`
- Added a total run limit (default `200` videos)
- Added optional per-file limit
- Added global URL deduplication across all files in one run
- Added retry logic for transient network errors
- Added failed URL logs (`failed_urls.txt`) per input file output folder

## Requirements

1. Python 3.9+
2. FFmpeg installed and available in PATH
3. Python packages:
   - `yt-dlp`

Install dependency:

```bash
pip install yt-dlp
```

## Input File Formats

Supported link files:
- `.txt`
- `.list`
- `.tsv`
- `.csv`

Rules:
- URLs must be `http://` or `https://`
- CSV files can have any column containing `url` or `link` in the header
- Duplicate URLs in a file are removed

## Quick Start (Your Requested Flow)

Put 10-20 link files in:

`C:/Users/User/Downloads/Test`

Then run:

```bash
python headless_downloader.py
```

This will:
- scan that folder for supported link files
- download up to 200 videos total
- save outputs under:

`D:/Yobunny/Test`

Each link file gets its own subfolder named after the file name.

## Common Commands

Use a custom input folder and output folder:

```bash
python headless_downloader.py "C:/Users/User/Downloads/Test" -o "D:/Yobunny/Test"
```

Set total max videos in one run:

```bash
python headless_downloader.py "C:/Users/User/Downloads/Test" -o "D:/Yobunny/Test" --limit 200
```

Set optional per-file max:

```bash
python headless_downloader.py "C:/Users/User/Downloads/Test" -o "D:/Yobunny/Test" --per-file-limit 30
```

Include subfolders recursively:

```bash
python headless_downloader.py "C:/Users/User/Downloads/Test" -o "D:/Yobunny/Test" --recursive
```

Dry run (no actual download):

```bash
python headless_downloader.py "C:/Users/User/Downloads/Test" -o "D:/Yobunny/Test" --dry-run
```

## Output Structure

Example:

```text
D:/Yobunny/Test/
  links_file_1/
    <downloaded_video_files>.mp4
    download_archive.txt
    failed_urls.txt
  links_file_2/
    <downloaded_video_files>.mp4
    download_archive.txt
```

Notes:
- `download_archive.txt` avoids redownloading the same URL in that folder
- `failed_urls.txt` is created when some URLs fail

## GitHub Push Steps

If this folder is not yet a git repository:

```bash
git init
git add .
git commit -m "Update bulk downloader and add README"
git branch -M main
git remote add origin https://github.com/sahanvin2/Bulk-Video-Downloader.git
git push -u origin main
```

If the repo is already initialized:

```bash
git add .
git commit -m "Update bulk downloader and add README"
git push
```

## Notes

- Some websites may require cookies or authentication for protected content.
- Download success depends on source availability and network stability.
- The GUI app and headless CLI can both coexist; for large batches, use `headless_downloader.py`.
