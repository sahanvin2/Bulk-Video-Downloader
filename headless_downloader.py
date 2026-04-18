import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import yt_dlp


SUPPORTED_LINK_EXTENSIONS = {".csv", ".txt", ".tsv", ".list"}
DEFAULT_INPUT_FOLDER = r"C:\Users\User\Downloads\Test"
DEFAULT_OUTPUT_FOLDER = r"D:\Yobunny\Test"
DEFAULT_TOTAL_LIMIT = 200
NETWORK_RETRY_ATTEMPTS = 4
NETWORK_RETRY_BASE_DELAY_SEC = 3


def extract_url(value: str) -> str:
    if value is None:
        return ""
    match = re.search(r"https?://\S+", str(value).strip())
    if not match:
        return ""
    return match.group(0).rstrip('"\'')


def sanitize_name(value: str) -> str:
    name = str(value).replace("\n", " ").replace("\r", " ")
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.strip().strip(".")
    return name[:100] if name else "links"


def dedupe_preserve_order(items):
    seen = set()
    deduped = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def load_links_file(path: str):
    suffix = os.path.splitext(path)[1].lower()
    urls = []

    if suffix in {".txt", ".list", ".tsv"}:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                url = extract_url(line)
                if url:
                    urls.append(url)
        return dedupe_preserve_order(urls)

    with open(path, "r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        url_col = next((c for c in fieldnames if "url" in c.lower() or "link" in c.lower()), None)

        if url_col:
            for row in reader:
                url = extract_url(row.get(url_col, ""))
                if url:
                    urls.append(url)
            return dedupe_preserve_order(urls)

        handle.seek(0)
        for line in handle:
            line = line.strip()
            if not line:
                continue
            url = extract_url(line)
            if url:
                urls.append(url)

    return dedupe_preserve_order(urls)


def discover_link_files(inputs, recursive=False):
    discovered = []

    for raw in inputs:
        path = Path(raw)
        if not path.exists():
            print(f"Warning: Path not found, skipped: {path}")
            continue

        if path.is_file():
            if path.suffix.lower() in SUPPORTED_LINK_EXTENSIONS:
                discovered.append(path.resolve())
            else:
                print(f"Warning: Unsupported file extension, skipped: {path}")
            continue

        if path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            for candidate in iterator:
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_LINK_EXTENSIONS:
                    discovered.append(candidate.resolve())

    discovered = dedupe_preserve_order(discovered)
    return sorted(discovered)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Bulk video downloader for many link files (.csv/.txt/.tsv/.list)."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Input files/folders containing URL lists. If omitted, defaults to C:/Users/User/Downloads/Test.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT_FOLDER,
        help="Output root folder. Default: D:/Yobunny/Test",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=DEFAULT_TOTAL_LIMIT,
        help="Max total videos to process in this run. Default: 200",
    )
    parser.add_argument(
        "--per-file-limit",
        type=int,
        default=0,
        help="Optional max videos per links file. 0 means unlimited per file.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Search input folders recursively.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without downloading.",
    )

    args = parser.parse_args(argv[1:])

    if args.limit <= 0:
        parser.error("--limit must be greater than 0")

    if args.per_file_limit < 0:
        parser.error("--per-file-limit must be 0 or greater")

    if not args.inputs:
        args.inputs = [DEFAULT_INPUT_FOLDER]

    return args


def build_ydl_opts(out_dir: str, archive_file: str):
    quality_format = (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo[height<=720]+bestaudio/"
        "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo[height<=480]+bestaudio/"
        "best[height<=720]/best[height<=480]/best"
    )

    return {
        "format": quality_format,
        "outtmpl": os.path.join(out_dir, "%(title).150s.%(ext)s"),
        "merge_output_format": "mp4",
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 5,
        "concurrent_fragment_downloads": 10,
        "socket_timeout": 20,
        "windowsfilenames": True,
        "continuedl": True,
        "quiet": True,
        "no_warnings": True,
        "download_archive": archive_file,
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }


