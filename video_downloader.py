import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import csv
import threading
import yt_dlp
import os
import time
import re
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────
#  BANDWIDTH LIMITER (Disabled per user request)
# ─────────────────────────────────────────────
MAX_RATE_BYTES_PER_SEC = None   # Unlimited speed

# Quality preference order — 720p first, 480p fallback, never above 720p
QUALITY_FORMAT = (
    "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
    "bestvideo[height<=720]+bestaudio/"
    "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/"
    "bestvideo[height<=480]+bestaudio/"
    "best[height<=720]/best[height<=480]/best"
)

DEFAULT_DOWNLOAD_SELECTION = "200"
MAX_DOWNLOADS_PER_FILE = 200
NETWORK_RETRY_ATTEMPTS = 4
NETWORK_RETRY_BASE_DELAY_SEC = 3
INTER_ITEM_DELAY_SEC = 0


def sanitize_filename(name: str) -> str:
    """Remove characters that are illegal in filenames."""
    name = str(name).replace("\n", " ").replace("\r", " ")
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.strip().strip(".")
    return name[:150] if name else "video"


class DownloaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HLS Video Downloader Studio")
        self.geometry("900x680")
        self.configure(bg="#0d0d0f")
        self.resizable(True, True)

        self._stop_flag = False
        self._paused = False
        self._thread = None
        self._urls = []          # list of (title, url)
        self._output_dir = os.path.expanduser("~/Downloads/vkvideos")
        self._links_file = ""
        self._downloaded = 0
        self._failed = 0
        self._total = 0
        self._start_time = None
        self._failed_urls = []
        self._archive_file = ""
        self._failed_urls_file = ""

        self._build_ui()

    # ─────────────── UI BUILD ───────────────
    def _build_ui(self):
        BG      = "#0d0d0f"
        PANEL   = "#16161a"
        ACCENT  = "#00e5ff"
        ACCENT2 = "#7c3aed"
        TEXT    = "#e8e8f0"
        MUTED   = "#6b7280"
        DANGER  = "#ef4444"
        SUCCESS = "#22c55e"
        WARNING = "#f59e0b"

        self._colors = dict(
            BG=BG, PANEL=PANEL, ACCENT=ACCENT, ACCENT2=ACCENT2,
            TEXT=TEXT, MUTED=MUTED, DANGER=DANGER, SUCCESS=SUCCESS, WARNING=WARNING
        )

        # ── Header ──
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=24, pady=(20, 0))

        tk.Label(hdr, text="HLS VIDEO DOWNLOADER",
                 font=("Courier New", 15, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left")

        self._clock_var = tk.StringVar(value="00:00:00")
        tk.Label(hdr, textvariable=self._clock_var,
                 font=("Courier New", 13), fg=MUTED, bg=BG).pack(side="right")

        tk.Frame(self, bg=ACCENT2, height=1).pack(fill="x", padx=24, pady=8)

        # ── Stats Row ──
        stats = tk.Frame(self, bg=BG)
        stats.pack(fill="x", padx=24, pady=(0, 10))

        self._stat_vars = {}
        stat_items = [
            ("TOTAL",      "total",      TEXT),
            ("DONE",       "done",       SUCCESS),
            ("FAILED",     "failed",     DANGER),
            ("SPEED",      "speed",      ACCENT),
            ("ELAPSED",    "elapsed",    WARNING),
        ]
        for label, key, color in stat_items:
            box = tk.Frame(stats, bg=PANEL, padx=14, pady=10)
            box.pack(side="left", padx=(0, 8))
            tk.Label(box, text=label, font=("Courier New", 8),
                     fg=MUTED, bg=PANEL).pack()
            var = tk.StringVar(value="—")
            self._stat_vars[key] = var
            tk.Label(box, textvariable=var, font=("Courier New", 16, "bold"),
                     fg=color, bg=PANEL).pack()

        # ── Controls ──
        ctrl = tk.Frame(self, bg=BG)
        ctrl.pack(fill="x", padx=24, pady=(0, 10))

        btn_style = dict(font=("Courier New", 10, "bold"), relief="flat",
                         cursor="hand2", padx=14, pady=7, bd=0)

        self._btn_csv = tk.Button(ctrl, text="LINK FILE",
                                  bg=ACCENT2, fg="white",
                                  command=self._load_links_file, **btn_style)
        self._btn_csv.pack(side="left", padx=(0, 6))

        self._links_var = tk.StringVar(value="No file selected")
        tk.Label(ctrl, textvariable=self._links_var,
             font=("Courier New", 9), fg=MUTED, bg=BG,
             wraplength=200, anchor="w", width=24).pack(side="left", padx=(0, 10))

        self._btn_dir = tk.Button(ctrl, text="OUTPUT FOLDER",
                                  bg=PANEL, fg=TEXT,
                                  command=self._choose_dir, **btn_style)
        self._btn_dir.pack(side="left", padx=(0, 6))

        self._dir_var = tk.StringVar(value=self._output_dir)
        tk.Label(ctrl, textvariable=self._dir_var,
                 font=("Courier New", 9), fg=MUTED, bg=BG,
                 wraplength=200).pack(side="left", padx=8)

        tk.Label(ctrl, text="Limit (optional)", font=("Courier New", 9, "bold"), fg=MUTED, bg=BG).pack(side="left", padx=(10, 2))
        self._limit_var = tk.StringVar(value=DEFAULT_DOWNLOAD_SELECTION)
        self._limit_entry = tk.Entry(ctrl, textvariable=self._limit_var, width=6,
                                     bg=PANEL, fg=TEXT, font=("Courier New", 10), bd=0, justify="center")
        self._limit_entry.pack(side="left")
        tk.Label(ctrl, text="(type number or all)", font=("Courier New", 8), fg=MUTED, bg=BG).pack(side="left", padx=(6, 0))

        self._btn_start = tk.Button(ctrl, text="▶  START",
                                    bg=SUCCESS, fg="#000",
                                    command=self._start, **btn_style)
        self._btn_start.pack(side="right", padx=(6, 0))

        self._btn_pause = tk.Button(ctrl, text="⏸  PAUSE",
                                    bg=WARNING, fg="#000",
                                    command=self._toggle_pause,
                                    state="disabled", **btn_style)
        self._btn_pause.pack(side="right", padx=(6, 0))

        self._btn_stop = tk.Button(ctrl, text="⏹  STOP",
                                   bg=DANGER, fg="white",
                                   command=self._stop,
                                   state="disabled", **btn_style)
        self._btn_stop.pack(side="right", padx=(6, 0))

        # ── Overall Progress ──
        prog_frame = tk.Frame(self, bg=BG)
        prog_frame.pack(fill="x", padx=24, pady=(0, 4))

        self._overall_var = tk.DoubleVar(value=0)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Overall.Horizontal.TProgressbar",
                         troughcolor=PANEL, background=ACCENT2,
                         thickness=14, borderwidth=0)
        ttk.Progressbar(prog_frame, variable=self._overall_var,
                         maximum=100,
                         style="Overall.Horizontal.TProgressbar").pack(fill="x")

        self._overall_label = tk.StringVar(value="Load a link file to begin")
        tk.Label(self, textvariable=self._overall_label,
                 font=("Courier New", 9), fg=MUTED, bg=BG).pack(anchor="w", padx=24)

        # ── Current file progress ──
        cur_frame = tk.Frame(self, bg=BG)
        cur_frame.pack(fill="x", padx=24, pady=(6, 2))

        self._cur_title = tk.StringVar(value="")
        tk.Label(self, textvariable=self._cur_title,
                 font=("Courier New", 9, "bold"), fg=ACCENT,
                 bg=BG, anchor="w").pack(fill="x", padx=24)

        self._cur_var = tk.DoubleVar(value=0)
        style.configure("File.Horizontal.TProgressbar",
                         troughcolor=PANEL, background=ACCENT,
                         thickness=8, borderwidth=0)
        ttk.Progressbar(self, variable=self._cur_var,
                         maximum=100,
                         style="File.Horizontal.TProgressbar").pack(fill="x", padx=24, pady=(2, 8))

        # ── Log ──
        log_frame = tk.Frame(self, bg=PANEL, bd=0)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        self._log = tk.Text(log_frame, bg=PANEL, fg=TEXT,
                             font=("Courier New", 9),
                             relief="flat", bd=0,
                             state="disabled", wrap="word",
                             insertbackground=ACCENT)
        scroll = tk.Scrollbar(log_frame, command=self._log.yview,
                               bg=PANEL, troughcolor=PANEL)
        self._log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._log.pack(fill="both", expand=True, padx=8, pady=8)

        # colour tags
        self._log.tag_configure("ok",   foreground=SUCCESS)
        self._log.tag_configure("err",  foreground=DANGER)
        self._log.tag_configure("info", foreground=ACCENT)
        self._log.tag_configure("warn", foreground=WARNING)
        self._log.tag_configure("muted",foreground=MUTED)

    # ─────────────── HELPERS ───────────────
    def _log_write(self, msg, tag="muted"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"[{ts}] {msg}\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _extract_url(self, value):
        if value is None:
            return ""
        match = re.search(r"https?://\S+", str(value).strip())
        if not match:
            return ""
        return match.group(0).rstrip('"\'')

    def _dedupe_urls(self, rows):
        """Keep first occurrence of each URL and preserve order."""
        seen = set()
        unique = []
        for title, url in rows:
            if url in seen:
                continue
            seen.add(url)
            unique.append((title, url))
        return unique

    def _load_links_file(self):
        path = filedialog.askopenfilename(
            title="Select link file with video URLs",
            filetypes=[("Link files", "*.csv *.txt *.tsv *.list"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            self._urls = []
            suffix = Path(path).suffix.lower()

            if suffix in {".txt", ".list", ".tsv"}:
                with open(path, "r", encoding="utf-8-sig", errors="ignore") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        url = self._extract_url(line)
                        if url:
                            self._urls.append(("", url))
            else:
                with open(path, "r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
                    reader = csv.DictReader(handle)
                    fieldnames = reader.fieldnames or []
                    url_col = next(
                        (c for c in fieldnames if "url" in c.lower() or "link" in c.lower()),
                        None,
                    )
                    title_col = next(
                        (c for c in fieldnames if "title" in c.lower() or "name" in c.lower()),
                        None,
                    )

                    if url_col:
                        for row in reader:
                            url = self._extract_url(row.get(url_col, ""))
                            if not url:
                                continue
                            title = str(row.get(title_col, "")).strip() if title_col else ""
                            self._urls.append((title, url))
                    else:
                        handle.seek(0)
                        for line in handle:
                            line = line.strip()
                            if not line:
                                continue
                            url = self._extract_url(line)
                            if url:
                                self._urls.append(("", url))

            original_count = len(self._urls)
            self._urls = self._dedupe_urls(self._urls)
            duplicate_count = original_count - len(self._urls)

            self._total = len(self._urls)
            self._stat_vars["total"].set(str(self._total))
            self._limit_var.set(DEFAULT_DOWNLOAD_SELECTION)
            self._links_file = path
            self._links_var.set(Path(path).name)
            preview_total = min(self._total, MAX_DOWNLOADS_PER_FILE)
            self._overall_label.set(f"Loaded {self._total} videos — ready to download {preview_total}")
            self._log_write(
                f"Links loaded: {self._total} videos from {Path(path).name} (will download up to {MAX_DOWNLOADS_PER_FILE})",
                "info",
            )
            if duplicate_count:
                self._log_write(f"Removed {duplicate_count} duplicate URLs.", "warn")
        except Exception as e:
            messagebox.showerror("Link File Error", str(e))

    def _choose_dir(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self._output_dir = d
            self._dir_var.set(d)

    def _start(self):
        if not self._urls:
            messagebox.showwarning("No URLs", "Please load a link file first.")
            return
        os.makedirs(self._output_dir, exist_ok=True)
        self._stop_flag = False
        self._paused    = False

        try:
            limit_val = self._limit_var.get().strip().lower()
            if not limit_val or limit_val == "all":
                limit = MAX_DOWNLOADS_PER_FILE
            else:
                limit = int(limit_val)
        except ValueError:
            messagebox.showwarning("Invalid Number", "Enter a positive number or 'all'.")
            return

        if limit <= 0:
            messagebox.showwarning("Invalid Number", "Enter a value greater than 0.")
            return

        limit = min(limit, len(self._urls), MAX_DOWNLOADS_PER_FILE)

        self._active_urls = self._urls[:limit]
        self._total = len(self._active_urls)
        self._stat_vars["total"].set(str(self._total))
        self._overall_label.set(f"Starting download of {self._total} videos")
        
        self._downloaded = 0
        self._failed     = 0
        self._failed_urls = []
        self._archive_file = os.path.join(self._output_dir, "download_archive.txt")
        self._failed_urls_file = os.path.join(self._output_dir, "failed_urls.txt")
        self._start_time = time.time()
        self._stat_vars["done"].set("0")
        self._stat_vars["failed"].set("0")
        self._stat_vars["speed"].set("—")
        self._stat_vars["elapsed"].set("00:00:00")
        self._overall_var.set(0)
        self._cur_var.set(0)

        self._btn_start.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._btn_pause.config(state="normal")

        self._thread = threading.Thread(target=self._download_all, daemon=True)
        self._thread.start()
        self._tick_clock()

    def _toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._btn_pause.config(text="▶  RESUME")
            self._log_write("Paused.", "warn")
        else:
            self._btn_pause.config(text="⏸  PAUSE")
            self._log_write("Resumed.", "info")

    def _stop(self):
        self._stop_flag = True
        self._log_write("Stopping after current download...", "warn")

    def _tick_clock(self):
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            h, r = divmod(elapsed, 3600)
            m, s = divmod(r, 60)
            elapsed_str = f"{h:02d}:{m:02d}:{s:02d}"
            self._clock_var.set(elapsed_str)
            self._stat_vars["elapsed"].set(elapsed_str)
        if not self._stop_flag:
            self.after(1000, self._tick_clock)

    def _is_transient_network_error(self, err: Exception) -> bool:
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

    # ─────────────── DOWNLOAD LOOP ───────────────
    def _download_all(self):
        for i, (title, url) in enumerate(self._active_urls):
            if self._stop_flag:
                break

            while self._paused:
                time.sleep(0.5)

            # Use %(title).150s to avoid incredibly long titles causing OS errors
            display_title = sanitize_filename(title) if title and title != "nan" else f"video_{i+1}"
            out_tmpl   = os.path.join(self._output_dir, "%(title).150s.%(ext)s")

            self._cur_title.set(f"↓ Fetching ... {display_title[:60]}")
            self._log_write(f"[{i+1}/{self._total}] Starting: {display_title}", "info")

            def progress_hook(d):
                if d["status"] == "downloading":
                    total  = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                    downloaded = d.get("downloaded_bytes", 0)
                    pct = min(downloaded / total * 100, 100)

                    speed_bps = d.get("speed") or 0
                    speed_kb  = speed_bps / 1024
                    speed_str = f"{speed_kb:.0f} KB/s" if speed_kb < 1024 else f"{speed_kb/1024:.2f} MB/s"

                    real_filename = os.path.basename(d.get("filename", ""))
                    if real_filename:
                        self._cur_title.set(f"↓ {real_filename[:80]}")

                    self._cur_var.set(pct)
                    self._stat_vars["speed"].set(speed_str)

                    overall_pct = ((self._downloaded + pct/100) / self._total) * 100
                    self._overall_var.set(overall_pct)
                    self._overall_label.set(
                        f"{self._downloaded}/{self._total} done  •  "
                        f"{overall_pct:.1f}%  •  {speed_str}"
                    )

                elif d["status"] == "finished":
                    self._cur_var.set(100)

            ydl_opts = {
                "format":         QUALITY_FORMAT,
                "outtmpl":        out_tmpl,
                "progress_hooks": [progress_hook],
                "quiet":          True,
                "no_warnings":    True,
                "merge_output_format": "mp4",
                "retries":        10,
                "extractor_retries": 5,
                "fragment_retries": 10,
                "concurrent_fragment_downloads": 10,
                "socket_timeout": 20,
                "windowsfilenames": True,
                "continuedl": True,
                "download_archive": self._archive_file,
                # Try cookies if available, uncomment and set browser to bypass age-restricted fully if needed
                # "cookiesfrombrowser": ("chrome",), 
                "postprocessors": [{
                    "key":            "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }],
            }

            downloaded_ok = False
            last_error = None
            for attempt in range(1, NETWORK_RETRY_ATTEMPTS + 1):
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                    downloaded_ok = True
                    break
                except Exception as e:
                    last_error = e
                    if not self._is_transient_network_error(e) or attempt == NETWORK_RETRY_ATTEMPTS:
                        break
                    delay = NETWORK_RETRY_BASE_DELAY_SEC * attempt
                    self._log_write(
                        f"Transient network error for {display_title} (attempt {attempt}/{NETWORK_RETRY_ATTEMPTS}). Retrying in {delay}s...",
                        "warn",
                    )
                    time.sleep(delay)

            if downloaded_ok:
                self._downloaded += 1
                self._stat_vars["done"].set(str(self._downloaded))
                self._log_write(f"✓ Done: {display_title}", "ok")
            else:
                self._failed += 1
                self._failed_urls.append(url)
                self._stat_vars["failed"].set(str(self._failed))
                self._log_write(f"✗ Failed: {display_title} → {last_error}", "err")

            self._cur_var.set(0)
            if INTER_ITEM_DELAY_SEC > 0:
                time.sleep(INTER_ITEM_DELAY_SEC)

        if self._failed_urls:
            try:
                with open(self._failed_urls_file, "w", encoding="utf-8") as handle:
                    for failed_url in self._failed_urls:
                        handle.write(f"{failed_url}\n")
                self._log_write(
                    f"Saved failed URLs to: {Path(self._failed_urls_file).name}",
                    "warn",
                )
            except Exception as e:
                self._log_write(f"Could not save failed URLs file: {e}", "err")
        # ── Finished ──
        self._stop_flag = True
        self._btn_start.config(state="normal")
        self._btn_stop.config(state="disabled")
        self._btn_pause.config(state="disabled")
        self._cur_title.set("")
        self._overall_label.set(
            f"All done! ✓ {self._downloaded} downloaded   ✗ {self._failed} failed"
        )
        self._log_write(
            f"Session complete — {self._downloaded} ok, {self._failed} failed", "ok"
        )
        self._start_time = None


if __name__ == "__main__":
    app = DownloaderApp()
    app.mainloop()