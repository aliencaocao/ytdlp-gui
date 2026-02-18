# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YT-DLP GUI is a desktop video/audio downloader built with Python and Tkinter, wrapping the yt-dlp library. It bundles ffmpeg, ffprobe, and deno into a single executable via PyInstaller.

## Build Commands

```bash
# Install dependencies
pip install -U -r requirements.txt

# Generate Windows version info file (required before build)
create-version-file version.yml --outfile version.txt

# Build Windows executable
pyinstaller --log-level DEBUG -F -i icon.ico --version-file=version.txt --add-data "icon.png:." --add-data "ffmpeg.exe:." --add-data "ffprobe.exe:." --add-data "deno.exe:." --distpath ./ --clean --noconfirm --optimize 2 "yt-dlp-gui.py"

# Build Linux executable (no ffmpeg/ffprobe bundled)
pyinstaller --log-level DEBUG -F --add-data "icon.png:." --add-data "deno:." --distpath ./ --clean --noconfirm --optimize 2 "yt-dlp-gui.py"

# Run directly (requires ffmpeg/ffprobe in PATH or same directory)
python yt-dlp-gui.py
```

## Architecture

The entire application is a single file: `yt-dlp-gui.py` (~960 lines). There are no tests.

### Key Components

- **Global state**: `download_queue` (list of `DownloadTask`), `ongoing_task` flag, `ydl_base_opts` (default yt-dlp configuration)
- **`DownloadTask(Frame)`**: Tkinter Frame subclass representing one download job. Handles info extraction, progress tracking, and download execution in background threads. Uses `progress_hook` and `postprocessor_hook` callbacks from yt-dlp.
- **`ScrolledWindow(Frame)`**: Reusable scrollable container widget using Canvas.
- **`parse_info()` / `parse_format()`**: Extract and normalize format metadata from yt-dlp's info dictionaries into a simplified structure with video/audio codec, resolution, bitrate info.
- **`detect_and_handle()`**: Gateway function all 3 buttons route through. Validates URL, runs flat playlist detection in a background thread, then routes to playlist selector or single-video handler.
- **`show_playlist_selector()`**: Toplevel popup for selecting which playlist videos to download, with checkboxes and mode-specific buttons.
- **`handle_download_video_best()` / `handle_download_audio_best()` / `handle_download_info()`**: Per-video download handlers. `handle_download_info` supports `on_complete` callback (for sequential chaining) and `apply_to_urls` (for applying one format to many videos).
- **`extract_flat_info()`**: Fast playlist detection using `extract_flat='in_playlist'` — gets titles/IDs/durations without full format extraction.
- **`handle_private_video()`**: Popup flow for browser cookie authentication when encountering private videos.

### Threading Model

Downloads and info extraction run in daemon threads. Tkinter UI updates from threads use `widget.after(0, callback)` to schedule on the main thread. The `do_tasks()` function polls `download_queue` every 500ms to start the next queued task. Playlist detection also runs in a background thread via `detect_and_handle()`.

### Resource Path Handling

`get_res_path()` resolves bundled resources, using `sys._MEIPASS` when running as a PyInstaller frozen executable, or `__file__` directory in development.

### Platform Differences

- **Windows**: Bundles ffmpeg.exe/ffprobe.exe/deno.exe; uses Windows registry (`HKCU\Software\YT-DLP GUI`) to persist last save path; DPI awareness via `ctypes.windll.shcore.SetProcessDpiAwareness(2)`.
- **Linux**: Does not bundle ffmpeg (uses system ffmpeg); bundles deno; persists path in `~/.config/yt-dlp/last_path.txt`.

## Build Artifacts

- `yt-dlp-gui.spec` — PyInstaller spec for Windows (bundles ffmpeg.exe, ffprobe.exe, deno.exe)
- `yt-dlp-gui-linux.spec` — PyInstaller spec for Linux (bundles deno only)
- `version.yml` — Version metadata used by `pyinstaller-versionfile` to generate `version.txt`
- `build.txt` — Quick-reference build commands

## CI/CD

GitHub Actions workflows in `.github/workflows/` build for Windows and Linux on push/PR to `master`. Both use Python 3.14, UPX for compression, and a custom `aliencaocao/pyinstaller_action` action.

## Dependencies

- `yt_dlp[default,curl-cffi]` — core download engine
- `sanitize_filename` — safe filenames
- `pyinstaller` + `pyinstaller-versionfile` — packaging
- External binaries: ffmpeg, ffprobe (from yt-dlp/FFmpeg-Builds), deno (for yt-dlp JS extractors)

## Gotchas

- **ScrolledWindow mousewheel**: `<Enter>`/`<Leave>` on a parent frame fires when cursor moves onto child widgets, unbinding the mousewheel handler. When adding scrollable child widgets, bind `<MouseWheel>` recursively to all children.
- **yt-dlp `noplaylist: True`**: Must be set on per-video ydl_opts when downloading individual playlist entries, otherwise yt-dlp re-expands the entire playlist.
- **`ydl_base_opts['noplaylist']` stays `False`**: The base opts need `noplaylist: False` so `extract_flat_info()` can see playlist entries. Individual handlers override to `True`.
