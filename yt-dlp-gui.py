import copy
import ctypes
import logging
import os
import re
import sys
import threading
import urllib.parse
from tkinter import *
from tkinter import filedialog, messagebox
from tkinter.ttk import *
from typing import Any, Callable, Union

if sys.platform == 'win32':
    import winreg

import yt_dlp
from sanitize_filename import sanitize

frozen = getattr(sys, 'frozen', False)  # frozen -> running in exe
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.addLevelName(15, 'STATUS')  # between debug 10 and info 20
logger.setLevel(15)
download_queue = []
ongoing_task: bool = False
logger.info(f'YT-DLP GUI (yt-dlp {yt_dlp.version.__version__}) (Python {sys.version})')


def get_res_path(relative_path: str) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller
     Relative path will always get extracted into root!"""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
    if os.path.exists(os.path.join(base_path, relative_path)):
        return os.path.join(base_path, relative_path)
    else:
        raise FileNotFoundError(f'{os.path.join(base_path, relative_path)} is not found!')


# Add deno to PATH
try:
    deno_exe = 'deno.exe' if sys.platform == 'win32' else 'deno'
    deno_path = get_res_path(deno_exe)
    os.environ["PATH"] += os.pathsep + os.path.dirname(deno_path)
    logger.info(f'Found {deno_exe} at {deno_path}, added to PATH')
except FileNotFoundError:
    logger.warning('Deno not found! yt-dlp might fail on some sites.')

ydl_base_opts: dict[str, Any] = {'outtmpl': '%(title)s.%(ext)s',
                                 'restrictfilenames': True,
                                 'nocheckcertificate': True,
                                 'ignoreerrors': False,
                                 'logtostderr': False,
                                 'geo-bypass': True,
                                 'quiet': True,
                                 'no_warnings': True,
                                 'default_search': 'auto',
                                 'source_address': '0.0.0.0',
                                 'windowsfilenames': True,
                                 'overwrites': True,
                                 'cachedir': False,
                                 'age_limit': 100,
                                 'noplaylist': False,
                                 'live_from_start': True,
                                 'no-video-multistreams': True,
                                 'no-audio-multistreams': True,
                                 'check_formats': 'selected',
                                 'fixup': 'detect_or_warn',
                                 'extractor_args': {'youtube': {'skip': ['dash', 'hls']}, },
                                 'ffmpeg_location': get_res_path('ffmpeg.exe') if sys.platform == 'win32' else 'ffmpeg',
                                 }
percent_str_regex = re.compile(r'\d{1,3}\.\d{1,2}%')
ansi_escape_regex = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def handle_private_video(e: object, url: str, ydl_opts: dict, func: Callable[[str, dict, bool], Union[dict, bool]]) -> Union[dict, bool]:
    """Returns info if func is successful after login and False if not"""
    result = False

    def handle_choose():
        nonlocal result
        if v.get() == 0: return
        browser = [browsers[v.get() - 1]]  # yt_dlp expects a list
        ydl_opts['cookiesfrombrowser'] = browser
        popup.title('Logging in...')
        choose_button_var.set('Logging in...')
        choose_button.configure(state=DISABLED)
        popup.update()
        info = func(url, ydl_opts, True)  # can be download() or extract_info()
        if info:
            ydl_base_opts['cookiesfrombrowser'] = browser
            result = info
            messagebox.showinfo('Login', 'Login successful! Specified browser will be used until you close this app. Browser will be asked again if you attempt to download another private video that the existing accounts in this browser cannot access.')
        else:
            messagebox.showerror('Login', 'Login failed. The browser you chose does not have an account with access to this video.')
        popup.destroy()

    if str(e).endswith('Private video. Sign in if you\'ve been granted access to this video'):
        browsers = ['brave', 'chrome', 'chromium', 'edge', 'firefox', 'opera', 'safari', 'vivaldi']
        popup = Toplevel(takefocus=True)
        popup.title('Choose browser to fetch account cookies from')
        Label(popup, text='This video is private. Please choose the browser you use that is logged into your video platform.\nIf you are on Windows and use Chrome or Edge, please close your browser before choosing.').pack()
        v = IntVar(value=0)
        choose_button_var = StringVar(value='Choose')
        for i, option in enumerate(browsers):
            Radiobutton(popup, text=option, variable=v, value=i + 1).pack(anchor="w")
        choose_button = Button(popup, command=handle_choose, textvariable=choose_button_var)
        choose_button.pack()
        root.wait_window(popup)
    return result


def download(urls: Union[list, str], ydl_opts=None, ignore_error: bool = False) -> bool:
    """Return whether download is successful"""
    if ydl_opts is None: ydl_opts = copy.deepcopy(ydl_base_opts)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download(urls if isinstance(urls, list) else [urls])
    except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as e:
        if ignore_error: return False
        return handle_private_video(e, urls, ydl_opts, download)
    except Exception as e:
        messagebox.showerror('Error', f'Error while downloading: {e}')
        return False
    else:
        return True


def extract_info(url: str, ydl_opts: dict, ignore_error: bool = False) -> dict:
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return ydl.sanitize_info(info)
    except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as e:
        if ignore_error: return {}
        result = handle_private_video(e, url, ydl_opts, extract_info)
        if not result:
            return {}
        else:  # success
            return result
    except Exception as e:
        messagebox.showerror('Error', f'Error while extracting info: {e}')
        return {}


def extract_flat_info(url: str) -> dict:
    """Quickly extract playlist metadata without full format extraction.
    Uses extract_flat='in_playlist' so only titles/IDs/durations are fetched.
    For single videos, yt-dlp returns the normal info dict (no 'entries' key)."""
    ydl_opts = copy.deepcopy(ydl_base_opts)
    ydl_opts['extract_flat'] = 'in_playlist'
    ydl_opts['quiet'] = True
    ydl_opts['no_warnings'] = True
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return ydl.sanitize_info(info) if info else {}
    except Exception as e:
        logger.warning(f'Flat extraction failed: {e}')
        return {}


class ScrolledWindow(Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.parent = parent

        # creating scrollbars
        self.xscrlbr = Scrollbar(self.parent, orient=HORIZONTAL)
        self.xscrlbr.pack(fill=X, side=BOTTOM)
        self.yscrlbr = Scrollbar(self.parent)
        self.yscrlbr.pack(fill=Y, side=RIGHT)

        # creating canvas
        self.canv = Canvas(self.parent)
        # noinspection PyArgumentList
        self.canv.config(relief='flat', width=10, heigh=10, bd=2)
        self.canv.pack(side=TOP, fill=BOTH, expand=True)

        # accociating scrollbar comands to canvas scroling
        self.xscrlbr.config(command=self.canv.xview)
        self.yscrlbr.config(command=self.canv.yview)

        # creating a frame to inserto to canvas
        self.scrollwindow = Frame(self.parent)
        self.canv.create_window(0, 0, window=self.scrollwindow, anchor=NW)
        self.canv.config(xscrollcommand=self.xscrlbr.set, yscrollcommand=self.yscrlbr.set, scrollregion=self.canv.bbox('all'))
        self.yscrlbr.lift(self.scrollwindow)
        self.xscrlbr.lift(self.scrollwindow)
        self.scrollwindow.bind('<Configure>', self._configure_window)
        self.scrollwindow.bind('<Enter>', self._bound_to_mousewheel)
        self.scrollwindow.bind('<Leave>', self._unbound_to_mousewheel)

    def _bound_to_mousewheel(self, event):
        self.canv.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.canv.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.canv.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _configure_window(self, event):
        # update the scrollbars to match the size of the inner frame
        size = (self.scrollwindow.winfo_reqwidth(), self.scrollwindow.winfo_reqheight())
        # noinspection PyTypeChecker
        self.canv.config(scrollregion='0 0 %s %s' % size)
        if self.scrollwindow.winfo_reqwidth() != self.canv.winfo_width():
            # update the canvas's width to fit the inner frame
            self.canv.config(width=self.scrollwindow.winfo_reqwidth())
        if self.scrollwindow.winfo_reqheight() != self.canv.winfo_height():
            # update the canvas's width to fit the inner frame
            self.canv.config(height=self.scrollwindow.winfo_reqheight())


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    pass


class DownloadTask(Frame):
    def __init__(self, url: str, path: str, ydl_opts: dict, parent: Widget, info: dict = None):
        super().__init__(parent, borderwidth=2, relief='groove')
        self.url = url
        self.path = path
        self.parent = parent
        self.ydl_opts = ydl_opts
        self.thread = None
        self.ydl_opts['progress_hooks'] = [self.progress_hook]
        self.ydl_opts['postprocessor_hooks'] = [self.postprocessor_hook]
        self.status = StringVar(value='Queued - Waiting to extract info...')
        self.progress = IntVar(value=0)

        self.extracting = False
        self.extracted = False
        self.extract_info_succeed = False

        # Placeholder UI
        self.title_label = Label(self, text=f'URL: {self.url}')
        self.title_label.pack(side=TOP)
        self.details_frame = Frame(self)
        self.details_frame.pack(side=TOP)
        self.status_label = Label(self, textvariable=self.status, anchor=CENTER)
        self.status_label.pack(side=TOP, fill=X, expand=True, padx=10)
        self.pack(side=TOP, fill=X, pady=(0, 5), ipadx=5)

        if info:
            self.title = info.get('title', 'Unknown Title')
            self.duration = info.get('duration_string', 'Unknown Duration')
            self.size = info.get('filesize', info.get('filesize_approx', 0))
            self.formats = info.get('formats', {})
            self._update_ui_after_extraction()

    def start_extraction(self):
        self.extracting = True
        self.status.set('Extracting info...')
        threading.Thread(target=self._extract_info_thread, daemon=True).start()

    def _extract_info_thread(self):
        info = extract_info(self.url, self.ydl_opts)
        if not info:
            self.extracting = False
            self.extracted = True
            self.status.set('Failed to extract info')
            self.after(0, lambda: messagebox.showerror('Error', 'URL is invalid or extraction failed!'))
            return

        parsed_info = parse_info(info)
        self.title = sanitize(parsed_info['title'])
        self.duration = parsed_info['duration']
        self.size = parsed_info['size']
        self.formats = parsed_info['formats']

        self.after(0, self._update_ui_after_extraction)

    def _update_ui_after_extraction(self):
        self.title_label.config(text=self.title)
        Label(self.details_frame, text=f'Duration: {self.duration}').pack(side=LEFT)
        Label(self.details_frame, text=f'Size: {round(self.size / (1024 * 1024), 2)}MB' if self.size else 'unknown size').pack(side=LEFT)
        format_str = ''
        if self.formats['video']: format_str += f'Video: {self.formats["video"]["resolution"]}@{self.formats["video"]["fps"]}fps {self.formats["video"]["codec"]} {"HDR" if self.formats["video"]["hdr"] else ""}'
        if self.formats['audio']: format_str += f'Audio: {self.formats["audio"]["sample_rate"]} {self.formats["audio"]["bitrate"]} {self.formats["audio"]["codec"]}'
        Label(self.details_frame, text=format_str).pack(side=LEFT)

        Label(self, text=f'Save to: {self.path}').pack(side=TOP)  # Show path roughly

        # Re-pack status label to be at bottom
        self.status_label.pack_forget()
        self.progress_bar = Progressbar(self, orient=HORIZONTAL, length=100, mode='determinate', variable=self.progress, value=0)
        self.progress_bar.pack(side=TOP, fill=X, expand=True, padx=10)
        self.status_label.pack(side=TOP, fill=X, expand=True, padx=10)

        self.extract_info_succeed = True
        self.extracted = True
        self.extracting = False
        self.status.set('Ready to download')

    def start_task(self):
        global ongoing_task
        status('Downloading')
        self.status.set('Starting download...')
        self.thread = threading.Thread(target=download, args=(self.url, self.ydl_opts), daemon=True)
        self.thread.start()
        ongoing_task = True

    def progress_hook(self, d: dict):
        global ongoing_task
        if d['status'] == 'downloading' and '_default_template' in d:
            percent_str = percent_str_regex.search(d['_percent_str'])
            if percent_str:
                percent_str = percent_str.group()
                clean_status = ansi_escape_regex.sub('', d["_default_template"])
                self.status.set(f'Downloading: {clean_status}')
                self.progress.set(int(float(percent_str.rstrip('%'))))
        elif d['status'] == 'finished':  # may have postprocessing later but can start downloading next task already since postprocessing no need internet and is usually fast
            if self in download_queue: download_queue.remove(self)
            self.status.set('Finished')
            ongoing_task = False
            status('Ready', log=False)
        elif d['status'] == 'error':
            if self in download_queue: download_queue.remove(self)
            ongoing_task = False
            self.status.set('Download error')
            status('Ready', log=False)

    def postprocessor_hook(self, d: dict):
        global ongoing_task
        if d['status'] == 'started' or d['status'] == 'processing':
            self.status.set('Post-processing')
        else:
            if self in download_queue: download_queue.remove(self)
            self.status.set('Finished')
            status('Ready', log=False)
            # do not set ongoing_ask = False here as the next download task may have already began


root = Tk()
root.iconphoto(True, PhotoImage(file=get_res_path('icon.png')))
root.title(f'YT-DLP GUI - Initializing')
status_var = StringVar(value='Initializing')
status_bar = LabelFrame(root, padding=(2, 2))  # status bar must be at front else scrollable window will block it
status_bar.pack(expand=True, fill=X, side=BOTTOM, pady=(0, 0))

status_bar.rowconfigure(0, weight=1)
status_bar.columnconfigure(1, weight=1)
status_text = Label(status_bar, textvariable=status_var, anchor=E)
status_text.grid(row=0, column=2, sticky=E)


def status(text: Any, log: bool = True):
    global status_text
    text = text.strip()
    status_var.set(text)
    text = text.replace('\n', ' ')
    if log:
        if text.lower() == 'ready':
            logger.log(15, text + '\n')  # custom STATUS logging level 15
        else:
            logger.log(15, text)
    root.title(f'YT-DLP GUI - {text}')


def parse_info(info: dict, best_format_only: bool = True) -> dict:
    title = info.get('title', 'Unknown Title')
    duration = info.get('duration_string', 'Unknown Duration')
    size = info.get('filesize', info.get('filesize_approx', 0))
    subtitles = info.get('subtitles', {})
    if best_format_only:  # only 1 for video and/or 1 for audio
        formats = {'video': None, 'audio': None}
        if 'requested_formats' in info:  # best video AND best audio
            temp = [parse_format(f) for f in info['requested_formats']]  # best video/best audio only
            for f in temp:
                if f['video']: formats['video'] = f['video']
                if f['audio']: formats['audio'] = f['audio']
        else:  # best video OR audio only
            format_id = info.get('format_id')
            if format_id and 'formats' in info:
                for f in info['formats']:
                    if f['format_id'] == format_id:
                        formats = parse_format(f)
                        break
    else:
        formats = [parse_format(f) for f in info.get('formats', []) if f.get('format_note', '') != 'storyboard' and (f.get('vcodec', 'none') != 'none' or f.get('acodec', 'none') != 'none') and f.get('url', '')]
    # noinspection PyUnboundLocalVariable
    return {'title': title, 'duration': duration, 'size': size, 'subtitles': subtitles, 'formats': formats}


def parse_format(format: dict) -> dict:
    parsed = {'video': {}, 'audio': {}}
    contains_video = format['vcodec'] != 'none'
    contains_audio = format['acodec'] != 'none'
    parsed['format_id'] = format['format_id']
    parsed['ext'] = format['ext']
    parsed['size'] = format.get('filesize', format.get('filesize_approx', 0))

    def parse_codec(codec: str) -> str:
        mapping = {'mp4v': 'H263', 'av01': 'AV1', 'avc1': 'H264/AVC', 'hev1': 'H265/HEVC', 'vp9': 'VP9', 'vp09': 'VP9', 'vp8': 'VP8', 'mp4a': 'AAC', 'opus': 'Opus'}
        return mapping.get(codec.split('.')[0].lower(), codec.split('.')[0].lower())

    if contains_video: parsed['video'] = {'resolution': format['resolution'], 'fps': format['fps'],
                                          'codec': parse_codec(format['vcodec']),
                                          'hdr': format['dynamic_range'] != 'SDR'}
    if contains_audio: parsed['audio'] = {'sample_rate': f'{round(format["asr"] / 1000, 2)}khz' if 'asr' in format else 'unknown sample rate',
                                          'bitrate': f'{round(format["abr"])}kbps' if format.get('abr', None) and float(format['abr']) else 'unknown bitrate',
                                          'codec': parse_codec(format['acodec'])}
    return parsed


def is_valid_url(url: str) -> bool:
    try:
        result = urllib.parse.urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False


def get_entry_url(entry: dict, playlist_url: str) -> str:
    """Construct a direct video URL from a flat playlist entry.
    For YouTube, flat entries may have 'url' as just a video ID.
    For other extractors, 'url' may already be a full URL."""
    entry_url = entry.get('url', '')
    if entry_url.startswith(('http://', 'https://')):
        return entry_url
    # YouTube-style: url is just a video ID
    video_id = entry_url or entry.get('id', '')
    if video_id:
        parsed = urllib.parse.urlparse(playlist_url)
        if 'youtube' in parsed.netloc or 'youtu.be' in parsed.netloc:
            return f'https://www.youtube.com/watch?v={video_id}'
        # For other sites, try constructing from the base domain
        return f'{parsed.scheme}://{parsed.netloc}/watch?v={video_id}'
    return playlist_url


def show_playlist_selector(playlist_info: dict, playlist_url: str, path: str, mode: str):
    """Show a popup for selecting which playlist videos to download."""
    entries = playlist_info.get('entries', [])
    if not entries:
        messagebox.showerror('Error', 'No videos found in playlist!')
        return
    entries = [e for e in entries if e is not None]

    playlist_title = playlist_info.get('title', 'Unknown Playlist')
    popup = Toplevel(takefocus=True)
    popup.title('Select Videos')

    # Header
    header_frame = Frame(popup)
    header_frame.pack(side=TOP, fill=X, padx=10, pady=(10, 5))
    Label(header_frame, text=f'{playlist_title}', font=('', 11, 'bold')).pack(side=TOP, anchor=W)
    Label(header_frame, text=f'{len(entries)} videos').pack(side=TOP, anchor=W)

    # Select all checkbox
    select_all_var = BooleanVar(value=True)
    check_vars = []

    def on_select_all():
        val = select_all_var.get()
        for var in check_vars:
            var.set(val)
        update_button_text()

    select_all_check = Checkbutton(header_frame, text='Select All / Deselect All',
                                   variable=select_all_var, command=on_select_all)
    select_all_check.pack(side=TOP, anchor=W, pady=(5, 0))

    # Scrollable list of videos
    scroll_container = Frame(popup)
    scroll_container.pack(expand=True, fill=BOTH, side=TOP, padx=10, pady=5)
    scrollable = ScrolledWindow(scroll_container)
    list_frame = scrollable.scrollwindow

    # Buttons frame (created before checkboxes so update_button_text can reference them)
    button_frame = Frame(popup)
    button_frame.pack(side=BOTTOM, fill=X, padx=10, pady=(5, 10))

    def get_selected():
        return [entries[i] for i, var in enumerate(check_vars) if var.get()]

    # Create buttons based on mode (need references for update_button_text)
    if mode == 'customize':
        def on_same_format():
            selected = get_selected()
            if not selected:
                return
            popup.destroy()
            _queue_selected_entries(selected, playlist_url, path, 'customize_same')

        def on_each():
            selected = get_selected()
            if not selected:
                return
            popup.destroy()
            _queue_selected_entries(selected, playlist_url, path, 'customize_each')

        same_btn = Button(button_frame, text=f'Same Format for All ({len(entries)})',
                          command=on_same_format)
        same_btn.pack(side=LEFT, expand=True, fill=X, padx=(0, 2))
        each_btn = Button(button_frame, text=f'Customize Each ({len(entries)})',
                          command=on_each)
        each_btn.pack(side=LEFT, expand=True, fill=X, padx=(2, 0))
    else:
        def on_download():
            selected = get_selected()
            if not selected:
                return
            popup.destroy()
            _queue_selected_entries(selected, playlist_url, path, mode)

        dl_btn = Button(button_frame, text=f'Download Selected ({len(entries)})',
                        command=on_download)
        dl_btn.pack(side=LEFT, expand=True, fill=X)

    Button(button_frame, text='Cancel', command=popup.destroy).pack(side=RIGHT, padx=(5, 0))

    def update_button_text():
        count = sum(1 for var in check_vars if var.get())
        if mode == 'customize':
            same_btn.config(text=f'Same Format for All ({count})')
            each_btn.config(text=f'Customize Each ({count})')
            same_btn.config(state=NORMAL if count > 0 else DISABLED)
            each_btn.config(state=NORMAL if count > 0 else DISABLED)
        else:
            dl_btn.config(text=f'Download Selected ({count})')
            dl_btn.config(state=NORMAL if count > 0 else DISABLED)

    for i, entry in enumerate(entries):
        var = BooleanVar(value=True)
        check_vars.append(var)
        title = entry.get('title', f'Video {i + 1}')
        duration = entry.get('duration')
        if duration:
            mins, secs = divmod(int(duration), 60)
            hours, mins = divmod(mins, 60)
            dur_str = f' [{hours}:{mins:02d}:{secs:02d}]' if hours else f' [{mins}:{secs:02d}]'
        else:
            dur_str = ''
        cb = Checkbutton(list_frame, text=f'{i + 1}. {title}{dur_str}', variable=var,
                         command=update_button_text)
        cb.pack(side=TOP, anchor=W, padx=5, pady=1)

    # Bind mousewheel scrolling at the canvas level so it works over all children
    scrollable.canv.bind_all("<MouseWheel>", lambda e: scrollable.canv.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def _unbind_on_destroy(e):
        try:
            scrollable.canv.unbind_all("<MouseWheel>")
        except TclError:
            pass

    popup.bind("<Destroy>", _unbind_on_destroy)

    # Auto-size width to fit content, capped at 50% screen width for initial size.
    # User can still manually resize wider than the cap.
    popup.update_idletasks()
    max_width = popup.winfo_screenwidth() // 2
    needed_width = popup.winfo_reqwidth() + 40  # padding for scrollbar + borders
    initial_width = min(needed_width, max_width)
    popup.geometry(f'{initial_width}x500')


def _queue_selected_entries(entries: list, playlist_url: str, path: str, mode: str):
    """Queue download tasks for selected playlist entries."""
    if mode == 'video_best':
        for entry in entries:
            video_url = get_entry_url(entry, playlist_url)
            ydl_opts = copy.deepcopy(ydl_base_opts)
            ydl_opts['noplaylist'] = True
            ydl_opts['outtmpl'] = os.path.join(path, ydl_opts['outtmpl'] if isinstance(ydl_opts['outtmpl'], str) else ydl_opts['outtmpl']['default'])
            download_queue.append(DownloadTask(video_url, path, ydl_opts, queue_frame))
    elif mode == 'audio_best':
        for entry in entries:
            video_url = get_entry_url(entry, playlist_url)
            ydl_opts = copy.deepcopy(ydl_base_opts)
            ydl_opts['noplaylist'] = True
            ydl_opts.update({'format': 'bestaudio'})
            ydl_opts['outtmpl'] = os.path.join(path, ydl_opts['outtmpl'] if isinstance(ydl_opts['outtmpl'], str) else ydl_opts['outtmpl']['default'])
            ydl_opts['outtmpl'] = ydl_opts['outtmpl'].replace('.%(ext)s', '_audio.%(ext)s')
            download_queue.append(DownloadTask(video_url, path, ydl_opts, queue_frame))
    elif mode == 'customize_same':
        # Show format picker for first video, then apply to all
        urls = [get_entry_url(e, playlist_url) for e in entries]
        first_url = urls[0]
        handle_download_info(first_url, path, apply_to_urls=urls[1:] if len(urls) > 1 else None)
    elif mode == 'customize_each':
        # Chain through format picker for each video sequentially
        urls = [get_entry_url(e, playlist_url) for e in entries]
        _chain_customize(urls, path, 0)


def _chain_customize(urls: list, path: str, index: int):
    """Show format picker for each URL sequentially."""
    if index >= len(urls):
        return
    handle_download_info(urls[index], path,
                         on_complete=lambda: _chain_customize(urls, path, index + 1))


def detect_and_handle(url: str, path: str, mode: str):
    """Gateway function that detects playlists and routes accordingly."""
    if not url:
        messagebox.showerror('Error', 'URL is empty!')
        return
    if not is_valid_url(url):
        messagebox.showerror('Error', 'URL is invalid!')
        return
    if not path.strip():
        messagebox.showerror('Error', 'Download directory is empty! Please choose a folder.')
        return

    # Disable buttons during detection
    download_video_button.config(state=DISABLED)
    download_audio_button.config(state=DISABLED)
    download_info_button.config(state=DISABLED)

    # Show checking popup
    checking_popup = Toplevel(takefocus=True)
    checking_popup.title('Checking...')
    Label(checking_popup, text='Checking URL...').pack(padx=20, pady=20)
    checking_popup.update()

    def _re_enable():
        download_video_button.config(state=NORMAL)
        download_audio_button.config(state=NORMAL)
        download_info_button.config(state=NORMAL)

    def on_popup_close():
        checking_popup.destroy()
        _re_enable()

    checking_popup.protocol("WM_DELETE_WINDOW", on_popup_close)

    def _detect_thread():
        info = extract_flat_info(url)

        def _handle_result():
            if not checking_popup.winfo_exists():
                _re_enable()
                return
            checking_popup.destroy()

            if not info:
                _re_enable()
                messagebox.showerror('Error', 'URL is invalid or extraction failed!')
                return

            is_playlist = info.get('_type') == 'playlist' or 'entries' in info
            if is_playlist and info.get('entries'):
                _re_enable()
                show_playlist_selector(info, url, path, mode)
            else:
                # Single video - delegate to original handler
                _re_enable()
                _handle_single(url, path, mode)

        root.after(0, _handle_result)

    threading.Thread(target=_detect_thread, daemon=True).start()


def _handle_single(url: str, path: str, mode: str):
    """Delegate to the original per-mode handler for a single video."""
    if mode == 'video_best':
        handle_download_video_best(url, path)
    elif mode == 'audio_best':
        handle_download_audio_best(url, path)
    elif mode == 'customize':
        handle_download_info(url, path)


def handle_download_video_best(url: str, path: str):
    ydl_opts = copy.deepcopy(ydl_base_opts)
    ydl_opts['noplaylist'] = True
    ydl_opts['outtmpl'] = os.path.join(path, ydl_opts['outtmpl'] if isinstance(ydl_opts['outtmpl'], str) else ydl_opts['outtmpl']['default'])
    download_queue.append(DownloadTask(url, path, ydl_opts, queue_frame))


def handle_download_audio_best(url: str, path: str):
    ydl_opts = copy.deepcopy(ydl_base_opts)
    ydl_opts['noplaylist'] = True
    ydl_opts.update({'format': 'bestaudio'})
    ydl_opts['outtmpl'] = os.path.join(path, ydl_opts['outtmpl'] if isinstance(ydl_opts['outtmpl'], str) else ydl_opts['outtmpl']['default'])
    ydl_opts['outtmpl'] = ydl_opts['outtmpl'].replace('.%(ext)s', '_audio.%(ext)s')
    download_queue.append(DownloadTask(url, path, ydl_opts, queue_frame))


def handle_download_info(url: str, path: str, ydl_opts: dict = None,
                         on_complete: Callable = None, apply_to_urls: list = None):
    if not url:
        messagebox.showerror('Error', 'URL is empty!')
        if on_complete: on_complete()
        return
    if not is_valid_url(url):
        messagebox.showerror('Error', 'URL is invalid!')
        if on_complete: on_complete()
        return
    if not ydl_opts: ydl_opts = copy.deepcopy(ydl_base_opts)
    ydl_opts['noplaylist'] = True

    # Disable button to prevent spamming
    download_info_button.config(state=DISABLED)

    # Create loading popup
    loading_popup = Toplevel(takefocus=True)
    loading_popup.title('Loading...')
    Label(loading_popup, text='Extracting info, please wait...').pack(padx=20, pady=20)
    loading_popup.update()

    def on_loading_close():
        loading_popup.destroy()
        download_info_button.config(state=NORMAL)
        if on_complete: on_complete()

    loading_popup.protocol("WM_DELETE_WINDOW", on_loading_close)

    def _extract_thread():
        info = extract_info(url, ydl_opts)

        def _handle_result():
            # Check if loading popup still exists (might be closed by user)
            if not loading_popup.winfo_exists():
                status('Ready')
                return

            loading_popup.destroy()
            if not info:
                status('Ready')
                messagebox.showerror('Error', 'URL is invalid or extraction failed!')
                download_info_button.config(state=NORMAL)
                if on_complete: on_complete()
                return

            _show_details(info)

        root.after(0, _handle_result)

    def _show_details(info):
        parsed_info = parse_info(info, best_format_only=False)
        details_window = Toplevel(takefocus=True)  # no need mainloop here as below we use the general global mainloop function
        details_window.title('Extracted Info')

        def on_details_close():
            details_window.destroy()
            download_info_button.config(state=NORMAL)
            if on_complete: on_complete()

        details_window.protocol("WM_DELETE_WINDOW", on_details_close)

        Label(details_window, text=f'{parsed_info["title"]} ({parsed_info["duration"]})', anchor=CENTER).pack(side=TOP, fill=X, expand=True, padx=10)

        scroll_container_frame = Frame(details_window)
        scroll_container_frame.pack(expand=True, fill=BOTH, side=TOP)
        scrollableFrame = ScrolledWindow(scroll_container_frame)
        formats_frame = LabelFrame(scrollableFrame.scrollwindow, text='Download Options')
        formats_frame.pack(side=TOP, fill=BOTH, expand=True, padx=(10, 10), pady=(10, 0))
        formats = parsed_info['formats']

        # noinspection PyArgumentList
        def on_select_single_format(*args):
            if video_only_formats[video_selected_format.get()] is None and audio_only_formats[audio_selected_format.get()] is None:  # if both selected nothing, unlock radio buttons
                for radio_button in radiobutton_frame.winfo_children():
                    radio_button.configure(state=NORMAL)
                selected_format.set('')
            else:
                for radio_button in radiobutton_frame.winfo_children():
                    radio_button.configure(state=DISABLED)
                selected = []
                if video_only_formats[video_selected_format.get()]: selected.append(video_only_formats[video_selected_format.get()])
                if audio_only_formats[audio_selected_format.get()]: selected.append(audio_only_formats[audio_selected_format.get()])
                selected_format.set('+'.join(selected))  # allow 1 only
            try:
                if video_only_formats[video_selected_format.get()] is None and audio_only_formats[audio_selected_format.get()] is not None:
                    audio_convert_selector.configure(state=NORMAL)
                else:
                    audio_convert_selector.configure(state=DISABLED)
                    audio_convert_quality_selector.configure(state=DISABLED)
            except NameError:  # if audio convert selector is not defined yet
                pass

        def on_select_format(*args):
            download_button.configure(state=NORMAL if selected_format.get() else DISABLED)

        def on_select_audio_convert_format(*args):
            audio_convert_quality_selector.configure(state=NORMAL if audio_convert_format.get() != 'Do not convert' else DISABLED)

        def handle_download():
            nonlocal ydl_opts
            ydl_opts['format'] = selected_format.get()
            if video_only_formats[video_selected_format.get()] is None and audio_only_formats[audio_selected_format.get()] is not None and valid_audio_convert_formats[audio_convert_format.get()] is not None:
                ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': valid_audio_convert_formats[audio_convert_format.get()], 'preferredquality': audio_convert_quality_values[audio_convert_quality.get()]}]  # 0 highest, 10 lowest.
            ydl_opts['outtmpl'] = os.path.join(path, ydl_opts['outtmpl'] if isinstance(ydl_opts['outtmpl'], str) else ydl_opts['outtmpl']['default'])

            # Construct task_info for DownloadTask
            task_info = {
                'title': parsed_info['title'],
                'duration_string': parsed_info['duration'],
                'filesize': parsed_info['size'],
                'formats': {'video': None, 'audio': None}
            }

            # Find selected formats
            sel_fmt = selected_format.get()
            if sel_fmt:
                sel_ids = sel_fmt.split('+')
                for f in parsed_info['formats']:
                    if f['format_id'] in sel_ids:
                        if f['video']: task_info['formats']['video'] = f['video']
                        if f['audio']: task_info['formats']['audio'] = f['audio']

            download_queue.append(DownloadTask(url, path, ydl_opts, queue_frame, task_info))

            # If apply_to_urls is set, queue the same format for all other URLs
            if apply_to_urls:
                for extra_url in apply_to_urls:
                    extra_opts = ydl_opts.copy()
                    extra_opts['noplaylist'] = True
                    # Reset outtmpl for each new video
                    base_tmpl = ydl_base_opts['outtmpl'] if isinstance(ydl_base_opts['outtmpl'], str) else ydl_base_opts['outtmpl']['default']
                    extra_opts['outtmpl'] = os.path.join(path, base_tmpl)
                    extra_opts['progress_hooks'] = []
                    extra_opts['postprocessor_hooks'] = []
                    download_queue.append(DownloadTask(extra_url, path, extra_opts, queue_frame))

            ydl_opts = copy.deepcopy(ydl_base_opts)  # reset for next task
            details_window.destroy()
            root.lift()
            download_info_button.config(state=NORMAL)
            if on_complete: on_complete()

        download_button = Button(scrollableFrame.scrollwindow, text='Download', command=handle_download)  # have to define first else callbacks below complain
        selected_format = StringVar()
        selected_format.trace_add('write', on_select_format)
        video_only_formats, audio_only_formats = {'Select video format': None}, {'Select audio format': None}  # {text: value} except for None
        radiobutton_frame = Frame(formats_frame, relief='groove', borderwidth=3)
        radiobutton_frame.pack(side=TOP, fill=X, expand=True)
        for f in formats:
            if f['video'] and f['audio']:  # video AND audio
                Radiobutton(radiobutton_frame, variable=selected_format, value=f['format_id'],
                            text=f'Video: {f["video"]["resolution"]}@{f["video"]["fps"]}fps {f["video"]["codec"]} {"HDR" if f["video"]["hdr"] else ""}\n'
                                 f'Audio: {f["audio"]["sample_rate"]} {f["audio"]["bitrate"]} {f["audio"]["codec"]}\n'
                                 f'File extension: {f["ext"]} Size: ' + (f'{round(f["size"] / (1024 * 1024), 2)}MB' if f["size"] else 'unknown size')).pack(side=TOP, fill=X, expand=True, pady=(0, 10))
            else:  # video only or audio only
                if f['video']: video_only_formats[f'{f["video"]["resolution"]}@{f["video"]["fps"]}fps {f["video"]["codec"]} {"HDR" if f["video"]["hdr"] else ""}'] = f['format_id']
                if f['audio']: audio_only_formats[f'{f["audio"]["sample_rate"]} {f["audio"]["bitrate"]} {f["audio"]["codec"]}'] = f['format_id']
        if not len(radiobutton_frame.winfo_children()): Label(radiobutton_frame, text='No stream containing both video and audio available', anchor=CENTER).pack(side=TOP, fill=X, expand=True)

        custom_formats_frame = LabelFrame(formats_frame, text='Customize', borderwidth=3)
        custom_formats_frame.pack(side=TOP, fill=X, expand=True)
        video_selected_format = StringVar(value='Select video format')
        video_selected_format.trace_add('write', on_select_single_format)
        audio_selected_format = StringVar(value='Select audio format')
        audio_selected_format.trace_add('write', on_select_single_format)
        OptionMenu(custom_formats_frame, video_selected_format, 'Select video format', *video_only_formats.keys()).pack(side=TOP, fill=X, expand=True, pady=(0, 10))
        OptionMenu(custom_formats_frame, audio_selected_format, 'Select audio format', *audio_only_formats.keys()).pack(side=TOP, fill=X, expand=True, pady=(0, 10))
        audio_convert_format = StringVar(value='Do not convert')
        valid_audio_convert_formats = {'Do not convert': None, 'AAC (.m4a)': 'aac', 'ALAC (.m4a)': 'alac', 'FLAC (.flac)': 'flac', 'm4a (.m4a)': 'm4a', 'mp3 (.mp3)': 'mp3', 'Opus (.opus)': 'opus', 'Vorbis (.ogg)': 'vorbis', 'WAV (.wav)': 'wav'}
        audio_convert_frame = LabelFrame(formats_frame, text='Convert audio format to', borderwidth=3)
        audio_convert_frame.pack(side=TOP, fill=X, expand=True)
        audio_convert_selector = OptionMenu(audio_convert_frame, audio_convert_format, 'Do not convert', *valid_audio_convert_formats.keys(), command=on_select_audio_convert_format)
        audio_convert_selector.pack(side=TOP, fill=X, expand=True, pady=(5, 5))
        audio_convert_selector.configure(state=DISABLED)
        audio_convert_quality = StringVar(value='5')
        # FFmpeg uses 0 for highest quality and 10 for lowest. We want to show 10 as highest to user.
        # So we map UI '10' -> 0, '9' -> 1, ..., '0' -> 10.
        audio_convert_quality_values = {f'{10 - i} {"(Highest Quality)" if i == 0 else "(Lowest Quality)" if i == 10 else "(Medium Quality)" if i == 5 else ""}': i for i in range(11)}
        # Sort keys so they appear in order 10, 9, ... 0 in the dropdown
        sorted_keys = sorted(audio_convert_quality_values.keys(), key=lambda x: int(x.split()[0]), reverse=True)
        audio_convert_quality_selector = OptionMenu(audio_convert_frame, audio_convert_quality, '5 (Medium Quality)', *sorted_keys)
        audio_convert_quality_selector.pack(side=TOP, fill=X, expand=True, pady=(5, 5))
        audio_convert_quality_selector.configure(state=DISABLED)
        download_button.pack(side=TOP, fill=X, expand=True, padx=10, pady=(0, 10))  # defined at top
        status('Ready')

    threading.Thread(target=_extract_thread, daemon=True).start()


def select_save_path():
    path = filedialog.askdirectory(initialdir=initial_dir, title='Choose a folder to save the downloaded file')
    if path:
        path_input.delete(0, END)
        path_input.insert(0, path)
    if sys.platform == 'win32':
        winreg.SetValue(winreg.HKEY_CURRENT_USER, 'Software\\YT-DLP GUI', winreg.REG_SZ, path)
    else:
        os.makedirs(os.path.expanduser('~/.config/yt-dlp'), exist_ok=True)
        with open(os.path.expanduser('~/.config/yt-dlp/last_path.txt'), 'w+') as f:
            f.write(path)


def do_tasks():
    if download_queue and not ongoing_task:
        task = download_queue[0]
        if not task.extracted and not task.extracting:
            task.start_extraction()
        elif task.extracted and task.extract_info_succeed:
            task.start_task()
        elif task.extracted and not task.extract_info_succeed:
            download_queue.remove(task)
            status('Ready')
    queue_frame.after(500, do_tasks)


initial_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
if sys.platform == 'win32':
    try:
        initial_dir = winreg.QueryValue(winreg.HKEY_CURRENT_USER, 'Software\\YT-DLP GUI')
    except FileNotFoundError:  # if key not found
        pass
elif os.path.isfile(os.path.expanduser('~/.config/yt-dlp/last_path.txt')):
    with open(os.path.expanduser('~/.config/yt-dlp/last_path.txt'), 'r') as f:
        initial_dir = f.read()

url_input_frame = Frame(root)
url_input_frame.pack(expand=True, fill=BOTH, side=TOP, pady=(5, 10))
Label(url_input_frame, text='URL: ').pack(side=LEFT, padx=(10, 0))
url_input = Entry(url_input_frame, width=50)
url_input.pack(expand=True, fill=X, side=LEFT, padx=(2, 10))
url_input.focus_set()

path_input_frame = Frame(root)
path_input_frame.pack(expand=True, fill=BOTH, side=TOP, pady=(5, 10))
Label(path_input_frame, text='Path: ').pack(side=LEFT, padx=(10, 0))
path_input = Entry(path_input_frame, width=50)
path_input.pack(expand=True, fill=X, side=LEFT, padx=(2, 0))
path_input.insert(0, initial_dir.replace('\\', '/'))
path_select_button = Button(path_input_frame, text='Choose', command=select_save_path)
path_select_button.pack(side=LEFT, padx=(2, 10))

buttons_frame = Frame(root)
buttons_frame.pack(expand=True, fill=BOTH, side=TOP, anchor=NW)
download_video_button = Button(buttons_frame, text='Download Video', command=lambda: detect_and_handle(url_input.get(), path_input.get(), 'video_best'))
download_video_button.pack(expand=True, fill=X, side=LEFT, padx=(10, 0))
download_audio_button = Button(buttons_frame, text='Download Audio', command=lambda: detect_and_handle(url_input.get(), path_input.get(), 'audio_best'))
download_audio_button.pack(expand=True, fill=X, side=LEFT, padx=(2, 0))
download_info_button = Button(buttons_frame, text='Customize Downloads', command=lambda: detect_and_handle(url_input.get(), path_input.get(), 'customize'))
download_info_button.pack(expand=True, fill=X, side=LEFT, padx=(2, 10))

scroll_container_frame = Frame(root)
scroll_container_frame.pack(expand=True, fill=BOTH, side=TOP)
scrollableFrame = ScrolledWindow(scroll_container_frame)
queue_frame = LabelFrame(scrollableFrame.scrollwindow, text='Download Queue')
queue_frame.pack(fill=BOTH, expand=True, anchor=CENTER, padx=(10, 10), pady=(10, 0))
do_tasks()

status('Ready')
root.mainloop()
