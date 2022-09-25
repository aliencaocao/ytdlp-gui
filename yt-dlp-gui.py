import os, sys
import json
import ctypes
import logging
from typing import Union, Any
import threading

from tkinter import *
from tkinter.ttk import *
from tkinter import messagebox, filedialog

import yt_dlp
import requests

frozen = getattr(sys, 'frozen', False***REMOVED***  # frozen -> running in exe
logging.basicConfig(format='%(asctime***REMOVED***s - %(levelname***REMOVED***s - %(message***REMOVED***s'***REMOVED***
logger = logging.getLogger(__name__***REMOVED***
logging.addLevelName(15, 'STATUS'***REMOVED***  # between debug 10 and info 20
logger.setLevel(logging.DEBUG***REMOVED***
download_queue = []
ongoing_task: bool = False
logger.info(f'YT-DLP GUI (yt-dlp {yt_dlp.version.__version__}***REMOVED*** (Python {sys.version}***REMOVED***'***REMOVED***


def get_res_path(relative_path: str***REMOVED*** -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller
     Relative path will always get extracted into root!"""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(__file__***REMOVED******REMOVED***
    if os.path.exists(os.path.join(base_path, relative_path***REMOVED******REMOVED***:
        return os.path.join(base_path, relative_path***REMOVED***
    else:
        raise FileNotFoundError(f'{os.path.join(base_path, relative_path***REMOVED***} is not found!'***REMOVED***


ydl_base_opts: dict[str, Any] = {'outtmpl': '%(extractor***REMOVED***s-TITLE-%(id***REMOVED***s.%(ext***REMOVED***s',
                                 'restrictfilenames': True,
                                 'nocheckcertificate': True,
                                 'ignoreerrors': False,
                                 'logtostderr': False,
                                 'geo-bypass': True,
                                 'no_color': True,
                                 'quiet': True,
                                 'no_warnings': True,
                                 'default_search': 'auto',
                                 'source_address': '0.0.0.0',
                                 'windowsfilenames': True,
                                 'overwrites': True,
                                 'logger': logger,
                                 'cachedir': False,
                                 'age_limit': 100,
                                 'noplaylist': True,
                                 'live_from_start': True,
                                 'ffmpeg-location': get_res_path('ffmpeg.exe'***REMOVED***,
                                 'no-video-multistreams': True,
                                 'no-audio-multistreams': True}


def download(urls: Union[list, str], ydl_opts=None***REMOVED***:
    if ydl_opts is None: ydl_opts = ydl_base_opts
    with yt_dlp.YoutubeDL(ydl_opts***REMOVED*** as ydl:
        ydl.download(urls if isinstance(urls, list***REMOVED*** else [urls]***REMOVED***


def extract_info(url: str, ydl_opts: dict***REMOVED*** -> dict:
    try:
        print(ydl_opts***REMOVED***
        with yt_dlp.YoutubeDL(ydl_opts***REMOVED*** as ydl:
            info = ydl.extract_info(url, download=False***REMOVED***
            return ydl.sanitize_info(info***REMOVED***
    except Exception as e:
        messagebox.showerror('Error', f'Error while extracting info: {e}'***REMOVED***
        return {}


class ScrolledWindow(Frame***REMOVED***:
    def __init__(self, parent, **kwargs***REMOVED***:
        super(***REMOVED***.__init__(parent, **kwargs***REMOVED***
        self.parent = parent

        # creating scrollbars
        self.xscrlbr = Scrollbar(self.parent, orient=HORIZONTAL***REMOVED***
        self.xscrlbr.pack(fill=X, side=BOTTOM***REMOVED***
        self.yscrlbr = Scrollbar(self.parent***REMOVED***
        self.yscrlbr.pack(fill=Y, side=RIGHT***REMOVED***

        # creating canvas
        self.canv = Canvas(self.parent***REMOVED***
        # noinspection PyArgumentList
        self.canv.config(relief='flat', width=10, heigh=10, bd=2***REMOVED***
        self.canv.pack(side=TOP, fill=BOTH, expand=True***REMOVED***

        # accociating scrollbar comands to canvas scroling
        self.xscrlbr.config(command=self.canv.xview***REMOVED***
        self.yscrlbr.config(command=self.canv.yview***REMOVED***

        # creating a frame to inserto to canvas
        self.scrollwindow = Frame(self.parent***REMOVED***
        self.canv.create_window(0, 0, window=self.scrollwindow, anchor=NW***REMOVED***
        self.canv.config(xscrollcommand=self.xscrlbr.set, yscrollcommand=self.yscrlbr.set, scrollregion=self.canv.bbox('all'***REMOVED******REMOVED***
        self.yscrlbr.lift(self.scrollwindow***REMOVED***
        self.xscrlbr.lift(self.scrollwindow***REMOVED***
        self.scrollwindow.bind('<Configure>', self._configure_window***REMOVED***
        self.scrollwindow.bind('<Enter>', self._bound_to_mousewheel***REMOVED***
        self.scrollwindow.bind('<Leave>', self._unbound_to_mousewheel***REMOVED***

    def _bound_to_mousewheel(self, event***REMOVED***:
        self.canv.bind_all("<MouseWheel>", self._on_mousewheel***REMOVED***

    def _unbound_to_mousewheel(self, event***REMOVED***:
        self.canv.unbind_all("<MouseWheel>"***REMOVED***

    def _on_mousewheel(self, event***REMOVED***:
        self.canv.yview_scroll(int(-1 * (event.delta / 120***REMOVED******REMOVED***, "units"***REMOVED***

    def _configure_window(self, event***REMOVED***:
        # update the scrollbars to match the size of the inner frame
        size = (self.scrollwindow.winfo_reqwidth(***REMOVED***, self.scrollwindow.winfo_reqheight(***REMOVED******REMOVED***
        # noinspection PyTypeChecker
        self.canv.config(scrollregion='0 0 %s %s' % size***REMOVED***
        if self.scrollwindow.winfo_reqwidth(***REMOVED*** != self.canv.winfo_width(***REMOVED***:
            # update the canvas's width to fit the inner frame
            self.canv.config(width=self.scrollwindow.winfo_reqwidth(***REMOVED******REMOVED***
        if self.scrollwindow.winfo_reqheight(***REMOVED*** != self.canv.winfo_height(***REMOVED***:
            # update the canvas's width to fit the inner frame
            self.canv.config(height=self.scrollwindow.winfo_reqheight(***REMOVED******REMOVED***


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2***REMOVED***
except:
    pass


class DownloadTask(Frame***REMOVED***:
    def __init__(self, url: str, path: str, ydl_opts: dict, parent: Widget***REMOVED***:
        super(***REMOVED***.__init__(parent, borderwidth=2, relief='groove'***REMOVED***
        self.url = url
        self.parent = parent
        self.ydl_opts = ydl_opts
        self.thread = None
        self.ydl_opts['progress_hooks'] = [self.progress_hook]
        self.ydl_opts['postprocessor_hooks'] = [self.postprocessor_hook]
        self.status = StringVar(***REMOVED***
        self.status.set('Queued'***REMOVED***
        self.progress = IntVar(value=0***REMOVED***

        info = extract_info(url, ydl_opts***REMOVED***
        if not info: return
        parsed_info = parse_info(info***REMOVED***
        self.title = parsed_info['title']
        self.duration = parsed_info['duration']
        self.size = parsed_info['size']
        self.formats = parsed_info['formats']
        if isinstance(self.ydl_opts['outtmpl'], dict***REMOVED***:
            self.ydl_opts['outtmpl']['default'] = self.ydl_opts['outtmpl']['default'].replace('TITLE', self.title***REMOVED***
        else:
            self.ydl_opts['outtmpl'] = self.ydl_opts['outtmpl'].replace('TITLE', self.title***REMOVED***

        Label(self, text=self.title***REMOVED***.pack(side=TOP***REMOVED***
        details_frame = Frame(self***REMOVED***
        details_frame.pack(side=TOP***REMOVED***
        Label(details_frame, text=f'Duration: {self.duration}'***REMOVED***.pack(side=LEFT***REMOVED***
        Label(details_frame, text=f'Size: {round(self.size / (1024 * 1024***REMOVED***, 2***REMOVED***}MB' if self.size else 'unknown size'***REMOVED***.pack(side=LEFT***REMOVED***
        format_str = ''
        if self.formats[
            'video']: format_str += f'Video: {self.formats["video"]["resolution"]}@{self.formats["video"]["fps"]}fps {self.formats["video"]["codec"]} {"HDR" if self.formats["video"]["hdr"] else ""}'
        if self.formats['audio']: format_str += f'Audio: {self.formats["audio"]["sample_rate"]} {self.formats["audio"]["bitrate"]} {self.formats["audio"]["codec"]}'
        Label(details_frame, text=format_str***REMOVED***.pack(side=LEFT***REMOVED***
        Label(self, text=f'Save to: {path}'***REMOVED***.pack(side=TOP***REMOVED***
        self.progress_bar = Progressbar(self, orient=HORIZONTAL, length=100, mode='determinate', variable=self.progress, value=0***REMOVED***
        self.progress_bar.pack(side=TOP, fill=X, expand=True, padx=10***REMOVED***
        Label(self, textvariable=self.status, anchor=CENTER***REMOVED***.pack(side=TOP, fill=X, expand=True, padx=10***REMOVED***
        self.pack(side=TOP, fill=X, pady=(0, 5***REMOVED***, ipadx=5***REMOVED***

    def start_task(self***REMOVED***:
        global ongoing_task
        status('Downloading'***REMOVED***
        self.thread = threading.Thread(target=download, args=(self.url, self.ydl_opts***REMOVED******REMOVED***
        self.thread.start(***REMOVED***
        ongoing_task = True

    def progress_hook(self, d: dict***REMOVED***:
        global ongoing_task
        if d['status'] == 'downloading':
            self.status.set(f'Downloading: {d["_percent_str"]} at {d["_speed_str"]} ETA {d["_eta_str"]}'***REMOVED***
            self.progress.set(int(float(d['_percent_str'].rstrip('%'***REMOVED******REMOVED******REMOVED******REMOVED***
        elif d['status'] == 'finished':  # may have postprocessing later but can start downloading next task already since postprocessing no need internet and is usually fast
            if self in download_queue: download_queue.remove(self***REMOVED***
            self.status.set('Finished'***REMOVED***
            ongoing_task = False
            status('Ready', log=False***REMOVED***
        elif d['status'] == 'error':
            if self in download_queue: download_queue.remove(self***REMOVED***
            ongoing_task = False
            self.status.set('Download error'***REMOVED***
            status('Ready', log=False***REMOVED***

    def postprocessor_hook(self, d: dict***REMOVED***:
        global ongoing_task
        if d['status'] == 'started' or d['status'] == 'processing':
            self.status.set('Processing'***REMOVED***
        else:
            if self in download_queue: download_queue.remove(self***REMOVED***
            self.status.set('Finished'***REMOVED***
            status('Ready', log=False***REMOVED***
            # do not set ongoing_ask = False here as the next download task may have already began


root = Tk(***REMOVED***
root.iconphoto(True, PhotoImage(file=get_res_path('icon.png'***REMOVED******REMOVED******REMOVED***
root.title(f'YT-DLP GUI - Initializing'***REMOVED***
status_var = StringVar(value='Initializing'***REMOVED***
status_bar = LabelFrame(root, padding=(2, 2***REMOVED******REMOVED***  # status bar must be at front else scrollable window will block it
status_bar.pack(expand=True, fill=X, side=BOTTOM, pady=(0, 0***REMOVED******REMOVED***

status_bar.rowconfigure(0, weight=1***REMOVED***
status_bar.columnconfigure(1, weight=1***REMOVED***
testing_text = Label(status_bar, text='', anchor=W***REMOVED***
testing_text.grid(row=0, column=0, sticky=W***REMOVED***
status_text = Label(status_bar, textvariable=status_var, anchor=E***REMOVED***
status_text.grid(row=0, column=2, sticky=E***REMOVED***


def status(text: Any, log: bool = True***REMOVED***:
    global status_text
    text = text.strip(***REMOVED***
    status_var.set(text***REMOVED***
    text = text.replace('\n', ' '***REMOVED***
    if log:
        if text.lower(***REMOVED*** == 'ready':
            logger.log(15, text + '\n'***REMOVED***  # custom STATUS logging level 15
        else:
            logger.log(15, text***REMOVED***
    root.title(f'YT-DLP GUI - {text}'***REMOVED***


def parse_info(info: dict, best_format_only: bool = True***REMOVED*** -> dict:
    title = info['title']
    duration = info['duration_string']
    size = info.get('filesize', info.get('filesize_approx', 0***REMOVED******REMOVED***
    subtitles = info['subtitles']
    if best_format_only:  # only 1 for video and/or 1 for audio
        if 'requested_formats' in info:  # best video AND best audio
            temp = [parse_format(f***REMOVED*** for f in info['requested_formats']]  # best video/best audio only
            formats = {}
            for f in temp:
                if f['video']: formats['video'] = f['video']
                if f['audio']: formats['audio'] = f['audio']
        else:  # best video OR audio only
            format_id = info['format_id']
            for f in info['formats']:
                if f['format_id'] == format_id:
                    formats = parse_format(f***REMOVED***
                    break
    else:
        formats = [parse_format(f***REMOVED*** for f in info['formats'] if
                   f.get('format_note', ''***REMOVED*** != 'storyboard' and (f.get('vcodec', 'none'***REMOVED*** != 'none' or f.get('acodec', 'none'***REMOVED*** != 'none'***REMOVED*** and f.get('url', ''***REMOVED***]
    # noinspection PyUnboundLocalVariable
    return {'title': title, 'duration': duration, 'size': size, 'subtitles': subtitles, 'formats': formats}


def parse_format(format: dict***REMOVED*** -> dict:
    parsed = {'video': {}, 'audio': {}}
    contains_video = format['vcodec'] != 'none'
    contains_audio = format['acodec'] != 'none'
    parsed['format_id'] = format['format_id']
    parsed['ext'] = format['ext']
    parsed['size'] = format.get('filesize', format.get('filesize_approx', 0***REMOVED******REMOVED***

    def parse_codec(codec: str***REMOVED*** -> str:
        mapping = {'mp4v': 'H263', 'av01': 'AV1', 'avc1': 'H264/AVC', 'hev1': 'H265/HEVC', 'vp9': 'VP9', 'vp8': 'VP8', 'mp4a': 'AAC', 'opus': 'Opus'}
        return mapping.get(codec.split('.'***REMOVED***[0].lower(***REMOVED***, codec.split('.'***REMOVED***[0].lower(***REMOVED******REMOVED***

    if contains_video: parsed['video'] = {'resolution': format['resolution'], 'fps': format['fps'], 'codec': parse_codec(format['vcodec']***REMOVED***, 'hdr': format['dynamic_range'] != 'SDR'}
    if contains_audio: parsed['audio'] = {'sample_rate': f'{round(format["asr"] / 1000, 2***REMOVED***}khz' if 'asr' in format else 'unknown sample rate',
                                          'bitrate': f'{round(format["abr"]***REMOVED***}kbps' if float(format['abr']***REMOVED*** else 'unknown bitrate', 'codec': parse_codec(format['acodec']***REMOVED***}
    return parsed


def check_url(url: str***REMOVED*** -> bool:
    try:
        requests.get(url***REMOVED***
    except:
        return False
    return True


def handle_download_video_best(url: str, path: str***REMOVED***:
    if not url:
        messagebox.showerror('Error', 'URL is empty!'***REMOVED***
        return
    if not check_url(url***REMOVED***:
        messagebox.showerror('Error', 'URL is invalid!'***REMOVED***
        return
    ydl_opts = ydl_base_opts.copy(***REMOVED***
    ydl_opts['outtmpl'] = os.path.join(path, ydl_opts['outtmpl'] if isinstance(ydl_opts['outtmpl'], str***REMOVED*** else ydl_opts['outtmpl']['default']***REMOVED***
    download_queue.append(DownloadTask(url, path, ydl_opts, queue_frame***REMOVED******REMOVED***


def handle_download_audio_best(url: str, path: str***REMOVED***:
    if not url:
        messagebox.showerror('Error', 'URL is empty!'***REMOVED***
        return
    if not check_url(url***REMOVED***:
        messagebox.showerror('Error', 'URL is invalid!'***REMOVED***
        return
    ydl_opts = ydl_base_opts.copy(***REMOVED***
    ydl_opts.update({'format': 'bestaudio'}***REMOVED***
    ydl_opts['outtmpl'] = os.path.join(path, ydl_opts['outtmpl'] if isinstance(ydl_opts['outtmpl'], str***REMOVED*** else ydl_opts['outtmpl']['default']***REMOVED***
    ydl_opts['outtmpl'] = ydl_opts['outtmpl'].replace('.%(ext***REMOVED***s', '_audio.%(ext***REMOVED***s'***REMOVED***
    download_queue.append(DownloadTask(url, path, ydl_opts, queue_frame***REMOVED******REMOVED***


def handle_download_info(url: str, path: str, ydl_opts: dict = None***REMOVED***:
    if not url:
        messagebox.showerror('Error', 'URL is empty!'***REMOVED***
        return
    if not check_url(url***REMOVED***:
        messagebox.showerror('Error', 'URL is invalid!'***REMOVED***
        return
    if not ydl_opts: ydl_opts = ydl_base_opts.copy(***REMOVED***
    status('Extracting info'***REMOVED***
    info = extract_info(url, ydl_opts***REMOVED***
    if not info:
        status('Ready'***REMOVED***
        return
    parsed_info = parse_info(info, best_format_only=False***REMOVED***
    details_window = Toplevel(***REMOVED***  # no need mainloop here as below we use the general global mainloop function
    details_window.title('Extracted Info'***REMOVED***
    Label(details_window, text=f'{parsed_info["title"]} ({parsed_info["duration"]}***REMOVED***', anchor=CENTER***REMOVED***.pack(side=TOP, fill=X, expand=True, padx=10***REMOVED***

    scroll_container_frame = Frame(details_window***REMOVED***
    scroll_container_frame.pack(expand=True, fill=BOTH, side=TOP***REMOVED***
    scrollableFrame = ScrolledWindow(scroll_container_frame***REMOVED***
    formats_frame = LabelFrame(scrollableFrame.scrollwindow, text='Download Options'***REMOVED***
    formats_frame.pack(side=TOP, fill=BOTH, expand=True, padx=(10, 10***REMOVED***, pady=(10, 0***REMOVED******REMOVED***
    formats = parsed_info['formats']

    # noinspection PyArgumentList
    def on_select_single_format(*args***REMOVED***:
        if video_only_formats[video_selected_format.get(***REMOVED***] is None and audio_only_formats[audio_selected_format.get(***REMOVED***] is None:  # if both selected nothing, unlock radio buttons
            for radio_button in radiobutton_frame.winfo_children(***REMOVED***:
                radio_button.configure(state=NORMAL***REMOVED***
            selected_format.set(''***REMOVED***
        else:
            for radio_button in radiobutton_frame.winfo_children(***REMOVED***:
                radio_button.configure(state=DISABLED***REMOVED***
            selected = []
            if video_only_formats[video_selected_format.get(***REMOVED***]: selected.append(video_only_formats[video_selected_format.get(***REMOVED***]***REMOVED***
            if audio_only_formats[audio_selected_format.get(***REMOVED***]: selected.append(audio_only_formats[audio_selected_format.get(***REMOVED***]***REMOVED***
            selected_format.set('+'.join(selected***REMOVED******REMOVED***  # allow 1 only

    def on_select_format(*args***REMOVED***:
        download_button.configure(state=NORMAL if selected_format.get(***REMOVED*** else DISABLED***REMOVED***

    def handle_download(***REMOVED***:
        nonlocal ydl_opts
        ydl_opts['format'] = selected_format.get(***REMOVED***
        ydl_opts['outtmpl'] = os.path.join(path, ydl_opts['outtmpl'] if isinstance(ydl_opts['outtmpl'], str***REMOVED*** else ydl_opts['outtmpl']['default']***REMOVED***
        download_queue.append(DownloadTask(url, path, ydl_opts, queue_frame***REMOVED******REMOVED***
        ydl_opts = ydl_base_opts.copy(***REMOVED***  # reset for next task
        details_window.destroy(***REMOVED***
        root.lift(***REMOVED***

    download_button = Button(details_window, text='Download', command=handle_download***REMOVED***  # have to define first else callbacks below complain
    selected_format = StringVar(***REMOVED***
    selected_format.trace('w', on_select_format***REMOVED***
    video_only_formats, audio_only_formats = {'Select video format': None}, {'Select audio format': None}  # {text: value} except for None
    radiobutton_frame = Frame(formats_frame, relief='groove', borderwidth=3***REMOVED***
    radiobutton_frame.pack(side=TOP, fill=X, expand=True***REMOVED***
    for f in formats:
        if f['video'] and f['audio']:  # video AND audio
            Radiobutton(radiobutton_frame, variable=selected_format, value=f['format_id'],
                        text=f'Video: {f["video"]["resolution"]}@{f["video"]["fps"]}fps {f["video"]["codec"]} {"HDR" if f["video"]["hdr"] else ""}\n'
                             f'Audio: {f["audio"]["sample_rate"]} {f["audio"]["bitrate"]} {f["audio"]["codec"]}\n'
                             f'File extension: {f["ext"]} Size: ' + (f'{round(f["size"] / (1024 * 1024***REMOVED***, 2***REMOVED***}MB' if f["size"] else 'unknown size'***REMOVED******REMOVED***.pack(side=TOP, fill=X,
                                                                                                                                                        expand=True, pady=(0, 10***REMOVED******REMOVED***
        else:  # video only or audio only
            if f['video']: video_only_formats[f'{f["video"]["resolution"]}@{f["video"]["fps"]}fps {f["video"]["codec"]} {"HDR" if f["video"]["hdr"] else ""}'] = f['format_id']
            if f['audio']: audio_only_formats[f'{f["audio"]["sample_rate"]} {f["audio"]["bitrate"]} {f["audio"]["codec"]}'] = f['format_id']
    if not len(radiobutton_frame.winfo_children(***REMOVED******REMOVED***: Label(radiobutton_frame, text='No stream containing both video and audio available', anchor=CENTER***REMOVED***.pack(side=TOP, fill=X,
                                                                                                                                                             expand=True***REMOVED***

    custom_formats_frame = LabelFrame(formats_frame, text='Customize', borderwidth=3***REMOVED***
    custom_formats_frame.pack(side=TOP, fill=X, expand=True***REMOVED***
    video_selected_format = StringVar(value='Select video format'***REMOVED***
    video_selected_format.trace('w', on_select_single_format***REMOVED***
    audio_selected_format = StringVar(value='Select audio format'***REMOVED***
    audio_selected_format.trace('w', on_select_single_format***REMOVED***
    OptionMenu(custom_formats_frame, video_selected_format, 'Select video format', *video_only_formats.keys(***REMOVED******REMOVED***.pack(side=TOP, fill=X, expand=True, pady=(0, 10***REMOVED******REMOVED***
    OptionMenu(custom_formats_frame, audio_selected_format, 'Select audio format', *audio_only_formats.keys(***REMOVED******REMOVED***.pack(side=TOP, fill=X, expand=True, pady=(0, 10***REMOVED******REMOVED***
    download_button.pack(side=TOP, fill=X, expand=True, padx=10, pady=(0, 10***REMOVED******REMOVED***  # defined at top
    status('Ready'***REMOVED***


def select_save_path(***REMOVED***:
    path = filedialog.askdirectory(initialdir=os.getcwd(***REMOVED***, title='Choose a folder to save the downloaded file'***REMOVED***
    if path:
        path_input.delete(0, END***REMOVED***
        path_input.insert(0, path***REMOVED***


def do_tasks(***REMOVED***:
    if download_queue and not ongoing_task:
        task = download_queue[0]
        task.start_task(***REMOVED***
    queue_frame.after(1000, do_tasks***REMOVED***
    root.update(***REMOVED***


url_input_frame = Frame(root***REMOVED***
url_input_frame.pack(expand=True, fill=BOTH, side=TOP, pady=(5, 10***REMOVED******REMOVED***
Label(url_input_frame, text='URL: '***REMOVED***.pack(side=LEFT, padx=(10, 0***REMOVED******REMOVED***
url_input = Entry(url_input_frame, width=50***REMOVED***
url_input.pack(expand=True, fill=X, side=LEFT, padx=(2, 10***REMOVED******REMOVED***
url_input.focus_set(***REMOVED***

path_input_frame = Frame(root***REMOVED***
path_input_frame.pack(expand=True, fill=BOTH, side=TOP, pady=(5, 10***REMOVED******REMOVED***
Label(path_input_frame, text='Path: '***REMOVED***.pack(side=LEFT, padx=(10, 0***REMOVED******REMOVED***
path_input = Entry(path_input_frame, width=50***REMOVED***
path_input.pack(expand=True, fill=X, side=LEFT, padx=(2, 0***REMOVED******REMOVED***
path_input.insert(0, os.getcwd(***REMOVED***.replace('\\', '/'***REMOVED******REMOVED***
path_select_button = Button(path_input_frame, text='Choose', command=select_save_path***REMOVED***
path_select_button.pack(side=LEFT, padx=(2, 10***REMOVED******REMOVED***

buttons_frame = Frame(root***REMOVED***
buttons_frame.pack(expand=True, fill=BOTH, side=TOP, anchor=NW***REMOVED***
download_video_button = Button(buttons_frame, text='Download Video', command=lambda: handle_download_video_best(url_input.get(***REMOVED***, path_input.get(***REMOVED******REMOVED******REMOVED***
download_video_button.pack(expand=True, fill=X, side=LEFT, padx=(10, 0***REMOVED******REMOVED***
download_audio_button = Button(buttons_frame, text='Download Audio', command=lambda: handle_download_audio_best(url_input.get(***REMOVED***, path_input.get(***REMOVED******REMOVED******REMOVED***
download_audio_button.pack(expand=True, fill=X, side=LEFT, padx=(2, 0***REMOVED******REMOVED***
download_info_button = Button(buttons_frame, text='Extract Info', command=lambda: handle_download_info(url_input.get(***REMOVED***, path_input.get(***REMOVED******REMOVED******REMOVED***
download_info_button.pack(expand=True, fill=X, side=LEFT, padx=(2, 10***REMOVED******REMOVED***

scroll_container_frame = Frame(root***REMOVED***
scroll_container_frame.pack(expand=True, fill=BOTH, side=TOP***REMOVED***
scrollableFrame = ScrolledWindow(scroll_container_frame***REMOVED***
queue_frame = LabelFrame(scrollableFrame.scrollwindow, text='Download Queue'***REMOVED***
queue_frame.pack(fill=BOTH, expand=True, anchor=CENTER, padx=(10, 10***REMOVED***, pady=(10, 0***REMOVED******REMOVED***
do_tasks(***REMOVED***

status('Ready'***REMOVED***
mainloop(***REMOVED***
