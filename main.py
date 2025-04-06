import cv2
import os
import numpy
from pathlib import Path
import subprocess
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
try:
    from tkinterdnd2 import *
except ImportError:
    class TkinterDnD:
        @staticmethod
        def Tk():
            print("Warning: tkinterdnd2 not found. Drag and drop disabled.")
            return tk.Tk()
        DND_FILES = None
    print("\n--- Optional Feature Notice ---")
    print("Drag and drop support requires the 'tkinterdnd2-universal' package.")
    print("You can install it via pip:")
    print("  pip install tkinterdnd2-universal")
    print("The application will run without drag and drop.\n")
import sys
import json
import datetime
import random
from tkinter import font as tkfont
import platform
import threading
import queue
import shlex
import zipfile
import logging
import traceback
import ctypes

if platform.system() == "Linux":
    try:
        subprocess.run(['which', 'xdotool'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

VERSION = "1.0"

OUTPUT_PROFILES = {
    "VP9 - .webm": {'codec': 'libvpx-vp9', 'container': '.webm', 'tooltip': "VP9 codec has decent compression."},
    "AV1 - .webm": {'codec': 'libaom-av1', 'container': '.webm', 'tooltip': "AV1 codec has the best compression. (Note: Not compatible with posting on 4chan)"},
    "H.264 - .mp4": {'codec': 'libx264', 'container': '.mp4', 'tooltip': "H.264 codec is widely supported, but offers less compression than VP9/AV1."},
}
DEFAULT_OUTPUT_PROFILE = "VP9 - .webm"

CRF_STATUS_COLORS = {
    "default": "#333333", "very_high": "#2ECC71", "high": "#1E8449",
    "medium": "#D4AC0D", "low": "#E67E22", "very_low": "#C0392B",
    "error": "red", "unknown": "grey", "info": "#00008B"
}

class ToolTip:
    def __init__(self, widget, text, position='default'):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.show_after_id = None
        self.position = position

    def schedule_showtip(self):
        self.cancel_showtip()
        self.show_after_id = self.widget.after(500, self.showtip)

    def showtip(self):
        self.show_after_id = None
        if self.tooltip_window or not self.text: return
        x, y, width, height = self.widget.winfo_rootx(), self.widget.winfo_rooty(), self.widget.winfo_width(), self.widget.winfo_height()
        tip_x = x + (width // 2 if self.position == 'center_bottom' else 20)
        tip_y = y + height + 5
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{int(tip_x)}+{int(tip_y)}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT, background="#ffffe0", relief=tk.SOLID, borderwidth=1, font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def cancel_showtip(self):
        if self.show_after_id:
            self.widget.after_cancel(self.show_after_id)
            self.show_after_id = None

    def hidetip(self):
        self.cancel_showtip()
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

log_file_name = "ImagesToVideoSlideshow.log"
log_file_path = Path(tempfile.gettempdir()) / log_file_name

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.info(f"Using log file location: {log_file_path}")

def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logging.critical(f"Unhandled exception occurred:\n{error_message}")
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            try: handler.flush()
            except Exception as flush_err: logging.error(f"Error flushing log handler: {flush_err}")
    user_message = (
        "A critical error occurred and the application needs to close.\n\n"
        f"Error details have been logged to:\n{log_file_path}\n\n"
        "Attempting to open the log file now..."
    )
    try:
        root_exists = False
        try:
            if 'app' in globals() and app.root and app.root.winfo_exists(): root_exists = True
        except Exception: root_exists = False
        parent = app.root if root_exists else None
        if not root_exists:
            temp_root = tk.Tk(); temp_root.withdraw()
            messagebox.showerror("Unhandled Exception", user_message, parent=temp_root)
            temp_root.destroy()
        else: messagebox.showerror("Unhandled Exception", user_message, parent=app.root)
    except Exception as mb_error:
        logging.error(f"Could not display the error messagebox: {mb_error}")
        print(f"CRITICAL ERROR: {user_message}\n(Could not show GUI message box: {mb_error})", file=sys.stderr)
    try:
        if log_file_path.exists():
            system = platform.system()
            if system == "Windows": os.startfile(log_file_path)
            elif system == "Darwin": subprocess.run(['open', str(log_file_path)], check=True)
            else: subprocess.run(['xdg-open', str(log_file_path)], check=True)
            logging.info(f"Attempted to open log file: {log_file_path}")
        else: logging.error(f"Log file not found, cannot open: {log_file_path}")
    except FileNotFoundError as fnf_error: logging.error(f"Error opening log file: command not found ({fnf_error})")
    except Exception as open_error: logging.error(f"Error opening log file '{log_file_path}': {open_error}")

class ImagesToVideoSlideshow:
    def __init__(self):
        self.is_loading = True
        self.ffmpeg_executable = self._find_ffmpeg_executable()
        if not self.ffmpeg_executable:
             logging.critical("FFmpeg executable not found. Application cannot continue.")
             sys.exit(1)
        self.progress_queue = queue.Queue()
        try: self.root = TkinterDnD.Tk()
        except Exception as e:
            logging.error(f"Error initializing TkinterDnD Tk: {e}")
            try:
                self.root = tk.Tk()
                logging.warning("Using fallback Tk implementation without drag and drop support")
            except Exception as tk_e:
                 logging.critical(f"CRITICAL ERROR: Could not initialize Tk: {tk_e}")
                 sys.exit(1)
        self.original_title = "ImagesToVideoSlideshow"
        self.root.title(self.original_title)
        try:
            icon_path_str = "icon.png"
            base_dir = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else (Path(__file__).parent if '__file__' in globals() else Path('.'))
            icon_path = base_dir / icon_path_str
            if not icon_path.exists(): icon_path = Path(".") / icon_path_str
            if icon_path.exists():
                photo = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, photo)
            else: logging.warning(f"Window icon '{icon_path_str}' not found relative to script/executable or CWD.")
        except tk.TclError as e: logging.warning(f"Could not load window icon '{icon_path_str}'. TclError: {e}")
        except NameError: logging.warning("Could not determine script path to find icon (NameError: __file__ not defined?).")
        except Exception as e: logging.warning(f"An unexpected error occurred loading window icon: {e}")
        self.time_per_image_ms = tk.StringVar(value="1.5")
        self.downscale_factor = tk.StringVar(value="1.0")
        self.quality_crf = tk.StringVar(value="36")
        self.downscale_enabled = tk.BooleanVar(value=True)
        self.output_profile = tk.StringVar(value=DEFAULT_OUTPUT_PROFILE)
        self.drag_data = {"item": None, "y": 0}
        self.widgets_to_disable = []
        self.treeview_bindings = {
             "<Double-Button-1>": self.open_selected_file, "<Button-3>": self.remove_on_right_click,
             "<ButtonPress-1>": self.on_drag_start, "<B1-Motion>": self.on_drag_motion,
             "<ButtonRelease-1>": self.on_drag_drop, "<Delete>": self.remove_selected_images,
         }
        self.last_add_directory = None
        self.setup_ui()
        self.quality_crf.trace_add("write", self.update_crf_status_label)
        self.output_profile.trace_add("write", self.update_crf_status_label)
        self.downscale_factor.trace_add("write", self._update_resolution_status_label)
        self.downscale_enabled.trace_add("write", self._update_resolution_status_label)
        self.update_crf_status_label()
        config_filename = "ImagesToVideoSlideshowSettings.json"
        self.config_file = Path(tempfile.gettempdir()) / config_filename
        self.output_file = None
        self.load_config()
        self.root.after_idle(self._update_resolution_status_label)
        self._set_initial_window_size()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.save_config()

    def _get_app_directory(self):
        """Determines the application's base directory."""
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # PyInstaller bundle
            return str(Path(sys.executable).parent.resolve())
        elif '__file__' in globals():
            # Regular script execution
            return str(Path(__file__).parent.resolve())
        else:
            # Fallback (e.g., interactive session)
            return str(Path('.').resolve())

    def _find_ffmpeg_executable(self):
        system = platform.system()
        exe_name = "ffmpeg.exe" if system == "Windows" else "ffmpeg"
        zip_name = "ffmpeg-windows.zip" if system == "Windows" else "ffmpeg-linux.zip"
        is_frozen = getattr(sys, 'frozen', False)
        base_path = None
        if is_frozen:
            logging.info("Running frozen, checking bundle for FFmpeg...")
            try: base_path = Path(sys._MEIPASS).resolve()
            except AttributeError:
                error_msg = "Running frozen but sys._MEIPASS is not defined."
                logging.error(error_msg); messagebox.showerror("Runtime Error", error_msg, parent=None); return None
            expected_exe_path = base_path / exe_name
            logging.info(f"  Looking for FFmpeg at: {expected_exe_path}")
            if expected_exe_path.is_file():
                logging.info(f"Found bundled FFmpeg: {expected_exe_path}")
                return str(expected_exe_path)
            else:
                error_msg = f"Bundled FFmpeg ('{exe_name}') not found at:\n{expected_exe_path}"
                logging.error(error_msg)
                try: logging.error(f"Contents of {base_path}: {os.listdir(base_path)}")
                except Exception as list_err: logging.error(f"Could not list contents of _MEIPASS: {list_err}")
                messagebox.showerror("Dependency Error", error_msg, parent=None); return None
        else:
            try: script_dir = Path(__file__).parent.resolve()
            except NameError: script_dir = Path('.').resolve(); logging.warning("__file__ not defined, using '.' as base.")
            base_path = script_dir
        expected_exe_path = base_path / exe_name
        expected_zip_path = base_path / zip_name
        if expected_exe_path.is_file(): logging.info(f"Found FFmpeg in script directory: {expected_exe_path}")
        elif expected_zip_path.is_file():
            logging.info(f"Found FFmpeg zip: {expected_zip_path}. Attempting extraction...")
            try:
                with zipfile.ZipFile(expected_zip_path, 'r') as zip_ref:
                    logging.info(f"  Zip contents: {zip_ref.namelist()}")
                    if exe_name not in zip_ref.namelist(): raise FileNotFoundError(f"'{exe_name}' not found inside '{zip_name}'.")
                    zip_ref.extractall(base_path)
                    logging.info(f"Successfully extracted to {base_path}.")
                if not expected_exe_path.is_file(): raise FileNotFoundError(f"Extraction successful, but '{exe_name}' not found at '{expected_exe_path}'.")
                logging.info(f"Using extracted FFmpeg: {expected_exe_path}")
            except Exception as e:
                error_msg = f"Failed to extract FFmpeg from '{expected_zip_path}'.\nReason: {e}\nDirectory: {base_path}"
                logging.error(error_msg); messagebox.showerror("Extraction Error", error_msg, parent=None); return None
        else:
             error_msg = f"FFmpeg executable ('{exe_name}') or archive ('{zip_name}') not found in script directory:\n{base_path}"
             logging.error(error_msg); messagebox.showerror("Dependency Error", error_msg, parent=None); return None
        if system == "Linux" and not is_frozen and not os.access(str(expected_exe_path), os.X_OK):
            logging.warning(f"'{exe_name}' lacks execute permissions. Attempting to set...")
            try: os.chmod(str(expected_exe_path), 0o755); logging.info("Execute permissions set.")
            except OSError as chmod_err:
                error_msg = f"Failed to set execute permissions for '{expected_exe_path}': {chmod_err}"
                logging.error(error_msg); messagebox.showerror("Permissions Error", error_msg, parent=None); return None
        return str(expected_exe_path)

    def _set_initial_window_size(self):
        self.root.update_idletasks()
        try:
            left_panel_width = self.settings_panel.winfo_reqwidth()
            left_panel_height = self.settings_panel.winfo_reqheight()
            tree_frame_req_height = self.tree_frame.winfo_reqheight()
            status_bar_height = self.status_version_frame.winfo_reqheight()
            min_width = max(900, left_panel_width + 250 + 40)
            min_height = max(600, left_panel_height + status_bar_height + 20)
            initial_width = max(min_width, left_panel_width + 900 + 40)
            effective_tree_height = max(tree_frame_req_height, 400)
            initial_height = max(min_height, max(left_panel_height, effective_tree_height) + status_bar_height + 20)
            self.root.geometry(f"{initial_width}x{initial_height}")
            self.root.minsize(min_width, min_height)
        except Exception as e:
            logging.warning(f"Warning: Could not dynamically calculate initial size: {e}")
            self.root.geometry("1600x720"); self.root.minsize(900, 600)

    def _create_button_with_tooltip(self, parent, text, command, tooltip_text, style='App.TButton', **grid_options):
        button = ttk.Button(parent, text=text, command=command, style=style)
        button.grid(**grid_options)
        self.create_tooltip(button, tooltip_text)
        self.widgets_to_disable.append(button)
        return button

    def _create_settings_row(self, parent, row, label_text, variable, tooltip_text, entry_width=8):
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky="w", padx=2, pady=3)
        entry = ttk.Entry(parent, textvariable=variable, width=entry_width)
        entry.grid(row=row, column=1, sticky="w", padx=(0, 5), pady=3)
        self.create_tooltip(entry, tooltip_text)
        self.widgets_to_disable.append(entry)
        return entry

    def setup_ui(self):
        self.root.grid_columnconfigure(0, weight=0); self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=0); self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1); self.main_frame.grid_rowconfigure(1, weight=0)
        self.main_frame.bind("<Button-1>", self._clear_entry_focus)
        self.settings_panel = ttk.Frame(self.main_frame, padding=(10, 10))
        self.settings_panel.grid(row=0, column=0, sticky="nsw")
        self.settings_panel.grid_rowconfigure(2, weight=0)
        self.settings_panel.bind("<Button-1>", self._clear_entry_focus)
        self.preset_frame = ttk.LabelFrame(self.settings_panel, text="Presets", padding=(10,5))
        self.preset_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        self.preset_frame.bind("<Button-1>", self._clear_entry_focus)
        self.preset_frame.columnconfigure((0, 1), weight=1)
        self._create_button_with_tooltip(self.preset_frame, "Small WebM", self.apply_low_quality_webm_preset, "Preset for small .webm files (VP9 codec).", row=0, column=0, sticky='ew', padx=2, pady=2)
        self._create_button_with_tooltip(self.preset_frame, "Quality WebM", self.apply_quality_av1_webm_preset, "Preset for higher quality .webm files (AV1 codec - Slow encoding).", row=0, column=1, sticky='ew', padx=2, pady=2)
        self.settings_frame = ttk.LabelFrame(self.settings_panel, text="Output Settings", padding=(10, 5))
        self.settings_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.settings_frame.bind("<Button-1>", self._clear_entry_focus)
        self.settings_frame.columnconfigure(1, weight=1)
        current_row = 0
        self._create_settings_row(self.settings_frame, current_row, "Delay (s):", self.time_per_image_ms, "Seconds each image is displayed.")
        current_row += 1
        ttk.Label(self.settings_frame, text="Format/Codec:").grid(row=current_row, column=0, sticky="w", padx=2, pady=3)
        profile_combo = ttk.Combobox(self.settings_frame, textvariable=self.output_profile, values=list(OUTPUT_PROFILES.keys()), state='readonly', width=20)
        profile_combo.grid(row=current_row, column=1, sticky="ew", padx=(0, 5), pady=3)
        profile_tooltips = {name: data['tooltip'] for name, data in OUTPUT_PROFILES.items()}
        self.profile_tooltip = self.create_tooltip(profile_combo, profile_tooltips.get(self.output_profile.get(), "Select profile."))
        def update_profile_tooltip(*args):
            tooltip_text = profile_tooltips.get(self.output_profile.get(), "Select profile.")
            if hasattr(self, 'profile_tooltip') and self.profile_tooltip: self.profile_tooltip.text = tooltip_text
        self.output_profile.trace_add("write", update_profile_tooltip)
        self.widgets_to_disable.append(profile_combo)
        current_row += 1
        self._create_settings_row(self.settings_frame, current_row, "Quality (CRF):", self.quality_crf, "Constant Rate Factor.\nLower = Better Quality, Larger File.\nVP9/AV1 (0-63), H.264 (0-51).")
        current_row += 1
        self.crf_status_label = ttk.Label(self.settings_frame, text="", width=35, foreground=CRF_STATUS_COLORS["default"], anchor='w')
        self.crf_status_label.grid(row=current_row, column=0, columnspan=2, sticky="ew", padx=(5, 5), pady=(0, 3))
        self.create_tooltip(self.crf_status_label, "Expected quality/size trade-off.")
        current_row += 1
        downscale_frame = ttk.Frame(self.settings_frame)
        downscale_frame.grid(row=current_row, column=0, columnspan=2, sticky="w")
        self.rescale_checkbox = ttk.Checkbutton(downscale_frame, text="Downscale Factor:", variable=self.downscale_enabled, command=self._toggle_downscale_entry_state)
        self.rescale_checkbox.pack(side=tk.LEFT, padx=(2,1), pady=3)
        downscale_tooltip_text = "Downscale images by this factor. Uncheck to use original dimensions. \n1.0 = original size, 0.5 = half size.\nMay enhance image clarity when working with high CRF values."
        self.create_tooltip(self.rescale_checkbox, downscale_tooltip_text)
        self.widgets_to_disable.append(self.rescale_checkbox)
        self.multiplier_entry = ttk.Entry(downscale_frame, textvariable=self.downscale_factor, width=8)
        self.multiplier_entry.pack(side=tk.LEFT, padx=(0, 5), pady=3)
        self.create_tooltip(self.multiplier_entry, downscale_tooltip_text)
        self.multiplier_entry.bind("<FocusOut>", self._validate_downscale_factor)
        self.widgets_to_disable.append(self.multiplier_entry)
        current_row += 1
        self.resolution_status_label = ttk.Label(self.settings_frame, text="", width=35, foreground=CRF_STATUS_COLORS["default"], anchor='w')
        self.resolution_status_label.grid(row=current_row, column=0, columnspan=2, sticky="ew", padx=(5, 5), pady=(0, 3))
        self.create_tooltip(self.resolution_status_label, "Original and calculated output resolution.")
        current_row += 1
        self._toggle_downscale_entry_state()
        self.control_frame = ttk.LabelFrame(self.settings_panel, text="Image List Actions", padding=(10, 5))
        self.control_frame.grid(row=2, column=0, sticky="ew")
        self.control_frame.bind("<Button-1>", self._clear_entry_focus)
        self.control_frame.columnconfigure((0, 1), weight=1)
        button_style = ttk.Style(); button_style.configure('App.TButton', padding=(8, 4))
        btn_options = {'sticky': 'ew', 'padx': 2}
        default_pady, section_pady = 2, (10, 2)
        self._create_button_with_tooltip(self.control_frame, "Add Images", self.add_images, "Select image files.", row=0, column=0, pady=default_pady, **btn_options)
        self._create_button_with_tooltip(self.control_frame, "Add Folder", self.add_folder, "Add images from a folder.", row=0, column=1, pady=default_pady, **btn_options)
        self._create_button_with_tooltip(self.control_frame, "Remove Selected", self.remove_selected_images, "Remove selected images (Delete key).", row=1, column=0, pady=section_pady, **btn_options)
        self._create_button_with_tooltip(self.control_frame, "Clear All", self.clear_all_files, "Remove all images.", row=1, column=1, pady=section_pady, **btn_options)
        self.sort_button = self._create_button_with_tooltip(self.control_frame, "Sort A-Z", self.sort_files_by_name, "Sort list by filename.", row=2, column=0, pady=section_pady, **btn_options)
        self.randomize_button = self._create_button_with_tooltip(self.control_frame, "Randomize", self.randomize_files, "Shuffle image order.", row=2, column=1, pady=section_pady, **btn_options)
        self._create_button_with_tooltip(self.control_frame, "Create Slideshow", self.start_slideshow, "Start video creation.", row=3, column=0, columnspan=2, pady=(15, 2), **btn_options)
        self.tree_frame = ttk.Frame(self.main_frame)
        self.tree_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=(10, 5))
        self.tree_frame.grid_columnconfigure(0, weight=1); self.tree_frame.grid_rowconfigure(0, weight=1)
        self.tree_frame.bind("<Button-1>", self._clear_entry_focus)
        self.file_tree = ttk.Treeview(self.tree_frame, columns=("icon", "filename", "path"), show="headings", selectmode='extended')
        self.file_tree.bind("<Button-1>", self._clear_entry_focus)
        style = ttk.Style()
        try:
            self.root.update_idletasks()
            actual_font = style.lookup("Treeview", "font")
            tree_font = tkfont.Font(font=actual_font) if actual_font else tkfont.nametofont("TkDefaultFont")
            final_row_height = max(20, int(tree_font.metrics("linespace") * 1.2))
        except Exception as e: logging.warning(f"Error calculating Treeview row height: {e}. Using default 25."); final_row_height = 25
        style.configure("Treeview", rowheight=final_row_height)
        self.file_tree.heading("icon", text=""); self.file_tree.column("icon", anchor="center", width=40, stretch=False)
        self.file_tree.heading("filename", text="File Name"); self.file_tree.column("filename", anchor="w", width=300)
        self.file_tree.heading("path", text="Full Path"); self.file_tree.column("path", anchor="w", width=400)
        self.file_tree.grid(row=0, column=0, sticky="nsew")
        tree_tooltip_text = "List of images.\nDrag & drop to reorder.\nRight-click to remove.\nCtrl+A to select all.\nDouble-click to open."
        if not isinstance(self.root, TkinterDnD.Tk): tree_tooltip_text = tree_tooltip_text.replace("Drag & drop to reorder.\n", "")
        self.create_tooltip(self.tree_frame, tree_tooltip_text, position='center_bottom')
        scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.file_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_tree.configure(yscrollcommand=scrollbar.set)
        self.file_tree.tag_configure('disabled', foreground='grey')
        self.status_version_frame = ttk.Frame(self.main_frame)
        self.status_version_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 5))
        self.status_version_frame.columnconfigure(0, weight=1)
        self.status_version_frame.bind("<Button-1>", self._clear_entry_focus)
        initial_status = "Drag & drop files/folders or use Add buttons." if isinstance(self.root, TkinterDnD.Tk) else "Use Add buttons."
        self.status_message = ttk.Label(self.status_version_frame, text=initial_status, foreground=CRF_STATUS_COLORS["default"])
        self.status_message.grid(row=0, column=0, sticky="w", padx=5)
        version_label = ttk.Label(self.status_version_frame, text=f"v{VERSION}", foreground='#666666')
        version_label.grid(row=0, column=1, sticky="e", padx=5)
        if isinstance(self.root, TkinterDnD.Tk):
            self.file_tree.drop_target_register(DND_FILES)
            self.file_tree.dnd_bind('<<Drop>>', self.handle_drop)
        self.root.bind("<Control-a>", self.select_all_files)
        self._set_ui_state(True)

    def _clear_entry_focus(self, event):
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry)) and event.widget != focused and not isinstance(event.widget, ttk.Scrollbar):
            self.main_frame.focus_set()

    def create_tooltip(self, widget, text, position='default'):
        tooltip = ToolTip(widget, text, position=position)
        widget.bind("<Enter>", lambda e: tooltip.schedule_showtip())
        widget.bind("<Leave>", lambda e: tooltip.hidetip())
        return tooltip

    def add_images(self):
        files = filedialog.askopenfilenames(
            initialdir=self.last_add_directory,
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.gif"), ("All files", "*.*")]
        )
        if files:
            try:
                self.last_add_directory = str(Path(files[0]).parent)
                self.save_config()
            except Exception as e:
                logging.warning(f"Could not update last_add_directory from selected files: {e}")

            count = self.add_files_to_tree(files)
            self.status_message.config(text=f"Added {count} image(s)." if count > 0 else "No new valid images added.")

    def add_folder(self):
        folder = filedialog.askdirectory(initialdir=self.last_add_directory)
        if not folder: return

        self.last_add_directory = folder
        self.save_config()

        images = []
        img_ext = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
        for root, _, filenames in os.walk(folder):
            for name in filenames:
                if name.lower().endswith(img_ext): images.append(os.path.join(root, name))
        if images:
            count = self.add_files_to_tree(images)
            self.status_message.config(text=f"Added {count} image(s) from folder." if count > 0 else "No new valid images added from folder.")
        else:
             messagebox.showinfo("Info", f"No image files found in '{folder}'.")
             self.status_message.config(text=f"No images found in folder: {os.path.basename(folder)}")

    def add_files_to_tree(self, files):
        current_paths = {self.file_tree.item(item, "values")[2] for item in self.file_tree.get_children()}
        added_count = 0
        img_ext = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
        for file in files:
            norm_path = os.path.normpath(file)
            if norm_path not in current_paths and norm_path.lower().endswith(img_ext):
                self.file_tree.insert("", "end", values=("🖼️", os.path.basename(norm_path), norm_path))
                current_paths.add(norm_path)
                added_count += 1
        if added_count > 0: self._update_resolution_status_label()
        return added_count

    def _delete_tree_items(self, items_to_delete, confirm_message):
        count = len(items_to_delete)
        if not items_to_delete: return False
        if messagebox.askyesno("Confirm", confirm_message, parent=self.root):
            for item in items_to_delete: self.file_tree.delete(item)
            self.status_message.config(text=f"Removed {count} item(s).")
            self._update_resolution_status_label()
            return True
        return False

    def remove_selected_images(self, event=None):
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry)) and event: return
        selected = self.file_tree.selection()
        count = len(selected)
        if not selected:
             if event is None: messagebox.showinfo("Info", "No images selected.", parent=self.root)
             return
        name = self.file_tree.item(selected[0], "values")[1]
        msg = f"Remove '{name}'?" if count == 1 else f"Remove {count} selected items?"
        self._delete_tree_items(selected, msg)

    def remove_on_right_click(self, event):
        item_id = self.file_tree.identify_row(event.y)
        if not item_id: return
        selected = self.file_tree.selection()
        to_delete, msg = [], ""
        name = self.file_tree.item(item_id, "values")[1]
        if item_id in selected:
            to_delete = list(selected)
            count = len(to_delete)
            msg = f"Remove '{name}'?" if count == 1 else f"Remove {count} selected items?"
        else:
            to_delete = [item_id]
            msg = f"Remove '{name}'?"
        self._delete_tree_items(to_delete, msg)

    def handle_drop(self, event):
        raw_paths = self.parse_drop_data(event.data)
        to_add, folders_scanned = [], 0
        img_ext = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
        for path_str in raw_paths:
            path_obj = Path(path_str)
            if path_obj.is_file() and path_str.lower().endswith(img_ext): to_add.append(str(path_obj))
            elif path_obj.is_dir():
                folders_scanned += 1
                logging.info(f"Scanning dropped folder: {path_obj}")
                for root, _, filenames in os.walk(path_obj):
                    for name in filenames:
                         if name.lower().endswith(img_ext): to_add.append(os.path.join(root, name))
        if to_add:
            count = self.add_files_to_tree(to_add)
            folder_txt = f" from {folders_scanned} folder(s)" if folders_scanned > 0 else ""
            status = f"Added {count} image(s) via drag & drop{folder_txt}." if count > 0 else f"No new valid images via drag & drop{folder_txt}."
            self.status_message.config(text=status)
        else:
            logging.info("No valid image files or folders found in drop data.")
            self.status_message.config(text="Drag & drop: No valid images or folders found.")

    def parse_drop_data(self, data):
        files = []
        if '{' in data and '}' in data:
            parts = data.split('} {')
            for part in parts:
                 cleaned = part.strip().strip('{}')
                 if cleaned: files.append(cleaned)
        else: files = [p.strip() for p in data.split() if p.strip()]
        return [path.strip('"') for path in files]

    def select_all_files(self, event):
        if self.main_frame.winfo_viewable():
            items = self.file_tree.get_children()
            if items: self.file_tree.selection_set(items)
            return "break"

    def _get_first_image_dimensions(self):
        items = self.file_tree.get_children()
        if not items: return None, None
        path = self.file_tree.item(items[0], "values")[2]
        try:
            img = cv2.imread(path)
            if img is None: raise ValueError(f"Could not read: {path}")
            h, w = img.shape[:2]
            return w, h
        except Exception as e:
            logging.error(f"Error reading dimensions from {path}: {e}")
            messagebox.showerror("Error", f"Error reading first image:\n{e}", parent=self.root)
            return None, None

    def _validate_and_get_settings(self):
        settings = {}
        try:
            time_sec = float(self.time_per_image_ms.get())
            if time_sec <= 0: raise ValueError("Delay must be positive.")
            settings['milliseconds_per_image'] = int(time_sec * 1000)
            profile_str = self.output_profile.get()
            codec, container = self._get_codec_container_from_profile(profile_str)
            if not codec or not container: raise ValueError(f"Invalid profile: {profile_str}")
            settings.update({'codec': codec, 'container': container, 'profile_str': profile_str})
            first_w, first_h = self._get_first_image_dimensions()
            if first_w is None: self.status_message.config(text="Error reading first image."); return None
            settings['target_width'], settings['target_height'] = first_w, first_h
            if self.downscale_enabled.get():
                factor = float(self.downscale_factor.get())
                if not (0 < factor <= 1.0): raise ValueError("Downscale factor must be > 0 and <= 1.0.")
                settings['target_width'] = max(1, int(first_w * factor))
                settings['target_height'] = max(1, int(first_h * factor))
                logging.info(f"Target (Downscaled x{factor}): {settings['target_width']}x{settings['target_height']}")
            else: logging.info(f"Target (Original): {first_w}x{first_h}")
            crf = int(self.quality_crf.get())
            codec_ranges = {'libvpx-vp9': (0, 63, 'VP9/AV1'), 'libaom-av1': (0, 63, 'VP9/AV1'), 'libx264': (0, 51, 'H.264')}
            if codec in codec_ranges:
                min_crf, max_crf, name = codec_ranges[codec]
                if not (min_crf <= crf <= max_crf): raise ValueError(f"Invalid CRF. For {name}, use {min_crf}-{max_crf}.")
            else: raise ValueError(f"Unsupported codec for CRF validation: {codec}")
            settings['crf'] = crf
            return settings
        except ValueError as e: messagebox.showerror("Error", str(e), parent=self.root); return None
        except Exception as e: logging.error(f"Unexpected validation error: {e}"); messagebox.showerror("Error", f"Unexpected validation error: {e}", parent=self.root); return None

    def _escape_path_for_concat(self, path_str):
        replacement = "'\\''"
        escaped_inner = path_str.replace("'", replacement)
        return f"'{escaped_inner}'"

    def start_slideshow(self):
        items = self.file_tree.get_children()
        if not items: messagebox.showerror("Error", "Please add images first."); return
        if hasattr(self, 'encoding_thread') and self.encoding_thread and self.encoding_thread.is_alive():
             logging.warning("Processing already in progress."); self.status_message.config(text="Processing..."); return
        validated_settings = self._validate_and_get_settings()
        if not validated_settings: return
        self._set_ui_state(False)
        self.root.title(f"{self.original_title} - Processing...")
        self.status_message.config(text="Validating settings..."); self.root.update_idletasks()
        self.current_milliseconds_per_image = validated_settings['milliseconds_per_image']
        self.current_active_codec = validated_settings['codec']
        self.current_active_container = validated_settings['container']
        self.final_output_width = validated_settings['target_width']
        self.final_output_height = validated_settings['target_height']
        self.current_quality_crf = validated_settings['crf']
        self.input_files = [self.file_tree.item(item, "values")[2] for item in items]
        if not self.select_output_file():
             self.status_message.config(text="Output selection cancelled.")
             self._set_ui_state(True); self.root.title(self.original_title)
             return
        else: self.save_config()
        self.status_message.config(text="Preparing FFmpeg..."); self.root.update_idletasks()
        try:
            ffmpeg_cmd, self.concat_file_path = self._build_ffmpeg_concat_command()
            self.status_message.config(text="Starting FFmpeg...")
            self.root.update_idletasks()
            logging.info("Starting video encoding thread...")
            self.encoding_result_queue = queue.Queue()
            while not self.progress_queue.empty():
                 try: self.progress_queue.get_nowait()
                 except queue.Empty: break
            self.encoding_thread = threading.Thread(target=self._run_ffmpeg_thread, args=(ffmpeg_cmd, self.encoding_result_queue, self.progress_queue), daemon=True)
            self.encoding_thread.start()
            self.root.after(100, self.check_queues)
        except Exception as e:
            logging.exception("Failed to prepare/start FFmpeg:")
            messagebox.showerror("Error", f"Failed to prepare FFmpeg command: {e}", parent=self.root)
            self.status_message.config(text="Error preparing FFmpeg.")
            self._set_ui_state(True); self.root.title(self.original_title)
            if hasattr(self, 'concat_file_path') and self.concat_file_path and os.path.exists(self.concat_file_path):
                 try: os.remove(self.concat_file_path); self.concat_file_path = None
                 except OSError as clean_err: logging.warning(f"Could not remove temp file {self.concat_file_path}: {clean_err}")

    def _build_ffmpeg_concat_command(self):
        concat_path = ""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as f:
            concat_path = f.name
            logging.info(f"Generating concat file: {concat_path}")
            duration_sec = self.current_milliseconds_per_image / 1000.0
            last_file = None
            for img_path in self.input_files:
                if os.path.exists(img_path):
                    f.write(f"file {self._escape_path_for_concat(img_path)}\n")
                    f.write(f"duration {duration_sec}\n")
                    last_file = img_path
                else: logging.warning(f"Image file not found, skipping: {img_path}")
            if last_file: f.write(f"file {self._escape_path_for_concat(last_file)}\n")
        W, H = self.final_output_width, self.final_output_height
        vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,format=pix_fmts=yuv420p"
        cmd = [
            self.ffmpeg_executable, '-y', '-f', 'concat', '-safe', '0', '-i', concat_path,
            '-vf', vf, '-c:v', self.current_active_codec, '-crf', str(self.current_quality_crf),
            '-progress', '-',
        ]
        codec = self.current_active_codec
        if codec == 'libvpx-vp9': cmd.extend(['-speed', '1', '-tile-columns', '2', '-auto-alt-ref', '1', '-lag-in-frames', '25'])
        elif codec == 'libx264': cmd.extend(['-preset', 'medium'])
        elif codec == 'libaom-av1': cmd.extend(['-cpu-used', '4', '-row-mt', '1', '-tile-columns', '2', '-tile-rows', '2'])
        cmd.append(self.output_file)
        return cmd, concat_path

    def check_queues(self):
        latest_progress_line = None
        try:
            while True: latest_progress_line = self.progress_queue.get_nowait().strip()
        except queue.Empty: pass
        except Exception as e: logging.error(f"Error reading progress queue: {e}")
        if latest_progress_line:
            cleaned_line = " ".join(latest_progress_line.split()).replace("= ", "=")
            self.status_message.config(text=f"FFmpeg: {cleaned_line}")
        try:
            success, message = self.encoding_result_queue.get_nowait()
            self._set_ui_state(True); self.root.title(self.original_title)
            if success:
                logging.info("Slideshow created successfully!")
                messagebox.showinfo("Success", f"Slideshow created:\n{message}", parent=self.root)
            else:
                logging.error(f"FFmpeg error: {message}")
                error_details = f"Error creating video (FFmpeg failed).\nCodec: {self.current_active_codec}\n\nDetails: {message}\n\nCheck log."
                messagebox.showerror("Error", error_details, parent=self.root)
                self.status_message.config(text="Error creating video. Check log.")
            self.cleanup(); return
        except queue.Empty: self.root.after(150, self.check_queues)
        except Exception as e:
             logging.exception("Error checking result queue:")
             self._set_ui_state(True); self.root.title(self.original_title)
             messagebox.showerror("Error", f"Error getting encoding result: {e}", parent=self.root)
             self.status_message.config(text="Error during final step.")
             self.cleanup()

    def _run_ffmpeg_thread(self, ffmpeg_cmd, result_queue, progress_queue):
        process, exit_code = None, -1; stderr_lines = []
        try:
            cmd_str = ' '.join(shlex.quote(str(s)) for s in ffmpeg_cmd)
            logging.info(f"Executing FFmpeg:\n  {cmd_str}")
            flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" and getattr(sys, 'frozen', False) else 0
            if flags: logging.info("Using CREATE_NO_WINDOW for Popen.")
            process = subprocess.Popen(ffmpeg_cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                      text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=flags)
            for line in iter(process.stderr.readline, ''):
                 line_strip = line.strip()
                 logging.info(f"FFMPEG: {line_strip}")
                 stderr_lines.append(line_strip)
                 if line_strip.startswith('frame='): progress_queue.put(line_strip)
            process.stderr.close(); process.wait()
            exit_code = process.returncode
            if exit_code != 0:
                error_context = "\n".join(stderr_lines[-20:])
                raise subprocess.CalledProcessError(exit_code, ffmpeg_cmd, output=None, stderr=error_context)
            result_queue.put((True, ffmpeg_cmd[-1]))
        except subprocess.CalledProcessError as e:
             cmd_disp = ' '.join(map(shlex.quote, e.cmd))
             err_log = f"FFmpeg failed!\nCode: {e.returncode}\nCmd: {cmd_disp}\nOutput:\n{e.stderr}"
             logging.error(err_log); err_ui = f"Return Code: {e.returncode}\nCheck log for command/output."
             result_queue.put((False, err_ui))
        except FileNotFoundError:
             msg = f"FFmpeg not runnable.\nPath: '{self.ffmpeg_executable}'\nEnsure it exists and has execute permissions."
             logging.error(msg); result_queue.put((False, msg))
        except Exception as e:
             logging.exception("Error during video creation thread:")
             result_queue.put((False, f"Unexpected error in encoding thread: {e}"))
        finally:
            if process and process.poll() is None:
                logging.warning("Terminating lingering FFmpeg process.")
                try: process.terminate(); process.wait(timeout=2)
                except Exception as term_err:
                    logging.error(f"Error terminating FFmpeg: {term_err}")
                    try: process.kill(); logging.warning("FFmpeg killed.")
                    except Exception as kill_err: logging.error(f"Error killing FFmpeg: {kill_err}")

    def cleanup(self):
        self._set_ui_state(True); self.root.title(self.original_title)
        if hasattr(self, 'concat_file_path') and self.concat_file_path:
             try:
                  if os.path.exists(self.concat_file_path):
                       logging.info(f"Cleaning temp file: {self.concat_file_path}")
                       os.remove(self.concat_file_path)
             except OSError as e: logging.warning(f"Error cleaning temp file {self.concat_file_path}: {e}")
             finally: self.concat_file_path = None
        self.input_files = []
        self.encoding_thread = None
        current_status = self.status_message.cget("text")
        if "successfully" not in current_status and "Error" not in current_status and "FFmpeg:" not in current_status:
             initial = "Ready. Drag & drop or use Add buttons." if isinstance(self.root, TkinterDnD.Tk) else "Ready. Use Add buttons."
             self.status_message.config(text=initial)

    def load_config(self):
        config_path = Path(self.config_file); config_loaded = False
        default_app_dir = self._get_app_directory()
        # Update defaults to match "Small WebM" preset
        defaults = {'output_profile': "VP9 - .webm", 'quality_crf': "36", 'time_per_image_sec': "1.5",
                    'downscale_enabled': True, 'downscale_factor': "0.5", 'output_file_hint': None,
                    'last_add_directory': default_app_dir}
        config = defaults.copy()
        if config_path.exists():
            try:
                with config_path.open('r') as f: loaded_config = json.load(f)
                config.update(loaded_config)
                profile_val = config['output_profile']
                if profile_val not in OUTPUT_PROFILES:
                    old_to_new = {"Compatible (MP4 / H.264)": "H.264 - .mp4", "Balanced (WebM / VP9)": "VP9 - .webm",
                                  "Smallest File (WebM / AV1 - Slow Encode)": "AV1 - .webm", ".mp4 - H.264": "H.264 - .mp4",
                                  ".webm - VP9": "VP9 - .webm", ".webm - AV1": "AV1 - .webm", "MP4 (H.264 - Compatible)": "H.264 - .mp4",
                                  "WebM (VP9 - Efficient)": "VP9 - .webm", "WebM (AV1 - Max Efficiency)": "AV1 - .webm"}
                    new_profile = old_to_new.get(profile_val)
                    if new_profile: logging.info(f"Mapping old profile '{profile_val}' to '{new_profile}'."); config['output_profile'] = new_profile
                    else: logging.warning(f"Unrecognized profile '{profile_val}' in config. Using default."); config['output_profile'] = defaults['output_profile']
                try:
                    factor = float(config['downscale_factor'])
                    if not (0 < factor <= 1.0): raise ValueError()
                    config['downscale_factor'] = str(factor)
                except (ValueError, TypeError):
                    logging.warning(f"Invalid downscale_factor '{config['downscale_factor']}'. Using default.")
                    config['downscale_factor'] = defaults['downscale_factor']
                if not isinstance(config['downscale_enabled'], bool): config['downscale_enabled'] = defaults['downscale_enabled']
                config_loaded = True

                # Validate last_add_directory
                loaded_add_dir = config.get('last_add_directory')
                if loaded_add_dir and not Path(loaded_add_dir).is_dir():
                    # If loaded dir is invalid, use the *current* default (Small WebM's factor/enabled)
                    logging.warning(f"Invalid last_add_directory '{loaded_add_dir}' found in config. Resetting to default: {default_app_dir}")
                    config['last_add_directory'] = default_app_dir
                    # Ensure other defaults aren't overridden if only this one is bad
                    for key, value in defaults.items():
                        if key not in config: config[key] = value
                elif not loaded_add_dir: # Handle if key is missing entirely but file exists
                     config['last_add_directory'] = default_app_dir

            except (json.JSONDecodeError, Exception) as e:
                logging.warning(f"Error loading '{config_path}': {e}. Using defaults.")
                # Ensure we use the correct defaults defined above
                config = defaults.copy()
        else:
             logging.info(f"Config file '{config_path}' not found. Using default settings (Small WebM preset).")
             config = defaults.copy() # Explicitly use defaults if file doesn't exist

        self.output_file = config.get('output_file_hint') # Use .get() for safety
        self.last_add_directory = config.get('last_add_directory', default_app_dir) # Use .get() with fallback
        self.output_profile.set(config.get('output_profile', defaults['output_profile']))
        self.quality_crf.set(str(config.get('quality_crf', defaults['quality_crf'])))
        self.time_per_image_ms.set(str(config.get('time_per_image_sec', defaults['time_per_image_sec'])))
        self.downscale_enabled.set(config.get('downscale_enabled', defaults['downscale_enabled']))
        self.downscale_factor.set(str(config.get('downscale_factor', defaults['downscale_factor'])))

        def finalize_load():
             # This call is now redundant here because _apply_preset (called by presets)
             # and the explicit setting of variables above will trigger necessary updates via traces.
             # However, _toggle_downscale_entry_state is still needed to set the initial state based on loaded config.
             self._toggle_downscale_entry_state() # Set initial state correctly
             self.update_crf_status_label()
             self._update_resolution_status_label()
             status = "Settings loaded." if config_loaded else "Using default settings (Small WebM)."
             if not self.status_message.cget("text").startswith("FFmpeg:"): self.status_message.config(text=status)
             self.is_loading = False
        self.root.after_idle(finalize_load)

    def save_config(self):
        config = {'output_file_hint': self.output_file or None, 'time_per_image_sec': self.time_per_image_ms.get(),
                  'downscale_factor': self.downscale_factor.get(), 'quality_crf': self.quality_crf.get(),
                  'output_profile': self.output_profile.get(), 'downscale_enabled': self.downscale_enabled.get(),
                  'last_add_directory': self.last_add_directory}
        try:
            with open(self.config_file, 'w') as f: json.dump(config, f, indent=4)
        except Exception as e: logging.warning(f"Could not save config '{self.config_file}': {e}")

    def select_output_file(self):
        container = self.current_active_container
        codec_map = {'libx264': 'h264', 'libvpx-vp9': 'vp9', 'libaom-av1': 'av1'}
        codec_short = codec_map.get(self.current_active_codec, 'video')
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        suggested = f"slideshow_{ts}_{codec_short}{container}"
        filetypes = [(f"{container[1:].upper()} Video", f"*{container}"), ("All files", "*.*")]

        # Determine initial directory for saving
        initial_dir = None
        if self.output_file: # Check if we have a hint from previous save or config
            try:
                last_dir = Path(self.output_file).parent
                if last_dir.is_dir():
                    initial_dir = str(last_dir)
                else:
                     # Log if the hint directory is invalid, but don't make it an error
                     logging.warning(f"Saved output directory hint '{last_dir}' not found or invalid.")
            except Exception as e:
                logging.warning(f"Error processing output_file hint '{self.output_file}': {e}")

        if initial_dir is None: # If hint was missing, invalid, or caused error, use app dir
            initial_dir = self._get_app_directory()

        # Final check - this shouldn't really fail as _get_app_directory has fallbacks
        if not initial_dir or not Path(initial_dir).is_dir():
            logging.error(f"Critical: Could not determine a valid initial directory ('{initial_dir}'). Falling back to home directory.")
            initial_dir = str(Path.home()) # Ultimate fallback

        # Log the final chosen directory before opening the dialog
        logging.info(f"Opening save dialog with initial directory: {initial_dir}")

        file_path = filedialog.asksaveasfilename(parent=self.root, initialdir=initial_dir, initialfile=suggested, defaultextension=container, filetypes=filetypes)
        if file_path:
            root, _ = os.path.splitext(file_path)
            self.output_file = root + container if not file_path.lower().endswith(container) else file_path
            self.status_message.config(text=f"Output: {os.path.basename(self.output_file)}")
            # Config saving is handled in start_slideshow after this returns True
            return True
        else:
            self.status_message.config(text="Output selection cancelled.")
            return False

    def run(self): self.root.mainloop()

    def randomize_files(self):
        items = list(self.file_tree.get_children())
        if items:
            random.shuffle(items)
            for i, item_id in enumerate(items): self.file_tree.move(item_id, '', i)
            self.status_message.config(text="List randomized.")
            self._update_resolution_status_label()

    def sort_files_by_name(self):
        items = self.file_tree.get_children()
        if items:
            items_data = [(self.file_tree.item(item_id, 'values')[1].lower(), item_id) for item_id in items]
            items_data.sort()
            for i, (_, item_id) in enumerate(items_data): self.file_tree.move(item_id, '', i)
            self.status_message.config(text="List sorted by filename.")
            self._update_resolution_status_label()

    def on_drag_start(self, event):
        if item := self.file_tree.identify_row(event.y):
            self.drag_data["item"] = item; self.drag_data["y"] = event.y
            self.root.config(cursor="hand2")

    def on_drag_motion(self, event):
        if not self.drag_data["item"]: return
        if target := self.file_tree.identify_row(event.y):
             if target != self.drag_data["item"]: self.file_tree.move(self.drag_data["item"], '', self.file_tree.index(target))

    def on_drag_drop(self, event):
        if self.drag_data["item"]:
            self.status_message.config(text="Item moved.")
            self._update_resolution_status_label()
        self.drag_data = {"item": None, "y": 0}; self.root.config(cursor="")

    def clear_all_files(self):
        if children := self.file_tree.get_children():
            self._delete_tree_items(children, f"Remove all {len(children)} files?")

    def open_selected_file(self, event):
        item_id = self.file_tree.identify_row(event.y)
        if not item_id: return
        try:
            file_path = self.file_tree.item(item_id, 'values')[2]
            filename = self.file_tree.item(item_id, 'values')[1]
            if not os.path.isfile(file_path): raise FileNotFoundError(f"File not found:\n{file_path}")
            self.status_message.config(text=f"Opening '{filename}'..."); self.root.update_idletasks()
            system = platform.system()
            try:
                if system == "Windows": os.startfile(file_path)
                elif system == "Darwin": subprocess.run(['open', file_path], check=True)
                else: subprocess.run(['xdg-open', file_path], check=True)
                self.root.after(2000, lambda: self.status_message.config(text="Ready.") if "Opening" in self.status_message.cget("text") else None)
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                cmd_name = 'startfile' if system=='Windows' else ('open' if system=='Darwin' else 'xdg-open')
                messagebox.showerror("Error", f"Failed to open file using '{cmd_name}':\n{e}", parent=self.root)
                self.status_message.config(text="Error opening file.")
        except (IndexError, FileNotFoundError) as e:
             logging.error(f"Error accessing/finding file for item {item_id}: {e}")
             messagebox.showerror("Error", str(e), parent=self.root)
             self.status_message.config(text="Error getting/finding file.")
        except Exception as e:
             logging.exception(f"Unexpected error opening file:")
             messagebox.showerror("Error", f"An unexpected error occurred:\n{e}", parent=self.root)
             self.status_message.config(text="Error opening file.")

    def _validate_downscale_factor(self, event=None):
        try:
            factor = float(self.downscale_factor.get())
            if factor > 1.0: self.downscale_factor.set("1.0")
        except ValueError: pass

    def _toggle_downscale_entry_state(self):
        overall_state = self.rescale_checkbox.cget('state')
        if overall_state != 'disabled' and self.downscale_enabled.get(): state = 'normal'
        else: state = 'disabled'
        if hasattr(self, 'multiplier_entry'): self.multiplier_entry.config(state=state)

    def update_crf_status_label(self, *args):
        if not hasattr(self, 'crf_status_label') or not self.crf_status_label.winfo_exists(): return
        status, color = "", CRF_STATUS_COLORS["default"]
        codec, _ = self._get_codec_container_from_profile()
        try:
            crf = int(self.quality_crf.get())
            ranges = {
                "libvpx-vp9": [(0, 63), (15, "Very High Quality / Large File"), (30, "High Quality / Med-Large File"), (45, "Medium Quality / Medium File"), (55, "Low Quality / Small File"), (63, "Very Low Quality / Very Small File")],
                "libaom-av1": [(0, 63), (15, "Very High Quality / Large File"), (30, "High Quality / Med-Large File"), (45, "Medium Quality / Medium File"), (55, "Low Quality / Small File"), (63, "Very Low Quality / Very Small File")],
                "libx264":    [(0, 51), (17, "Very High Quality / Large File"), (23, "High Quality / Med-Large File"), (28, "Medium Quality / Medium File"), (35, "Low Quality / Small File"), (51, "Very Low Quality / Very Small File")]
            }
            colors = ["very_high", "high", "medium", "low", "very_low"]
            if codec in ranges:
                bounds, *levels = ranges[codec]
                min_r, max_r = bounds
                if not (min_r <= crf <= max_r): status, color = f"Range ({codec[3:].upper()}): {min_r}-{max_r}", CRF_STATUS_COLORS["error"]
                else:
                    for i, (threshold, desc) in enumerate(levels):
                        if crf <= threshold: status, color = desc, CRF_STATUS_COLORS[colors[i]]; break
            else: status, color = "Unknown Codec", CRF_STATUS_COLORS["unknown"]
        except ValueError: status, color = "Invalid CRF (Number Required)", CRF_STATUS_COLORS["error"]
        self.crf_status_label.config(text=status, foreground=color)

    def _apply_preset(self, profile, crf, downscale_enabled, downscale_factor, status):
        self.output_profile.set(profile); self.quality_crf.set(crf)
        self.downscale_enabled.set(downscale_enabled); self.downscale_factor.set(downscale_factor)
        # Explicitly update the entry state after changing the variable
        self._toggle_downscale_entry_state()
        # The traces on the variables will call update_crf_status_label and _update_resolution_status_label automatically.
        self.status_message.config(text=status)

    def apply_low_quality_webm_preset(self): self._apply_preset("VP9 - .webm", "36", True, "0.5", "Applied 'Small WebM' preset (VP9).")
    def apply_quality_av1_webm_preset(self): self._apply_preset("AV1 - .webm", "24", False, "1.0", "Applied 'Quality WebM' preset (AV1).")

    def _update_resolution_status_label(self, *args):
        if self.is_loading or not hasattr(self, 'resolution_status_label') or not self.resolution_status_label.winfo_exists(): return
        status, color = "(Add images to see resolution)", CRF_STATUS_COLORS["default"]
        if self.file_tree.get_children():
            first_w, first_h = self._get_first_image_dimensions()
            if first_w:
                if self.downscale_enabled.get():
                    try:
                        factor = float(self.downscale_factor.get())
                        if not (0 < factor <= 1.0): raise ValueError("Factor out of range (0, 1.0]")
                        target_w, target_h = max(1, int(first_w * factor)), max(1, int(first_h * factor))
                        status, color = f"Downscale {first_w}x{first_h} → {target_w}x{target_h}", CRF_STATUS_COLORS["info"]
                    except ValueError: status, color = f"Original: {first_w}x{first_h}, Invalid Factor", CRF_STATUS_COLORS["error"]
                else: status = f"Original Resolution: {first_w}x{first_h}"
            else: status, color = "(Error reading first image)", CRF_STATUS_COLORS["error"]
        self.resolution_status_label.config(text=status, foreground=color)

    def _on_close(self):
        logging.info("Closing application, saving settings...")
        self.save_config()
        for handler in logging.getLogger().handlers[:]:
             if isinstance(handler, logging.FileHandler):
                  try: handler.close(); logging.getLogger().removeHandler(handler)
                  except Exception as e: logging.error(f"Error closing handler {handler}: {e}")
        self.root.destroy()

    def _get_codec_container_from_profile(self, profile_string=None):
        profile = profile_string or self.output_profile.get()
        data = OUTPUT_PROFILES.get(profile)
        if data: return data['codec'], data['container']
        logging.warning(f"Invalid profile '{profile}'. Falling back to default.")
        default_data = OUTPUT_PROFILES[DEFAULT_OUTPUT_PROFILE]
        return default_data['codec'], default_data['container']

    def _set_ui_state(self, enabled):
        new_state = 'normal' if enabled else 'disabled'
        combo_state = 'readonly' if enabled else 'disabled'
        tree_select_mode = 'extended' if enabled else 'none'
        logging.debug(f"Setting UI state: {'enabled' if enabled else 'disabled'}")
        for widget in self.widgets_to_disable:
            try:
                if isinstance(widget, ttk.Combobox): widget.config(state=combo_state)
                elif widget.winfo_exists(): widget.config(state=new_state)
            except tk.TclError as e: logging.warning(f"TclError setting state for {widget}: {e}")
            except Exception as e: logging.error(f"Error setting state for {widget}: {e}")
        try:
            self.file_tree.config(selectmode=tree_select_mode)
            self.file_tree.config(cursor="" if enabled else "arrow")
            for event, callback in self.treeview_bindings.items():
                 if enabled: self.file_tree.bind(event, callback)
                 else: self.file_tree.unbind(event)
            if isinstance(self.root, TkinterDnD.Tk):
                 try:
                     if enabled: self.file_tree.drop_target_register(DND_FILES)
                     else: self.file_tree.drop_target_unregister()
                 except tk.TclError: pass
            tag_to_modify = 'disabled'
            items = self.file_tree.get_children()
            for item_id in items:
                 current_tags = list(self.file_tree.item(item_id, 'tags'))
                 has_tag = tag_to_modify in current_tags
                 if enabled and has_tag: current_tags.remove(tag_to_modify)
                 elif not enabled and not has_tag: current_tags.append(tag_to_modify)
                 else: continue
                 self.file_tree.item(item_id, tags=tuple(current_tags))
        except tk.TclError as e: logging.warning(f"TclError configuring file_tree state: {e}")
        except Exception as e: logging.error(f"Error configuring file_tree state: {e}")
        if enabled: self._toggle_downscale_entry_state()
        elif hasattr(self, 'multiplier_entry'): self.multiplier_entry.config(state='disabled')

if __name__ == "__main__":
    try: import tkinterdnd2
    except ImportError: logging.warning("Optional: Install 'tkinterdnd2-universal' for drag & drop.")
    if sys.platform.startswith('win'):
        try:
            awareness = ctypes.c_int()
            ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
            if awareness.value == 0: ctypes.windll.shcore.SetProcessDpiAwareness(2)
            else: logging.info(f"DPI awareness already set (value: {awareness.value}).")
        except (AttributeError, OSError, Exception) as e: logging.warning(f"Could not set/get DPI awareness: {e}")
    sys.excepthook = handle_unhandled_exception
    try:
        app = ImagesToVideoSlideshow()
        app.run()
    except Exception:
        logging.critical("Exception during app initialization or main loop start:", exc_info=True)