def is_transient_network_error(err: Exception) -> bool:
    msg = str(err).lower()
    transient_markers = (
        "failed to resolve",
        "getaddrinfo failed",
        "temporary failure in name resolution",
        "name or service not known",
        "timed out",
        "timeout",
        "connection reset",
        "connection aborted",
        "network is unreachable",
    )
    return any(marker in msg for marker in transient_markers)


def download_one(url: str, ydl_opts: dict):
    last_error = None
    for attempt in range(1, NETWORK_RETRY_ATTEMPTS + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return True, None
        except Exception as err:
            last_error = err
            if not is_transient_network_error(err) or attempt == NETWORK_RETRY_ATTEMPTS:
                break
            delay = NETWORK_RETRY_BASE_DELAY_SEC * attempt
            print(f"    transient network error, retrying in {delay}s ({attempt}/{NETWORK_RETRY_ATTEMPTS})")
            time.sleep(delay)

    return False, last_error


def main():
    args = parse_args(sys.argv)

    link_files = discover_link_files(args.inputs, recursive=args.recursive)
    if not link_files:
        print("No link files found. Supported extensions: .csv, .txt, .tsv, .list")
        print("Example: python headless_downloader.py C:/Users/User/Downloads/Test -o D:/Yobunny/Test")
        sys.exit(1)

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"Input paths: {', '.join(args.inputs)}")
    print(f"Output root directory: {output_root}")
    print(f"Total video limit this run: {args.limit}")
    print(f"Per-file limit: {'unlimited' if args.per_file_limit == 0 else args.per_file_limit}")
    print(f"Discovered link files: {len(link_files)}")

    processed_total = 0
    success_total = 0
    failed_total = 0
    skipped_duplicate_total = 0
    seen_urls_global = set()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    for file_index, links_path in enumerate(link_files, 1):
        if processed_total >= args.limit:
            break

        print("\n" + "=" * 80)
        print(f"[{file_index}/{len(link_files)}] Reading links file: {links_path}")

        urls = load_links_file(str(links_path))
        if not urls:
            print(" -> Skipped: no valid http(s) URLs found.")
            continue

        if args.per_file_limit > 0:
            urls = urls[: args.per_file_limit]

        file_stem = sanitize_name(links_path.stem)
        file_out_dir = output_root / file_stem
        file_out_dir.mkdir(parents=True, exist_ok=True)

        archive_file = str(file_out_dir / "download_archive.txt")
        failed_file = file_out_dir / "failed_urls.txt"
        failed_urls_for_file = []

        ydl_opts = build_ydl_opts(str(file_out_dir), archive_file)

        print(f" -> URLs in file (after dedupe/per-file limit): {len(urls)}")
        print(f" -> Output directory: {file_out_dir}")

        for url in urls:
            if processed_total >= args.limit:
                break

            if url in seen_urls_global:
                skipped_duplicate_total += 1
                continue
            seen_urls_global.add(url)

            processed_total += 1
            safe_url = str(url).encode("ascii", "replace").decode()
            print(f"    [{processed_total}/{args.limit}] Processing: {safe_url}")

            if args.dry_run:
                print("     -> dry-run: skipped actual download")
                success_total += 1
                continue

            ok, err = download_one(url, ydl_opts)
            if ok:
                success_total += 1
                print("     -> finished")
            else:
                failed_total += 1
                failed_urls_for_file.append(url)
                safe_err = str(err).encode("ascii", "replace").decode()
                print(f"     -> failed: {safe_err}")

        if failed_urls_for_file:
            with open(failed_file, "w", encoding="utf-8") as handle:
                for failed_url in failed_urls_for_file:
                    handle.write(f"{failed_url}\n")
            print(f" -> Failed URLs saved: {failed_file}")

    print("\n" + "-" * 80)
    print("Run complete")
    print(f"Processed: {processed_total}")
    print(f"Success:   {success_total}")
    print(f"Failed:    {failed_total}")
    print(f"Skipped duplicate URLs across files: {skipped_duplicate_total}")


if __name__ == "__main__":
    main()
