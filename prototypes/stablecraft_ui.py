"""StableCraft — Tkinter MVP UI.

Zero extra dependency: the UI uses the standard library and Tkinter. The heavy
lifting (ComfyUI, Pillow, requests) runs in the ComfyUI embedded Python through
`prototypes/bridge_cli.py`.

Run:
    python prototypes/stablecraft_ui.py --config config.toml
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tomllib
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app_meta import (  # noqa: E402
    APP_VERSION,
    AUTHOR,
    LATEST_RELEASE_API,
    RELEASES_URL,
    REPO_URL,
)
from control_client import ControlClient, ControlError, read_token  # noqa: E402
from i18n import current_language, profile_text, set_language, tr  # noqa: E402
from lora_store import (  # noqa: E402
    MAX_LORAS,
    active_items as active_lora_items,
    compatibility as lora_compatibility,
    family_label as lora_family_label,
    load_settings as load_lora_settings,
    normalize_item as normalize_lora_item,
    profile_items as profile_lora_items,
    save_settings as save_lora_settings,
    set_profile_items as set_profile_lora_items,
    signature as lora_signature,
)
from models_tools import (  # noqa: E402
    download_options,
    krea_node_status,
    latest_krea_release,
    model_family_key,
    quantization_label,
    resolve_filename,
    same_model_file,
    set_selected_file,
)
from platform_support import open_path  # noqa: E402
from session_store import (  # noqa: E402
    SessionStore,
    parse_session_id,
    session_layer_name,
)

ROOT = Path(__file__).resolve().parents[1]

BG = "#1b1b1f"
PANEL = "#25252b"
PANEL_2 = "#2d2d34"
FG = "#e8e8ea"
MUTED = "#9a9aa3"
ACCENT = "#3b82f6"
ACCENT_ACTIVE = "#2563eb"
GREEN = "#22c55e"
RED = "#ef4444"
YELLOW = "#eab308"
BORDER = "#3a3a44"
# Scrollbars: the thumb keeps the panel border tone, the trough is darker so
# the two are immediately distinguishable on every StableCraft window.
SCROLL_THUMB = BORDER
SCROLL_THUMB_ACTIVE = "#50505c"
SCROLL_TROUGH = "#141418"

# Gallery cells use a fixed 4:3 box.  The thumbnail is contained inside it,
# so 16:9 and portrait results stay readable without being cropped.
GALLERY_IMAGE_W = 128
GALLERY_IMAGE_H = 96
GALLERY_CELL_W = GALLERY_IMAGE_W + 4
GALLERY_CELL_H = GALLERY_IMAGE_H + 4

KREA_PROFILES = {"krea2_edit", "krea2_general_edit"}
QWEN_PROFILE = "qwen_image_21"
MOSS_PROFILE = "moss_image_sft"
SUPPORTED_PROFILES = {
    "flux3_klein",
    "flux2_klein_9b",
    "krea2_general_edit",
    "krea2_edit",
    QWEN_PROFILE,
    MOSS_PROFILE,
}
REFERENCE_PROFILES = {
    "krea2_edit",
    "krea2_general_edit",
    "flux3_klein",
    "flux2_klein_9b",
    QWEN_PROFILE,
    MOSS_PROFILE,
}
T2I_REFERENCE_PROFILES = {"flux3_klein", "flux2_klein_9b", QWEN_PROFILE}
# Only FLUX.2 Klein EDIT starts from the source crop latent. Other profiles
# sample from an empty latent, where denoise < 1 produces artifacts.
DENOISE_PROFILES = {"flux2_klein_9b"}

# Fallback lists, replaced by ComfyUI's /object_info when it is reachable.
FALLBACK_SAMPLERS = [
    "euler",
    "euler_cfg_pp",
    "euler_ancestral",
    "euler_ancestral_cfg_pp",
    "heun",
    "heunpp2",
    "exp_heun_2_x0",
    "exp_heun_2_x0_sde",
    "dpm_2",
    "dpm_2_ancestral",
    "lms",
    "dpm_fast",
    "dpm_adaptive",
    "dpmpp_2s_ancestral",
    "dpmpp_2s_ancestral_cfg_pp",
    "dpmpp_sde",
    "dpmpp_sde_gpu",
    "dpmpp_2m",
    "dpmpp_2m_cfg_pp",
    "dpmpp_2m_sde",
    "dpmpp_2m_sde_gpu",
    "dpmpp_2m_sde_heun",
    "dpmpp_2m_sde_heun_gpu",
    "dpmpp_3m_sde",
    "dpmpp_3m_sde_gpu",
    "ddpm",
    "lcm",
    "ipndm",
    "ipndm_v",
    "deis",
    "cfgpp_ud10_ab",
    "res_multistep",
    "res_multistep_cfg_pp",
    "res_multistep_ancestral",
    "res_multistep_ancestral_cfg_pp",
    "gradient_estimation",
    "gradient_estimation_cfg_pp",
    "er_sde",
    "seeds_2",
    "seeds_3",
    "sa_solver",
    "sa_solver_pece",
    "ddim",
    "uni_pc",
    "uni_pc_bh2",
]
FALLBACK_SCHEDULERS = [
    "simple",
    "sgm_uniform",
    "karras",
    "exponential",
    "ddim_uniform",
    "beta",
    "normal",
    "linear_quadratic",
    "kl_optimal",
]


DEFAULTS: dict[str, Any] = {
    "app": {
        "language": "en",
        "default_profile": "flux3_klein",
        "sessions_dir": str(ROOT / "user" / "sessions"),
        "python_ui": "",
        "bridge_python": "",
    },
    "photocraft": {
        "control_host": "127.0.0.1",
        "control_port": 7990,
        "control_token_file": str(ROOT / "user" / "control.token"),
        "automation_root": str(ROOT / "user"),
    },
    "comfyui": {
        "endpoint": "http://127.0.0.1:8188",
        "manage": True,
        "open_console": True,
        "extra_args": [],
        "root": "",
        "python": "",
    },
    "models": {
        "store_dir": str(ROOT / "models"),
    },
    "profiles": {
        "flux3_klein": {
            "steps": 16,
            "cfg": 1.0,
            "context_padding": 96,
            "feather": 10,
        }
    },
}


def deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path) -> dict[str, Any]:
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg = deep_merge(DEFAULTS, data)
    app = cfg.setdefault("app", {})
    photocraft = cfg.setdefault("photocraft", {})
    if not photocraft.get("control_token_file"):
        photocraft["control_token_file"] = str(ROOT / "user" / "control.token")
    if not photocraft.get("automation_root"):
        photocraft["automation_root"] = str(ROOT / "user")
    if not app.get("sessions_dir"):
        app["sessions_dir"] = str(ROOT / "user" / "sessions")
    comfyui = cfg.setdefault("comfyui", {})
    if not comfyui.get("root"):
        comfyui["root"] = os.environ.get("STABLECRAFT_COMFY_ROOT", "")
    if not comfyui.get("python"):
        comfyui["python"] = os.environ.get("STABLECRAFT_COMFY_PYTHON", "")
    return cfg


def manifest() -> dict[str, Any]:
    return json.loads((ROOT / "models.json").read_text(encoding="utf-8"))


class Tooltip:
    """Minimal hover tooltip for Tk widgets."""

    def __init__(
        self, widget: tk.Misc, text: str = "", delay: int = 400
    ) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def set_text(self, text: str) -> None:
        self.text = text
        self._hide()

    def _schedule(self, _event: object = None) -> None:
        self._cancel()
        if self.text:
            self._after_id = self.widget.after(self.delay, self._show)

    def _show(self) -> None:
        self._after_id = None
        if not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 8
            y = (
                self.widget.winfo_rooty()
                + self.widget.winfo_height()
                + 6
            )
            self._tip = tk.Toplevel(self.widget)
            self._tip.wm_overrideredirect(True)
            self._tip.attributes("-topmost", True)
            self._tip.wm_geometry(f"+{x}+{y}")
            tk.Label(
                self._tip,
                text=self.text,
                justify="left",
                background=PANEL_2,
                foreground=FG,
                relief="solid",
                bd=1,
                padx=6,
                pady=4,
                wraplength=360,
                font=("Segoe UI", 8),
            ).pack()
        except tk.TclError:
            self._tip = None

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _hide(self, _event: object = None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def comfy_json(endpoint: str, path: str, timeout: float = 3.0) -> Any:
    with urllib.request.urlopen(endpoint.rstrip("/") + path, timeout=timeout) as response:
        return json.load(response)


def comfy_node_exists(endpoint: str, node: str) -> bool:
    info = comfy_json(endpoint, f"/object_info/{node}")
    return isinstance(info, dict) and node in info


def comfy_options(endpoint: str, node: str, key: str) -> list[str]:
    info = comfy_json(endpoint, f"/object_info/{node}")
    spec = info[node]["input"]["required"][key]
    if isinstance(spec, list) and spec and isinstance(spec[0], list):
        return list(spec[0])
    return []


def short_error(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()
    return (text[0] if text else exc.__class__.__name__)[:90]


def short_lora_label(value: object, limit: int = 24) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in str(value).lstrip("v").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts)


class StableCraftApp(tk.Tk):
    def __init__(self, config_path: Path, initial_profile: str | None = None) -> None:
        super().__init__()
        try:
            icon = ROOT / "demo" / "logo_full.ico"
            if icon.exists():
                self.iconbitmap(default=str(icon))
        except tk.TclError:
            pass
        self.config_path = config_path
        self.cfg = load_config(config_path)
        set_language(str(self.cfg.get("app", {}).get("language", "en")))
        self.manifest = manifest()
        self.queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.stop_event = threading.Event()
        self.proc: subprocess.Popen[str] | None = None
        self.running = False
        self.proc_reader: threading.Thread | None = None
        self.last_error: str | None = None
        self.preview_paths: dict[str, str | None] = {"result": None, "document": None}
        self.preview_image: tk.PhotoImage | None = None
        self.session_store = SessionStore(self._sessions_root())
        self.session_id: str | None = None
        self.session_data: dict[str, Any] | None = None
        self.current_selection: list[int] | None = None
        self.gallery_images: list[tk.PhotoImage] = []
        self.gallery_buttons: dict[int, tk.Canvas] = {}
        self.gallery_canvases: dict[int, tk.Canvas] = {}
        self._gallery_items: list[tk.Canvas] = []
        self._gallery_item_indices: list[int] = []
        self._gallery_star_centers: dict[int, tuple[int, int]] = {}
        self._gallery_delete_centers: dict[int, tuple[int, int]] = {}
        self._gallery_cell_w = GALLERY_CELL_W
        self._gallery_cell_h = GALLERY_CELL_H
        self._gallery_columns = 0
        self._gallery_reflow_job: str | None = None
        self._gallery_scroll_to: int | None = None
        # Repainting the same gallery (e.g. after applying an existing
        # generation) keeps the user's scroll position instead of jumping to
        # the current item.
        self._gallery_restore_y: float | None = None
        self._gallery_last_session: str | None = None
        self._gallery_last_count: int | None = None
        self.pending_session_id: str | None = None
        self.pending_generation: int | None = None
        self.batch_var = tk.StringVar(value="1")
        self.topmost_var = tk.BooleanVar(value=False)
        self._topmost_state = False
        self._topmost_job: str | None = None
        self.job_kind = "generate"
        self._apply_only = False
        # Layer created by the last normal generation. The PhotoCraft layer
        # change it causes must not reload the prompt/settings fields.
        self._job_layer_id: int | None = None
        # Favorites toggled while a bridge process is running. The bridge owns
        # session.json during a generation, so persist them at the end.
        self._pending_favorites: dict[int, bool] = {}
        self._pending_favorites_session: str | None = None
        self.xyz_window: Any = None
        self.progress_value = 0
        self.progress_text = "Prêt."
        self._progress_indeterminate = False
        self._progress_position = 0.0
        self._progress_animation: str | None = None
        self._cancel_requested = False
        self.reference_path: Path | None = None
        self.reference_name: str | None = None
        self.reference_thumb_image: tk.PhotoImage | None = None
        self.reference_is_pending = False
        self.pending_reference_selection: list[int] | None = None
        self.mode_var = tk.StringVar(value="edit")
        self._ref_enabled_before_t2i = False
        self._last_mode = "edit"
        self.guide_window: tk.Toplevel | None = None
        self._drop_proc_ref: Any = None
        self._old_wndproc: Any = None
        self._drop_hwnd: int | None = None
        self._drop_enabled = False
        self._win_user32: Any = None
        self._win_shell32: Any = None
        self.update_url = RELEASES_URL
        self.krea_status: dict[str, Any] | None = None
        self.krea_latest: dict[str, Any] | None = None
        self.profile_key = initial_profile or str(self.cfg["app"].get("default_profile", "flux3_klein"))
        self.models_ok = True
        self.models_checked = False
        self.missing_models: list[dict[str, Any]] = []
        self.models_error: str | None = None
        self._model_manager: Any = None
        self._sampler_choices = list(FALLBACK_SAMPLERS)
        self._scheduler_choices = list(FALLBACK_SCHEDULERS)
        self._sampler_choices_loaded = False
        self._comfy_model_files: dict[str, list[str]] = {}
        self._comfy_model_files_key: str | None = None
        # A selection belongs to one document + layer + bounds. Keeping that
        # context lets the UI reset the form instead of leaking the previous
        # project's prompt/settings into a new project or a fresh layer.
        self.pending_model_restart: set[tuple[str, str]] = set()
        self._context_ready = False
        self._context_key: tuple[Any, ...] | None = None
        self._context_selection: list[int] | None = None
        self._last_layer_key: tuple[Any, ...] | None = None
        self._session_retry_done: set[str] = set()
        self._duplicate_split_failed: dict[tuple[int, int, str], float] = {}
        self._closing = False
        self.lora_settings = load_lora_settings()
        self.lora_items: list[dict[str, Any]] = []
        self.lora_enabled_var = tk.BooleanVar(
            value=bool(self.lora_settings.get("enabled", True))
        )
        self.lora_blur_var = tk.BooleanVar(
            value=bool(self.lora_settings.get("blur_nsfw", True))
        )
        self.lora_manager: Any = None
        self._lora_available: set[str] | None = None

        self.pc_ok = False
        self.comfy_ok = False
        self.has_selection = False

        self.title(f"StableCraft v{APP_VERSION} — PhotoCraft × ComfyUI")
        self.geometry("500x930+20+20")
        self.minsize(460, 760)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._style()
        self._build()
        self._translate_static_widgets(self)
        self._load_profile(self.profile_key)
        self._load_preview(None)

        self.after(100, self._poll_queue)
        self.after(250, self._enable_windows_drop)
        self.after(1500, lambda: threading.Thread(target=self._check_update, daemon=True).start())
        self.after(2200, lambda: threading.Thread(target=self._check_krea_node, daemon=True).start())
        threading.Thread(target=self._refresh_loop, daemon=True).start()
        self._check_models()

    def _sessions_root(self) -> Path:
        configured = self.cfg.get("app", {}).get("sessions_dir")
        if configured:
            path = Path(str(configured))
            return path if path.is_absolute() else (ROOT / path)
        return ROOT / "user" / "sessions"

    def _pending_root(self) -> Path:
        root = self.session_store.root.parent / "pending"
        root.mkdir(parents=True, exist_ok=True)
        return root

    # ------------------------------------------------------------------
    # Look
    # ------------------------------------------------------------------

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Panel.TLabel", background=PANEL, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=FG, font=("Segoe UI", 18, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("TButton", background=PANEL_2, foreground=FG, borderwidth=0, padding=6)
        style.map("TButton", background=[("active", BORDER)])
        style.configure(
            "TCombobox",
            fieldbackground=PANEL_2,
            background=PANEL_2,
            foreground=FG,
            arrowcolor=FG,
            bordercolor=BORDER,
            lightcolor=PANEL_2,
            darkcolor=PANEL_2,
        )
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_2)], foreground=[("readonly", FG)])
        style.configure(
            "TSpinbox",
            fieldbackground=PANEL_2,
            background=PANEL_2,
            foreground=FG,
            arrowcolor=FG,
            bordercolor=BORDER,
            lightcolor=PANEL_2,
            darkcolor=PANEL_2,
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=PANEL_2,
            background=ACCENT,
            bordercolor=PANEL_2,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
        )
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)])
        for orient in ("Vertical", "Horizontal"):
            name = f"{orient}.TScrollbar"
            style.configure(
                name,
                background=SCROLL_THUMB,
                troughcolor=SCROLL_TROUGH,
                bordercolor=SCROLL_TROUGH,
                lightcolor=SCROLL_THUMB,
                darkcolor=SCROLL_THUMB,
                arrowcolor=FG,
                relief="flat",
                borderwidth=0,
                arrowsize=12,
            )
            style.map(
                name,
                background=[
                    ("active", SCROLL_THUMB_ACTIVE),
                    ("pressed", SCROLL_THUMB_ACTIVE),
                ],
                lightcolor=[
                    ("active", SCROLL_THUMB_ACTIVE),
                    ("pressed", SCROLL_THUMB_ACTIVE),
                ],
                darkcolor=[
                    ("active", SCROLL_THUMB_ACTIVE),
                    ("pressed", SCROLL_THUMB_ACTIVE),
                ],
            )

    def _text(self, parent: tk.Misc, height: int, font: tuple[str, int] | tuple[str, int, str] = ("Segoe UI", 10)) -> tk.Text:
        text = tk.Text(
            parent,
            height=height,
            wrap="word",
            bg=PANEL_2,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            bd=0,
            padx=8,
            pady=6,
            font=font,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self._attach_text_resize_grip(text, height)
        return text

    def _attach_text_resize_grip(self, text: tk.Text, default_height: int) -> None:
        """Windows-style grip in the bottom-right corner of a Text widget."""
        grip = ttk.Sizegrip(text)
        grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)
        grip.configure(cursor="bottom_right_corner")
        state = {"y": 0, "height": int(default_height)}

        def line_height() -> int:
            try:
                font = tkfont.Font(font=text.cget("font"))
                return max(1, int(font.metrics("linespace")))
            except Exception:  # noqa: BLE001
                return 16

        def on_press(event: tk.Event) -> str:
            state["y"] = int(event.y_root)
            state["height"] = int(text.cget("height"))
            return "break"

        def on_drag(event: tk.Event) -> str:
            delta = int(event.y_root) - state["y"]
            lines = int(round(delta / line_height()))
            new_height = max(1, state["height"] + lines)
            if new_height != int(text.cget("height")):
                text.configure(height=new_height)
            return "break"

        def on_reset(_event: tk.Event) -> str:
            text.configure(height=int(default_height))
            return "break"

        grip.bind("<ButtonPress-1>", on_press)
        grip.bind("<B1-Motion>", on_drag)
        grip.bind("<Double-Button-1>", on_reset)

    def _lock_scroll_wheel(self, widget: tk.Misc) -> None:
        """Keep the wheel for page scrolling instead of changing the value."""
        widget.bind("<MouseWheel>", self._on_widget_wheel)
        widget.bind("<Button-4>", self._on_widget_wheel_button)
        widget.bind("<Button-5>", self._on_widget_wheel_button)

    def _on_mousewheel(self, event: tk.Event) -> None:
        widget = event.widget
        if not isinstance(widget, tk.Misc):
            return
        # bind_all is global: only scroll the main window, never a Toplevel.
        if widget.winfo_toplevel() is not self:
            return
        # Let text areas and list boxes handle their own wheel scrolling.
        if isinstance(widget, (tk.Text, tk.Listbox)):
            return
        self.main_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_widget_wheel(self, event: tk.Event) -> str:
        self._on_mousewheel(event)
        return "break"

    def _on_widget_wheel_button(self, event: tk.Event) -> str:
        self.main_canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        return "break"

    # ------------------------------------------------------------------
    # Gallery (wrapping grid)
    # ------------------------------------------------------------------

    def _bind_gallery_wheel(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._on_gallery_wheel)
        widget.bind("<Button-4>", self._on_gallery_wheel_button)
        widget.bind("<Button-5>", self._on_gallery_wheel_button)

    def _on_gallery_wheel(self, event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta:
            self.gallery_canvas.yview_scroll(int(-delta / 120), "units")
        return "break"

    def _on_gallery_wheel_button(self, event: tk.Event) -> str:
        self.gallery_canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        return "break"

    def _on_gallery_canvas_configure(self, event: tk.Event) -> None:
        try:
            self.gallery_canvas.itemconfigure(
                self.gallery_window, width=max(1, event.width)
            )
        except tk.TclError:
            pass
        if self._gallery_reflow_job is not None:
            try:
                self.after_cancel(self._gallery_reflow_job)
            except tk.TclError:
                pass
        self._gallery_reflow_job = self.after(30, self._layout_gallery)

    def _gallery_height_for(self, columns: int) -> int:
        rows = max(1, math.ceil(len(self._gallery_items) / max(1, columns)))
        visible_rows = min(3, rows)
        return visible_rows * (self._gallery_cell_h + 2) + 2

    def _layout_gallery(self) -> None:
        self._gallery_reflow_job = None
        if not self._gallery_items:
            self._gallery_columns = 0
            return
        width = self.gallery_canvas.winfo_width()
        if width <= 1:
            width = 480
        item_w = max(40, self._gallery_cell_w + 2)
        columns = max(1, (width - 4) // item_w)
        desired_height = self._gallery_height_for(columns)
        if int(self.gallery_canvas.cget("height")) != desired_height:
            self.gallery_canvas.configure(height=desired_height)
        if columns == self._gallery_columns and all(
            item.winfo_manager() for item in self._gallery_items
        ):
            self.gallery_inner.update_idletasks()
            self.gallery_canvas.configure(
                scrollregion=self.gallery_canvas.bbox("all")
            )
            if self.gallery_canvas.winfo_height() > 1:
                if self._gallery_restore_y is not None:
                    self.gallery_canvas.yview_moveto(self._gallery_restore_y)
                    self._gallery_restore_y = None
                elif self._gallery_scroll_to is not None:
                    self._scroll_gallery_to(self._gallery_scroll_to)
                    self._gallery_scroll_to = None
            return
        self._gallery_columns = columns
        for index, item in enumerate(self._gallery_items):
            item.grid(
                row=index // columns,
                column=index % columns,
                padx=1,
                pady=1,
                sticky="n",
            )
        self.gallery_inner.update_idletasks()
        self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))
        if self.gallery_canvas.winfo_height() > 1:
            if self._gallery_restore_y is not None:
                self.gallery_canvas.yview_moveto(self._gallery_restore_y)
                self._gallery_restore_y = None
            elif self._gallery_scroll_to is not None:
                self._scroll_gallery_to(self._gallery_scroll_to)
                self._gallery_scroll_to = None

    def _scroll_gallery_to(self, index: int) -> None:
        try:
            position = self._gallery_item_indices.index(index)
        except ValueError:
            return
        if not 0 <= position < len(self._gallery_items):
            return
        item = self._gallery_items[position]
        self.gallery_inner.update_idletasks()
        canvas_h = max(1, self.gallery_canvas.winfo_height())
        inner_h = max(1, self.gallery_inner.winfo_height())
        if inner_h <= canvas_h + 1:
            self.gallery_canvas.yview_moveto(0.0)
            return
        y = max(0, int(item.winfo_y()))
        target = max(0.0, min(1.0, (y - 4) / max(1, inner_h - canvas_h)))
        self.gallery_canvas.yview_moveto(target)

    def _gallery_set_star(self, canvas: tk.Canvas, visible: bool) -> None:
        try:
            canvas.itemconfigure("star", state="normal" if visible else "hidden")
        except tk.TclError:
            pass

    def _gallery_set_delete(self, canvas: tk.Canvas, visible: bool) -> None:
        try:
            canvas.itemconfigure("del", state="normal" if visible else "hidden")
        except tk.TclError:
            pass

    def _gallery_enter(self, canvas: tk.Canvas) -> None:
        self._gallery_set_star(canvas, True)
        self._gallery_set_delete(canvas, True)

    def _gallery_leave(self, index: int, canvas: tk.Canvas) -> None:
        # Read the current favorite instead of the value captured when the item
        # was created: toggling the star must survive the mouse leaving.
        favorite = False
        if self.session_data:
            generations = self.session_data.get("generations", [])
            if 0 <= index < len(generations):
                favorite = bool(generations[index].get("favorite"))
        self._gallery_set_star(canvas, favorite)
        self._gallery_set_delete(canvas, False)

    def _make_gallery_item(
        self,
        index: int,
        generation: dict[str, Any],
        image: tk.PhotoImage,
        selected: bool,
        cell_w: int,
        cell_h: int,
        image_w: int,
        image_h: int,
    ) -> tk.Canvas:
        favorite = bool(generation.get("favorite"))
        canvas = tk.Canvas(
            self.gallery_inner,
            width=cell_w,
            height=cell_h,
            bg="#111114",
            highlightthickness=1,
            highlightbackground=ACCENT if selected else BORDER,
            cursor="hand2",
        )
        offset_x = max(0, (cell_w - image_w) // 2)
        offset_y = max(0, (cell_h - image_h) // 2)
        canvas.create_image(offset_x, offset_y, image=image, anchor="nw")

        # Star badge, on the case's top-right corner.
        star_x = cell_w - 10
        star_y = 10
        self._gallery_star_centers[index] = (star_x, star_y)
        canvas.create_oval(
            star_x - 8,
            star_y - 8,
            star_x + 8,
            star_y + 8,
            fill="#111114",
            outline="#000000",
            tags=("star", "star_bg"),
        )
        canvas.create_text(
            star_x,
            star_y,
            text="★" if favorite else "☆",
            fill=YELLOW if favorite else MUTED,
            font=("Segoe UI", 10, "bold"),
            tags=("star", "star_fg"),
        )
        if not favorite:
            canvas.itemconfigure("star", state="hidden")

        # Number badge, on the image's bottom-right corner.
        label = f"#{index + 1}"
        try:
            number_font = tkfont.Font(family="Segoe UI", size=8, weight="bold")
            text_w = number_font.measure(label)
            text_h = number_font.metrics("linespace")
        except Exception:  # noqa: BLE001
            text_w, text_h = 20, 12
        badge_w = text_w + 8
        badge_h = text_h + 4
        badge_x = cell_w - badge_w - 3
        badge_y = cell_h - badge_h - 3
        canvas.create_rectangle(
            badge_x,
            badge_y,
            badge_x + badge_w,
            badge_y + badge_h,
            fill="#111114",
            outline="#000000",
            tags=("num", "num_bg"),
        )
        canvas.create_text(
            badge_x + badge_w / 2,
            badge_y + badge_h / 2,
            text=label,
            fill=FG,
            font=("Segoe UI", 8, "bold"),
            tags=("num", "num_fg"),
        )

        # Delete badge, on the case's bottom-left corner. Hidden until hover.
        del_x = 10
        del_y = cell_h - 10
        self._gallery_delete_centers[index] = (del_x, del_y)
        canvas.create_oval(
            del_x - 8,
            del_y - 8,
            del_x + 8,
            del_y + 8,
            fill="#111114",
            outline="#000000",
            tags=("del", "del_bg"),
        )
        canvas.create_text(
            del_x,
            del_y,
            text="✕",
            fill=MUTED,
            font=("Segoe UI", 9, "bold"),
            tags=("del", "del_fg"),
        )
        canvas.itemconfigure("del", state="hidden")

        canvas.bind(
            "<Enter>",
            lambda _event, c=canvas: self._gallery_enter(c),
        )
        canvas.bind(
            "<Leave>",
            lambda _event, i=index, c=canvas: self._gallery_leave(i, c),
        )
        canvas.bind(
            "<Button-1>",
            lambda event, idx=index, c=canvas: self._gallery_click(event, idx, c),
        )
        self._bind_gallery_wheel(canvas)
        return canvas

    def _gallery_click(
        self, event: tk.Event, index: int, canvas: tk.Canvas
    ) -> str:
        delete = self._gallery_delete_centers.get(index)
        if delete is not None and abs(event.x - delete[0]) <= 12 and abs(
            event.y - delete[1]
        ) <= 12:
            self._delete_generation(index)
            return "break"
        closest = canvas.find_closest(event.x, event.y)
        if closest:
            tags = canvas.gettags(closest[0])
            if "del" in tags:
                self._delete_generation(index)
                return "break"
        star = self._gallery_star_centers.get(index)
        if star is not None and abs(event.x - star[0]) <= 12 and abs(
            event.y - star[1]
        ) <= 12:
            self._toggle_favorite(index)
            return "break"
        if closest:
            tags = canvas.gettags(closest[0])
            if "star" in tags:
                self._toggle_favorite(index)
                return "break"
        if self.running:
            return "break"
        self._apply_generation(index)
        return "break"

    def _toggle_favorite(self, index: int) -> None:
        if not self.session_data:
            return
        generations = self.session_data.get("generations", [])
        if not 0 <= index < len(generations):
            return
        generation = generations[index]
        favorite = not bool(generation.get("favorite"))
        generation["favorite"] = favorite
        if self.running:
            # The bridge writes session.json while it generates. Keep the
            # change in memory and merge it back once the job is over.
            if self._pending_favorites_session != self.session_id:
                self._pending_favorites.clear()
                self._pending_favorites_session = self.session_id
            self._pending_favorites[index] = favorite
        else:
            try:
                self.session_store.save(self.session_data)
            except Exception as exc:  # noqa: BLE001
                self._log(tr("Favori : {error}", error=short_error(exc)))
        canvas = self.gallery_canvases.get(index)
        if canvas is not None:
            try:
                canvas.itemconfigure(
                    "star_fg",
                    text="★" if favorite else "☆",
                    fill=YELLOW if favorite else MUTED,
                )
            except tk.TclError:
                pass
            self._gallery_set_star(canvas, favorite)
        self._update_gallery_title()

    def _delete_generation(self, index: int) -> None:
        if self.running or not self.session_id or not self.session_data:
            return
        generations = self.session_data.get("generations", [])
        if not 0 <= index < len(generations):
            return
        if not messagebox.askyesno(
            tr("Supprimer la génération"),
            tr(
                "Supprimer la génération #{index} ? Le fichier sera effacé du disque.",
                index=index + 1,
            ),
            parent=self,
        ):
            return
        try:
            self.session_store.delete_generation(self.session_data, index)
        except Exception as exc:  # noqa: BLE001
            try:
                self.session_data = self.session_store.load(self.session_id)
            except Exception:  # noqa: BLE001
                pass
            self._log(tr("Suppression : {error}", error=short_error(exc)))
            messagebox.showerror(
                tr("Suppression impossible"),
                short_error(exc),
                parent=self,
            )
            return
        self._pending_favorites.clear()
        self._pending_favorites_session = None
        self._populate_gallery()
        self._log(tr("Génération #{index} supprimée.", index=index + 1))

    def _apply_pending_favorites(self, data: dict[str, Any]) -> None:
        if not self._pending_favorites:
            return
        if self._pending_favorites_session != str(data.get("id") or ""):
            return
        generations = data.get("generations", [])
        for index, favorite in self._pending_favorites.items():
            if 0 <= index < len(generations):
                generations[index]["favorite"] = favorite

    def _flush_pending_favorites(self) -> None:
        """Persist favorites queued while a bridge process owned session.json."""
        if not self._pending_favorites:
            return
        data: dict[str, Any] | None = None
        if (
            self.session_data is not None
            and str(self.session_data.get("id") or "")
            == self._pending_favorites_session
        ):
            data = self.session_data
        elif self._pending_favorites_session:
            try:
                data = self.session_store.load(self._pending_favorites_session)
            except Exception:  # noqa: BLE001
                data = None
        if data is not None:
            self._apply_pending_favorites(data)
            try:
                self.session_store.save(data)
            except Exception as exc:  # noqa: BLE001
                self._log(tr("Favori : {error}", error=short_error(exc)))
        self._pending_favorites.clear()
        self._pending_favorites_session = None

    def _update_gallery_title(self) -> None:
        if not self.session_data:
            return
        generations = self.session_data.get("generations", [])
        favorites = sum(
            1 for generation in generations if generation.get("favorite")
        )
        text = tr(
            "Galerie — StableCraft [{session}] · {count} génération(s)",
            session=self.session_id,
            count=len(generations),
        )
        if favorites:
            text += tr(" · {count} favori(s)", count=favorites)
        self.gallery_title.config(text=text)

    def _section(
        self,
        parent: tk.Misc,
        title: str,
        action_text: str | None = None,
        action: Any = None,
    ) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=(8, 0))
        header = tk.Frame(frame, bg=BG)
        header.pack(fill="x")
        tk.Label(
            header, text=tr(title), bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold")
        ).pack(side="left")
        if action_text and action:
            tk.Button(
                header,
                text=action_text,
                command=action,
                bg=BG,
                fg=MUTED,
                activebackground=BG,
                activeforeground=FG,
                relief="flat",
                bd=0,
                font=("Segoe UI", 8),
                cursor="hand2",
            ).pack(side="right")
        return frame

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True)
        self.main_canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.main_canvas.yview)
        self.main_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.main_canvas.pack(side="left", fill="both", expand=True)

        main = tk.Frame(self.main_canvas, bg=BG, padx=14, pady=12)
        window_id = self.main_canvas.create_window((0, 0), window=main, anchor="nw")

        def on_frame_configure(_event: object) -> None:
            self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

        def on_canvas_configure(event: tk.Event) -> None:
            self.main_canvas.itemconfigure(window_id, width=event.width)

        main.bind("<Configure>", on_frame_configure)
        self.main_canvas.bind("<Configure>", on_canvas_configure)
        self.main_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        header = tk.Frame(main, bg=BG)
        header.pack(fill="x")
        title_row = tk.Frame(header, bg=BG)
        title_row.pack(anchor="w", fill="x")
        tk.Label(
            title_row,
            text="StableCraft",
            bg=BG,
            fg=FG,
            font=("Segoe UI", 20, "bold"),
        ).pack(side="left")
        tk.Label(
            title_row,
            text=f"v{APP_VERSION}",
            bg=PANEL_2,
            fg=ACCENT,
            padx=6,
            pady=1,
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(7, 0), pady=(5, 0))
        language_box = tk.Frame(title_row, bg=BG)
        language_box.pack(side="right")
        tk.Label(
            language_box,
            text=tr("Langue"),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(0, 4))
        self.language_var = tk.StringVar(value=current_language().upper())
        self.language_combo = ttk.Combobox(
            language_box,
            textvariable=self.language_var,
            values=("EN", "FR"),
            width=3,
            state="readonly",
        )
        self.language_combo.pack(side="left")
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_change)
        self._lock_scroll_wheel(self.language_combo)
        self.topmost_check = tk.Checkbutton(
            title_row,
            text=tr("Au premier plan"),
            variable=self.topmost_var,
            command=self._toggle_topmost,
            bg=BG,
            fg=MUTED,
            selectcolor=PANEL_2,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 8),
        )
        self.topmost_check.pack(side="right", padx=(0, 10))
        tk.Label(
            header,
            text="Le lasso de Stable.art, dans PhotoCraft, avec ComfyUI.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=tr("par {author} · {repo}", author=AUTHOR, repo=REPO_URL),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 7),
        ).pack(anchor="w", pady=(1, 4))
        self.update_label = tk.Label(
            header,
            text="",
            bg=BG,
            fg=YELLOW,
            anchor="w",
            font=("Segoe UI", 8),
            cursor="hand2",
        )
        self.update_label.pack(fill="x")
        self.update_label.bind("<Button-1>", self._open_release_page)
        self.node_update_label = tk.Label(
            header,
            text="",
            bg=BG,
            fg=YELLOW,
            anchor="w",
            wraplength=460,
            justify="left",
            font=("Segoe UI", 8),
            cursor="hand2",
        )
        self.node_update_label.pack(fill="x")
        self.node_update_label.bind("<Button-1>", lambda _event: self._open_model_manager())

        status = tk.Frame(main, bg=PANEL, padx=10, pady=8, highlightthickness=1, highlightbackground=BORDER)
        status.pack(fill="x", pady=(4, 0))
        self.pc_status = tk.Label(status, text="PhotoCraft : connexion…", bg=PANEL, fg=YELLOW, anchor="w", font=("Segoe UI", 9))
        self.pc_status.pack(fill="x")
        self.comfy_status = tk.Label(status, text="ComfyUI : connexion…", bg=PANEL, fg=YELLOW, anchor="w", font=("Segoe UI", 9))
        self.comfy_status.pack(fill="x")
        self.doc_status = tk.Label(status, text="Document : —", bg=PANEL, fg=MUTED, anchor="w", font=("Segoe UI", 9))
        self.doc_status.pack(fill="x")
        self.sel_status = tk.Label(status, text="Sélection : —", bg=PANEL, fg=MUTED, anchor="w", font=("Segoe UI", 9))
        self.sel_status.pack(fill="x")
        self.models_status = tk.Label(status, text="Modèles : vérification…", bg=PANEL, fg=YELLOW, anchor="w", font=("Segoe UI", 9))
        self.models_status.pack(fill="x")
        self.models_status.bind("<Button-1>", lambda _event: self._open_model_manager())

        mode_frame = self._section(main, "MODE")
        mode_row = tk.Frame(mode_frame, bg=BG)
        mode_row.pack(fill="x", pady=(4, 0))
        self.edit_radio = tk.Radiobutton(
            mode_row,
            text="EDIT — image source",
            variable=self.mode_var,
            value="edit",
            command=self._on_mode_change,
            bg=BG,
            fg=FG,
            selectcolor=PANEL_2,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 9, "bold"),
        )
        self.edit_radio.pack(side="left")
        self.t2i_radio = tk.Radiobutton(
            mode_row,
            text="T2I — texte seul",
            variable=self.mode_var,
            value="t2i",
            command=self._on_mode_change,
            bg=BG,
            fg=FG,
            selectcolor=PANEL_2,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 9, "bold"),
        )
        self.t2i_radio.pack(side="left", padx=(12, 0))
        self.mode_hint = tk.Label(
            mode_frame,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=420,
            font=("Segoe UI", 8),
        )
        self.mode_hint.pack(fill="x", pady=(2, 0))

        prompt_frame = self._section(
            main, "PROMPT", "Guide", self._show_prompt_guide
        )
        self.prompt_text = self._text(prompt_frame, 4)
        self.prompt_text.pack(fill="x", pady=(4, 0))
        self.prompt_text.insert("1.0", "Change the dress to royal blue, keep the pose and background unchanged.")

        neg_row = tk.Frame(prompt_frame, bg=BG)
        neg_row.pack(fill="x", pady=(4, 0))
        self.neg_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            neg_row,
            text="Negative prompt",
            variable=self.neg_var,
            command=self._toggle_negative,
            bg=BG,
            fg=MUTED,
            selectcolor=PANEL_2,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        self.neg_text = self._text(prompt_frame, 2)
        # hidden until the checkbox is on
        self._neg_visible = False

        ref_frame = self._section(main, "IMAGE DE RÉFÉRENCE")
        self.ref_var = tk.BooleanVar(value=False)
        self.ref_check = tk.Checkbutton(
            ref_frame,
            text="Utiliser une image de référence",
            variable=self.ref_var,
            command=self._toggle_reference,
            bg=BG,
            fg=MUTED,
            selectcolor=PANEL_2,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 9),
        )
        self.ref_check.pack(anchor="w", pady=(4, 0))
        self.ref_profile_hint = tk.Label(
            ref_frame,
            text="",
            bg=BG,
            fg=YELLOW,
            anchor="w",
            font=("Segoe UI", 8),
            wraplength=420,
        )
        self.ref_profile_hint.pack(fill="x")
        self.ref_panel = tk.Frame(ref_frame, bg=BG)
        self.ref_canvas = tk.Canvas(
            self.ref_panel,
            width=112,
            height=112,
            bg="#111114",
            highlightthickness=1,
            highlightbackground=BORDER,
            cursor="hand2",
        )
        self.ref_canvas.pack(side="left")
        self.ref_canvas.bind("<Button-1>", lambda _event: self._choose_reference())
        ref_side = tk.Frame(self.ref_panel, bg=BG)
        ref_side.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.ref_name = tk.Label(
            ref_side,
            text="Aucune image",
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=290,
            font=("Segoe UI", 8, "bold"),
        )
        self.ref_name.pack(fill="x")
        self.ref_hint = tk.Label(
            ref_side,
            text="Clique ou dépose une image ici.",
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=290,
            font=("Segoe UI", 8),
        )
        self.ref_hint.pack(fill="x", pady=(2, 4))
        ref_buttons = tk.Frame(ref_side, bg=BG)
        ref_buttons.pack(anchor="w", fill="x")
        self.ref_choose = tk.Button(
            ref_buttons,
            text=tr("Choisir…"),
            command=self._choose_reference,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=7,
            pady=2,
            font=("Segoe UI", 8),
            cursor="hand2",
        )
        self.ref_choose.pack(side="left")
        self.ref_paste = tk.Button(
            ref_buttons,
            text=tr("Coller"),
            command=self._paste_reference,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=7,
            pady=2,
            font=("Segoe UI", 8),
            cursor="hand2",
        )
        self.ref_paste.pack(side="left", padx=(4, 0))
        self.ref_remove = tk.Button(
            ref_buttons,
            text=tr("Retirer"),
            command=self._remove_reference,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=7,
            pady=2,
            font=("Segoe UI", 8),
            cursor="hand2",
            state="disabled",
        )
        self.ref_remove.pack(side="left", padx=(4, 0))
        self._draw_reference_tile()

        prof_frame = self._section(main, "PROFIL")
        self.profile_var = tk.StringVar()
        self.profile_labels: list[str] = []
        self.label_to_key: dict[str, str] = {}
        for key, profile in self.manifest["profiles"].items():
            label = profile_text(profile, "label")
            if key not in SUPPORTED_PROFILES:
                label += tr(" — bientôt")
            self.profile_labels.append(label)
            self.label_to_key[label] = key
        profile_row = tk.Frame(prof_frame, bg=BG)
        profile_row.pack(fill="x", pady=(4, 2))
        self.profile_combo = ttk.Combobox(
            profile_row,
            textvariable=self.profile_var,
            values=self.profile_labels,
            state="readonly",
        )
        self.profile_combo.pack(side="left", fill="x", expand=True)
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_change)
        self._lock_scroll_wheel(self.profile_combo)
        self.profile_manage_btn = tk.Button(
            profile_row,
            text=tr("Gérer"),
            command=self._open_model_manager,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            font=("Segoe UI", 8),
            cursor="hand2",
        )
        self.profile_manage_btn.pack(side="left", padx=(6, 0))
        self.profile_detail = tk.Label(prof_frame, text="", bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 9))
        self.profile_detail.pack(fill="x")
        self.profile_warning = tk.Label(
            prof_frame,
            text="",
            bg=BG,
            fg=YELLOW,
            anchor="w",
            justify="left",
            wraplength=420,
            font=("Segoe UI", 8),
        )
        self.quant_frame = tk.Frame(prof_frame, bg=BG)
        tk.Label(
            self.quant_frame,
            text=tr("Quantification"),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left")
        self.quant_var = tk.StringVar()
        self.quant_combo = ttk.Combobox(
            self.quant_frame,
            textvariable=self.quant_var,
            values=[],
            state="readonly",
            width=24,
        )
        self.quant_combo.pack(side="left", padx=(6, 0), fill="x", expand=True)
        self.quant_combo.bind("<<ComboboxSelected>>", self._on_quant_change)
        self._lock_scroll_wheel(self.quant_combo)
        self.quant_map: dict[str, str] = {}

        lora_frame = self._section(main, "LORA")
        lora_top = tk.Frame(lora_frame, bg=BG)
        lora_top.pack(fill="x", pady=(4, 0))
        self.lora_check = tk.Checkbutton(
            lora_top,
            text=tr("Activer les LoRA"),
            variable=self.lora_enabled_var,
            command=self._toggle_loras,
            bg=BG,
            fg=MUTED,
            selectcolor=PANEL_2,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 9),
        )
        self.lora_check.pack(side="left")
        self.lora_manage_btn = tk.Button(
            lora_top,
            text=tr("Gérer les LoRA…"),
            command=self._open_lora_manager,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=10,
            pady=3,
            font=("Segoe UI", 8),
            cursor="hand2",
        )
        self.lora_manage_btn.pack(side="right")
        self.lora_summary = tk.Label(
            lora_frame,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=420,
            font=("Segoe UI", 9),
        )
        self.lora_summary.pack(fill="x", pady=(2, 0))
        self.lora_hint = tk.Label(
            lora_frame,
            text="",
            bg=BG,
            fg=YELLOW,
            anchor="w",
            justify="left",
            wraplength=420,
            font=("Segoe UI", 8),
            cursor="hand2",
        )
        self.lora_hint.pack(fill="x")
        self.lora_hint.bind(
            "<Button-1>", lambda _event: self._open_lora_manager()
        )

        settings = self._section(main, "RÉGLAGES")
        grid = tk.Frame(settings, bg=BG)
        grid.pack(fill="x", pady=(4, 0))
        for col in (1, 3):
            grid.columnconfigure(col, weight=1)
        self.padding_var = tk.StringVar(value="96")
        self.feather_var = tk.StringVar(value="10")
        self.steps_var = tk.StringVar(value="16")
        self.cfg_var = tk.StringVar(value="1.0")
        self.sampler_var = tk.StringVar(value="euler")
        self.scheduler_var = tk.StringVar(value="simple")
        self.denoise_var = tk.StringVar(value="1.00")
        self.seed_var = tk.StringVar(value="-1")
        fields = [
            ("Contexte (px)", self.padding_var, 0, 0, 0, 512, 16),
            ("Feather (px)", self.feather_var, 0, 2, 0, 100, 1),
            ("Steps", self.steps_var, 1, 0, 1, 60, 1),
            ("CFG", self.cfg_var, 1, 2, 0, 20, 0.1),
            ("Seed (-1 = aléatoire)", self.seed_var, 2, 0, -1, 2**31 - 1, 1),
        ]
        for label, var, row, col, lo, hi, step in fields:
            tk.Label(grid, text=label, bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
                row=row, column=col, sticky="w", padx=(0, 6), pady=2
            )
            if label.startswith("Seed"):
                widget = tk.Entry(
                    grid,
                    textvariable=var,
                    bg=PANEL_2,
                    fg=FG,
                    insertbackground=FG,
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BORDER,
                    highlightcolor=ACCENT,
                )
            else:
                widget = ttk.Spinbox(grid, from_=lo, to=hi, increment=step, textvariable=var)
            widget.grid(row=row, column=col + 1, sticky="ew", pady=2)
            self._lock_scroll_wheel(widget)

        tk.Label(grid, text="Sampler", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=3, column=0, sticky="w", padx=(0, 6), pady=2
        )
        self.sampler_combo = ttk.Combobox(
            grid,
            textvariable=self.sampler_var,
            values=self._sampler_choices,
            state="readonly",
        )
        self.sampler_combo.grid(row=3, column=1, columnspan=3, sticky="ew", pady=2)
        self._lock_scroll_wheel(self.sampler_combo)

        tk.Label(grid, text="Scheduler", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=4, column=0, sticky="w", padx=(0, 6), pady=2
        )
        self.scheduler_combo = ttk.Combobox(
            grid,
            textvariable=self.scheduler_var,
            values=self._scheduler_choices,
            state="readonly",
        )
        self.scheduler_combo.grid(row=4, column=1, columnspan=3, sticky="ew", pady=2)
        self._lock_scroll_wheel(self.scheduler_combo)

        self.denoise_label = tk.Label(
            grid, text="Denoise", bg=BG, fg=MUTED, font=("Segoe UI", 9)
        )
        self.denoise_label.grid(row=5, column=0, sticky="w", padx=(0, 6), pady=2)
        self.denoise_spin = ttk.Spinbox(
            grid,
            from_=0.0,
            to=1.0,
            increment=0.05,
            textvariable=self.denoise_var,
            width=6,
        )
        self.denoise_spin.grid(row=5, column=1, sticky="w", pady=2)
        self._lock_scroll_wheel(self.denoise_spin)
        self.denoise_tooltip = Tooltip(self.denoise_spin)
        self.denoise_label_tooltip = Tooltip(self.denoise_label)

        actions = tk.Frame(main, bg=BG)
        actions.pack(fill="x", pady=(12, 0))
        self.generate_btn = tk.Button(
            actions,
            text="Générer",
            command=self._generate,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_ACTIVE,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=9,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self.generate_btn.pack(side="left", fill="x", expand=True)
        tk.Label(
            actions,
            text="×",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=(6, 2))
        self.batch_spin = ttk.Spinbox(
            actions,
            from_=1,
            to=16,
            increment=1,
            textvariable=self.batch_var,
            width=3,
        )
        self.batch_spin.pack(side="left")
        self._lock_scroll_wheel(self.batch_spin)
        self.batch_spin.bind("<KeyRelease>", lambda _event: self._update_generate_state())
        self.batch_spin.bind("<<Increment>>", lambda _event: self._update_generate_state())
        self.batch_spin.bind("<<Decrement>>", lambda _event: self._update_generate_state())
        self.batch_spin.bind("<FocusOut>", lambda _event: self._normalize_batch())
        self.cancel_btn = tk.Button(
            actions,
            text="Annuler",
            command=self._cancel,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=12,
            pady=9,
            state="disabled",
            cursor="hand2",
        )
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.xyz_btn = tk.Button(
            actions,
            text="XYZ Plot…",
            command=self._open_xyz,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=9,
            pady=9,
            font=("Segoe UI", 9),
            cursor="hand2",
        )
        self.xyz_btn.pack(side="left", padx=(8, 0))
        self.action_hint = tk.Label(
            main, text="", bg=BG, fg=YELLOW, anchor="w", font=("Segoe UI", 8)
        )
        self.action_hint.pack(fill="x", pady=(3, 0))

        self.progress_canvas = tk.Canvas(
            main,
            height=24,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.progress_canvas.pack(fill="x", pady=(10, 0))
        self.progress_canvas.bind("<Configure>", lambda _event: self._draw_progress())
        self.progress_label = tk.Label(
            main,
            text="Prêt.",
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9),
        )
        self.progress_label.pack(fill="x", pady=(2, 0))

        gallery_frame = self._section(main, "GALERIE")
        self.gallery_title = tk.Label(
            gallery_frame,
            text="Aucune galerie",
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9),
        )
        self.gallery_title.pack(fill="x")
        gallery_body = tk.Frame(gallery_frame, bg="#111114")
        gallery_body.pack(fill="x", pady=(4, 0))
        self.gallery_canvas = tk.Canvas(
            gallery_body,
            height=160,
            bg="#111114",
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.gallery_scroll = ttk.Scrollbar(
            gallery_body, orient="vertical", command=self.gallery_canvas.yview
        )
        self.gallery_canvas.configure(yscrollcommand=self.gallery_scroll.set)
        self.gallery_scroll.pack(side="right", fill="y")
        self.gallery_canvas.pack(side="left", fill="both", expand=True)
        self.gallery_inner = tk.Frame(self.gallery_canvas, bg="#111114")
        self.gallery_window = self.gallery_canvas.create_window(
            (0, 0), window=self.gallery_inner, anchor="nw"
        )
        self.gallery_inner.bind(
            "<Configure>",
            lambda _event: self.gallery_canvas.configure(
                scrollregion=self.gallery_canvas.bbox("all")
            ),
        )
        self.gallery_canvas.bind(
            "<Configure>", self._on_gallery_canvas_configure
        )
        self._bind_gallery_wheel(self.gallery_canvas)
        self._bind_gallery_wheel(self.gallery_inner)
        self.gallery_hint = tk.Label(
            gallery_frame,
            text="Clique sur une vignette pour appliquer.",
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 8),
        )
        self.gallery_hint.pack(fill="x", pady=(2, 0))

        preview_frame = self._section(main, "APERÇU")
        preview_tools = tk.Frame(preview_frame, bg=BG)
        preview_tools.pack(fill="x")
        self.preview_mode = tk.StringVar(value="result")
        tk.Radiobutton(
            preview_tools,
            text="Document",
            variable=self.preview_mode,
            value="document",
            command=self._load_preview_mode,
            bg=BG,
            fg=MUTED,
            selectcolor=PANEL_2,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 9),
        ).pack(side="left")
        tk.Radiobutton(
            preview_tools,
            text="Crop",
            variable=self.preview_mode,
            value="result",
            command=self._load_preview_mode,
            bg=BG,
            fg=MUTED,
            selectcolor=PANEL_2,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(8, 0))
        self.preview_canvas = tk.Canvas(
            preview_frame,
            width=450,
            height=290,
            bg="#111114",
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.preview_canvas.pack(fill="x", pady=(4, 0))

        log_frame = self._section(main, "JOURNAL")
        self.log_text = tk.Text(
            log_frame,
            height=4,
            wrap="word",
            bg="#141418",
            fg=MUTED,
            insertbackground=FG,
            relief="flat",
            bd=0,
            padx=8,
            pady=6,
            font=("Consolas", 8),
            state="disabled",
        )
        self.log_text.pack(fill="x", pady=(4, 0))

        footer = tk.Frame(main, bg=BG)
        footer.pack(fill="x", pady=(8, 0))
        tk.Label(
            footer,
            text=tr("Config : {path}", path=self.config_path),
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 8),
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            footer,
            text="Ouvrir",
            command=self._open_config,
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            activeforeground=FG,
            relief="flat",
            bd=0,
            font=("Segoe UI", 8),
            cursor="hand2",
        ).pack(side="right")

    def _translate_static_widgets(self, parent: tk.Misc) -> None:
        for child in parent.winfo_children():
            if isinstance(
                child,
                (tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton),
            ):
                try:
                    text = str(child.cget("text"))
                except tk.TclError:
                    text = ""
                if text:
                    try:
                        child.config(text=tr(text))
                    except tk.TclError:
                        pass
            self._translate_static_widgets(child)

    # ------------------------------------------------------------------
    # Profile / settings
    # ------------------------------------------------------------------

    def _profile_label(self) -> str:
        for label, key in self.label_to_key.items():
            if key == self.profile_key:
                return label
        return self.profile_labels[0] if self.profile_labels else ""

    def _mode(self) -> str:
        return "t2i" if self.mode_var.get() == "t2i" else "edit"

    def _update_mode_hint(self) -> None:
        if self._mode() == "t2i":
            self.mode_hint.config(
                text=tr(
                    "T2I ignore la scène : le prompt génère une image au format du "
                    "crop, puis PhotoCraft la masque avec la sélection. Utilise une "
                    "sélection rectangulaire pour un résultat propre."
                )
            )
        else:
            self.mode_hint.config(
                text=tr(
                    "EDIT envoie le crop de la scène au modèle et conserve la "
                    "scène d'origine, même après un passage en T2I."
                )
            )

    def _on_mode_change(self) -> None:
        mode = self._mode()
        if self.running:
            self.mode_var.set(self._last_mode)
            return
        if mode == self._last_mode:
            return
        if mode == "t2i":
            if self.profile_key not in T2I_REFERENCE_PROFILES:
                self._ref_enabled_before_t2i = bool(
                    self.ref_var.get() and self.reference_path
                )
                self.ref_var.set(False)
        else:
            restored = self._reload_session_reference()
            if (
                not restored
                and self._ref_enabled_before_t2i
                and self.reference_path
                and self.reference_path.exists()
                and self._reference_supported()
            ):
                self.ref_var.set(True)
                self._set_session_reference_enabled(True)
        self._sync_mode_defaults(self._last_mode, mode)
        self._last_mode = mode
        self._update_mode_hint()
        self._update_reference_for_profile()
        self._update_denoise_for_profile()
        self._update_generate_state()
        self._check_models()

    def _profile_settings(
        self, key: str, mode: str | None = None
    ) -> dict[str, Any]:
        """Profile defaults from config.toml, then models.json, then the UI."""
        profile = self.manifest["profiles"].get(key, {})
        pcfg = self.cfg.get("profiles", {}).get(key, {})
        settings = profile.get("settings", {})
        mode = mode or self._mode()
        edit_settings = profile.get("edit_settings", {}) if mode == "edit" else {}
        if mode == "edit":
            steps = pcfg.get(
                "edit_steps",
                edit_settings.get(
                    "steps", pcfg.get("steps", settings.get("steps", 16))
                ),
            )
            cfg_value = pcfg.get(
                "edit_cfg",
                edit_settings.get(
                    "cfg", pcfg.get("cfg", settings.get("cfg", 1.0))
                ),
            )
            sampler = pcfg.get(
                "edit_sampler",
                edit_settings.get(
                    "sampler", pcfg.get("sampler", settings.get("sampler", "euler"))
                ),
            )
            scheduler = pcfg.get(
                "edit_scheduler",
                edit_settings.get(
                    "scheduler",
                    pcfg.get("scheduler", settings.get("scheduler", "simple")),
                ),
            )
        else:
            steps = pcfg.get("steps", settings.get("steps", 16))
            cfg_value = pcfg.get("cfg", settings.get("cfg", 1.0))
            sampler = pcfg.get("sampler", settings.get("sampler", "euler"))
            scheduler = pcfg.get(
                "scheduler", settings.get("scheduler", "simple")
            )
        return {
            "padding": pcfg.get("context_padding", 96),
            "feather": pcfg.get("feather", 10),
            "steps": steps,
            "cfg": cfg_value,
            "sampler": sampler,
            "scheduler": scheduler,
            "denoise": pcfg.get("denoise", settings.get("denoise", 1.0)),
        }

    def _sync_mode_defaults(self, previous_mode: str, mode: str) -> None:
        """Move untouched fields to the new mode's profile defaults."""
        if previous_mode == mode:
            return
        old = self._profile_settings(self.profile_key, previous_mode)
        new = self._profile_settings(self.profile_key, mode)
        for var, key in (
            (self.steps_var, "steps"),
            (self.cfg_var, "cfg"),
            (self.sampler_var, "sampler"),
            (self.scheduler_var, "scheduler"),
        ):
            if str(var.get()) == str(old[key]):
                var.set(str(new[key]))

    def _reset_generation_fields(self, *, clear_reference: bool = True) -> None:
        """Clear the prompt/settings for a new selection or a new layer."""
        if self.running:
            return
        values = self._profile_settings(self.profile_key, "edit")
        self.prompt_text.delete("1.0", "end")
        self.neg_text.delete("1.0", "end")
        self.neg_var.set(False)
        self._toggle_negative()
        self.padding_var.set(str(values["padding"]))
        self.feather_var.set(str(values["feather"]))
        self.steps_var.set(str(values["steps"]))
        self.cfg_var.set(str(values["cfg"]))
        self.sampler_var.set(str(values["sampler"]))
        self.scheduler_var.set(str(values["scheduler"]))
        self.denoise_var.set(f"{float(values['denoise']):.2f}")
        self.seed_var.set("-1")
        self.mode_var.set("edit")
        self._last_mode = "edit"
        self._update_mode_hint()
        self._update_denoise_for_profile()
        if clear_reference:
            self._clear_pending_reference()
            self._clear_reference_ui()
        self._update_generate_state()

    def _load_profile(self, key: str) -> None:
        if self._model_manager is not None and getattr(
            self._model_manager, "profile_key", None
        ) != key:
            try:
                if self._model_manager.winfo_exists():
                    self._model_manager.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._model_manager = None
        self.profile_key = key
        label = self._profile_label()
        if label:
            self.profile_var.set(label)
        profile = self.manifest["profiles"].get(key, {})
        values = self._profile_settings(key, self._mode())
        self.padding_var.set(str(values["padding"]))
        self.feather_var.set(str(values["feather"]))
        self.steps_var.set(str(values["steps"]))
        self.cfg_var.set(str(values["cfg"]))
        self.sampler_var.set(str(values["sampler"]))
        self.scheduler_var.set(str(values["scheduler"]))
        self.denoise_var.set(f"{float(values['denoise']):.2f}")
        self.seed_var.set("-1")
        vram = profile.get("vram_gb")
        weights = profile.get("weights_gb")
        detail = tr(
            "{steps} steps · CFG {cfg}",
            steps=self.steps_var.get(),
            cfg=self.cfg_var.get(),
        )
        if weights:
            detail += tr(" · {weights} Go de poids", weights=weights)
        if vram:
            detail += tr(" · ~{vram} Go VRAM", vram=vram)
        if profile.get("recommended"):
            detail += tr(" · recommandé")
        if profile.get("experimental"):
            detail += tr(" · expérimental")
        if profile.get("untested"):
            detail += tr(" · non testé")
        if key not in SUPPORTED_PROFILES:
            detail += tr(" · bientôt disponible")
        self.profile_detail.config(text=detail)
        warning = profile_text(profile, "warning").strip()
        if warning:
            self.profile_warning.config(text=f"⚠ {warning}")
            if not self.profile_warning.winfo_manager():
                self.profile_warning.pack(fill="x", pady=(2, 0))
        else:
            self.profile_warning.config(text="")
            if self.profile_warning.winfo_manager():
                self.profile_warning.pack_forget()
        self._populate_quantizations()
        self._update_mode_hint()
        self._update_reference_for_profile()
        self._update_denoise_for_profile()
        self._load_profile_loras()
        self._update_generate_state()
        self._update_krea_node_label()
        self._check_models()

    def _update_denoise_for_profile(self) -> None:
        if not hasattr(self, "denoise_spin"):
            return
        if self._mode() != "edit":
            self.denoise_label.grid_remove()
            self.denoise_spin.grid_remove()
            self._set_denoise_tooltip("")
            return
        self.denoise_label.grid()
        self.denoise_spin.grid()
        supported = self.profile_key in DENOISE_PROFILES
        self.denoise_spin.config(state="normal" if supported else "disabled")
        if not supported:
            self.denoise_var.set("1.00")
        text = (
            tr(
                "1.0 = édition complète. En dessous, le résultat conserve "
                "davantage l'image source ; 0.8-1.0 recommandé avec FLUX.2 Klein."
            )
            if supported
            else tr(
                "Fixé à 1.0 : ce modèle part d'un latent vide ; un denoise "
                "partiel produirait des artefacts."
            )
        )
        self._set_denoise_tooltip(text)

    def _set_denoise_tooltip(self, text: str) -> None:
        if hasattr(self, "denoise_tooltip"):
            self.denoise_tooltip.set_text(text)
        if hasattr(self, "denoise_label_tooltip"):
            self.denoise_label_tooltip.set_text(text)

    def _populate_quantizations(self) -> None:
        profile = self.manifest["profiles"].get(self.profile_key, {})
        pcfg = self.cfg.get("profiles", {}).get(self.profile_key, {})
        spec = (profile.get("files") or {}).get("unet", {})
        options = spec.get("quantizations") or profile.get("quantizations") or []
        current = resolve_filename(self.profile_key, "unet", pcfg, profile)
        self.quant_map = {}
        if not current:
            if self.quant_frame.winfo_manager():
                self.quant_frame.pack_forget()
            return
        labels: list[str] = []

        def add(filename: object, preferred: object = None) -> str:
            value = str(filename or "").strip()
            label = str(preferred or "").strip()
            if not label:
                label = quantization_label(value)
            if not label:
                label = tr(
                    "Personnalisé : {filename}",
                    filename=Path(value.replace("\\", "/")).name,
                )
            base = label
            if label in self.quant_map and not same_model_file(
                self.quant_map[label], value
            ):
                display_name = Path(value.replace("\\", "/")).name
                label = f"{base} · {display_name}"
            index = 2
            while label in self.quant_map and not same_model_file(
                self.quant_map[label], value
            ):
                label = f"{base} ({index})"
                index += 1
            if label not in self.quant_map:
                self.quant_map[label] = value
                labels.append(label)
            return label

        for option in options:
            add(option.get("filename", "?"), option.get("label"))

        # ComfyUI knows about files downloaded outside StableCraft too. Show
        # the same model family (Q4/Q8/BF16…) even when models.json has no
        # quantization list for this profile.
        family = model_family_key(current)
        visible = (
            self._comfy_model_files.get("unet", [])
            if self._comfy_model_files_key == self.profile_key
            else []
        )
        for filename in visible:
            if same_model_file(filename, current):
                continue
            if model_family_key(filename) != family:
                continue
            add(filename)

        current_label = next(
            (
                label
                for label, filename in self.quant_map.items()
                if same_model_file(filename, current)
            ),
            None,
        )
        if current_label is None:
            current_label = add(current)
        if current_label in labels:
            labels.remove(current_label)
            labels.insert(0, current_label)
        self.quant_var.set(current_label)
        self.quant_combo.config(values=labels)
        if not self.quant_frame.winfo_manager():
            self.quant_frame.pack(fill="x", pady=(3, 0))
        self.quant_combo.config(state="disabled" if self.running else "readonly")

    def _on_quant_change(self, _event: object = None) -> None:
        filename = self.quant_map.get(self.quant_var.get())
        if not filename:
            return
        if same_model_file(
            filename,
            resolve_filename(
                self.profile_key,
                "unet",
                self.cfg.get("profiles", {}).get(self.profile_key, {}),
                self.manifest["profiles"].get(self.profile_key, {}),
            ),
        ):
            return
        set_selected_file(self.profile_key, "unet", filename)
        self._log(tr("Quantification : {filename}", filename=filename))
        self._update_generate_state()
        self._check_models()

    @staticmethod
    def _same_selection(
        left: list[int] | None, right: list[int] | None, tolerance: int = 2,
    ) -> bool:
        if not left or not right or len(left) != len(right):
            return False
        try:
            return all(
                abs(int(a) - int(b)) <= tolerance
                for a, b in zip(left, right)
            )
        except (TypeError, ValueError):
            return False

    def _reusable_session(self) -> bool:
        return bool(
            self.session_id
            and self.session_data
            and (
                not self.current_selection
                or self._same_selection(
                    self.current_selection, self.session_data.get("selection")
                )
            )
        )

    def _batch_count(self) -> int:
        try:
            value = int(float(self.batch_var.get().replace(",", ".")))
        except (TypeError, ValueError):
            value = 1
        return max(1, min(16, value))

    def _normalize_batch(self) -> None:
        self.batch_var.set(str(self._batch_count()))
        self._update_generate_state()

    def _form_values(self) -> dict[str, Any] | None:
        try:
            reference = self._reference_active_path()
            denoise = float(self.denoise_var.get().replace(",", "."))
            if self._mode() != "edit" or self.profile_key not in DENOISE_PROFILES:
                denoise = 1.0
            if not self.sampler_var.get() or not self.scheduler_var.get():
                return None
            return {
                "seed": int(self.seed_var.get().strip()),
                "steps": int(self.steps_var.get()),
                "cfg": float(self.cfg_var.get().replace(",", ".")),
                "sampler": self.sampler_var.get(),
                "scheduler": self.scheduler_var.get(),
                "denoise": denoise,
                "padding": int(self.padding_var.get()),
                "feather": int(self.feather_var.get()),
                "profile": self.profile_key,
                "mode": self._mode(),
                "prompt": self.prompt_text.get("1.0", "end").strip(),
                "negative": (
                    self.neg_text.get("1.0", "end").strip() if self.neg_var.get() else ""
                ),
                "reference": reference.name if reference else None,
                "loras": self._loras_signature(),
            }
        except (TypeError, ValueError):
            return None

    def _duplicate_generation(self) -> int | None:
        """Return the gallery index that already has these exact settings."""
        values = self._form_values()
        if values is None or values["seed"] < 0 or not self.session_data:
            return None
        for index, generation in enumerate(self.session_data.get("generations", [])):
            try:
                same = (
                    int(generation.get("seed", -1)) == values["seed"]
                    and str(generation.get("profile", "")) == values["profile"]
                    and str(generation.get("mode", "edit")) == values["mode"]
                    and str(generation.get("prompt", "")).strip() == values["prompt"]
                    and str(generation.get("negative", "")).strip() == values["negative"]
                    and int(generation.get("steps", -1)) == values["steps"]
                    and abs(float(generation.get("cfg", -1)) - values["cfg"]) < 1e-6
                    and str(generation.get("sampler") or "euler") == values["sampler"]
                    and str(generation.get("scheduler") or "simple")
                    == values["scheduler"]
                    and abs(
                        float(generation.get("denoise", 1.0)) - values["denoise"]
                    )
                    < 1e-6
                    and int(generation.get("padding", -1)) == values["padding"]
                    and str(generation.get("reference") or "")
                    == str(values.get("reference") or "")
                    and lora_signature(generation.get("loras") or [])
                    == values["loras"]
                )
            except (TypeError, ValueError):
                continue
            if same:
                return index
        return None

    def _update_generate_state(self) -> None:
        values = self._form_values()
        batch = self._batch_count()
        duplicate = self._duplicate_generation() if batch == 1 else None
        reuse = self._reusable_session()
        has_input = self.has_selection or reuse
        if not self.models_ok:
            enabled = (
                not self.running
                and self.profile_key in SUPPORTED_PROFILES
            )
        else:
            enabled = (
                not self.running
                and self.profile_key in SUPPORTED_PROFILES
                and self.pc_ok
                and self.comfy_ok
                and has_input
                and values is not None
                and duplicate is None
            )
        if not self.models_ok:
            button_text = tr("Gérer les modèles")
        else:
            button_text = tr("Régénérer") if reuse else tr("Générer")
        self.generate_btn.config(
            text=button_text,
            state="normal" if enabled else "disabled",
            bg=ACCENT if enabled else PANEL_2,
        )
        if duplicate is not None:
            self.action_hint.config(
                text=tr(
                    "Cette combinaison existe déjà (#{index}). Mets le seed à -1 "
                    "ou change le prompt.",
                    index=duplicate + 1,
                )
            )
        elif values is None:
            self.action_hint.config(
                text=tr("Vérifie les réglages (seed, steps, CFG…).")
            )
        elif not self.models_ok:
            self.action_hint.config(
                text=tr("Modèles manquants — le bouton ouvre le gestionnaire.")
            )
        elif not has_input:
            self.action_hint.config(
                text=tr(
                    "Fais un lasso, ou sélectionne un calque StableCraft pour régénérer."
                )
            )
        else:
            self.action_hint.config(text="")
        radio_state = "disabled" if self.running else "normal"
        self.edit_radio.config(state=radio_state)
        self.t2i_radio.config(state=radio_state)
        self.profile_manage_btn.config(state="disabled" if self.running else "normal")
        self.batch_spin.config(state="disabled" if self.running else "normal")
        self.xyz_btn.config(state="disabled" if self.running else "normal")
        for name in ("ref_choose", "ref_paste"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.config(state="disabled" if self.running else "normal")
        if hasattr(self, "ref_remove"):
            self.ref_remove.config(
                state=(
                    "disabled"
                    if self.running or not self.reference_path
                    else "normal"
                )
            )
        if self.quant_frame.winfo_manager():
            self.quant_combo.config(state="disabled" if self.running else "readonly")

    def _on_profile_change(self, _event: object = None) -> None:
        label = self.profile_var.get()
        key = self.label_to_key.get(label)
        if key and key != self.profile_key:
            self._load_profile(key)

    def _toggle_negative(self) -> None:
        if self.neg_var.get():
            if not self._neg_visible:
                self.neg_text.pack(fill="x", pady=(4, 0))
                self._neg_visible = True
        elif self._neg_visible:
            self.neg_text.pack_forget()
            self._neg_visible = False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _refresh_loop(self) -> None:
        pc_cfg = self.cfg["photocraft"]
        comfy_cfg = self.cfg["comfyui"]
        endpoint = str(comfy_cfg["endpoint"])
        while not self.stop_event.is_set():
            pc: dict[str, Any] = {
                "ok": False,
                "text": tr("PhotoCraft : déconnecté"),
                "doc": None,
                "doc_index": None,
            }
            client = None
            try:
                token = read_token(Path(pc_cfg["control_token_file"]))
                client = ControlClient(
                    str(pc_cfg["control_host"]),
                    int(pc_cfg["control_port"]),
                    token,
                    timeout=6.0,
                )
                ui = client.request("ui.inspect")
                doc = ui.get("document")
                if doc:
                    inspect = client.execute("document.inspect")
                    pc = {
                        "ok": True,
                        "text": tr("PhotoCraft : connecté"),
                        "doc": inspect,
                        "doc_index": (ui.get("session") or {}).get("active"),
                    }
                else:
                    pc = {
                        "ok": True,
                        "text": tr("PhotoCraft : connecté (aucun document)"),
                        "doc": None,
                        "doc_index": None,
                    }
            except Exception as exc:  # noqa: BLE001 - status must never crash the UI
                pc["text"] = tr("PhotoCraft : {error}", error=short_error(exc))
            finally:
                if client is not None:
                    client.close_socket()

            comfy: dict[str, Any] = {
                "ok": False,
                "text": tr("ComfyUI : déconnecté"),
            }
            try:
                stats = comfy_json(endpoint, "/system_stats", timeout=3.0)
                system = stats.get("system", {})
                devices = stats.get("devices", [])
                gpu = devices[0].get("name", "") if devices else ""
                vram = devices[0].get("vram_free", 0) / 1e9 if devices else 0
                comfy = {
                    "ok": True,
                    "text": tr(
                        "ComfyUI : {version} · {gpu} · {vram} Go libres",
                        version=system.get("comfyui_version", "?"),
                        gpu=gpu,
                        vram=f"{vram:.1f}",
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                comfy["text"] = tr("ComfyUI : {error}", error=short_error(exc))

            self.queue.put(("status", pc, comfy))
            self.stop_event.wait(3.0)

    def _check_models(self) -> None:
        key = self.profile_key
        mode = self._mode()
        self.models_checked = False
        threading.Thread(
            target=self._check_models_loop,
            args=(key, mode),
            daemon=True,
        ).start()

    def _check_models_loop(self, key: str, mode: str) -> None:
        profile = self.manifest["profiles"].get(key, {})
        pcfg = self.cfg.get("profiles", {}).get(key, {})
        files = profile.get("files", {})
        endpoint = str(self.cfg["comfyui"]["endpoint"])
        missing: list[dict[str, Any]] = []
        error: str | None = None

        def add_missing(kind: str, filename: str, note: str = "") -> None:
            if any(
                item.get("kind") == kind and item.get("filename") == filename
                for item in missing
            ):
                return
            spec = files.get(kind, {}) if kind in files else {}
            missing.append(
                {
                    "kind": kind,
                    "label": {
                        "unet": "UNet",
                        "lora": "LoRA",
                        "text_encoder": "Text encoder",
                        "vae": "VAE",
                        "node": "Custom node",
                    }.get(kind, kind),
                    "filename": filename,
                    "note": note or str(spec.get("note", "") or ""),
                    "folder": str(spec.get("folder", "") or ""),
                    "options": (
                        download_options(key, kind, profile, filename)
                        if kind != "node"
                        else []
                    ),
                }
            )

        model_files: dict[str, list[str]] = {}

        def visible_files(kind: str) -> list[str]:
            loaders = {
                "unet": (("UnetLoaderGGUF", "unet_name"), ("UNETLoader", "unet_name")),
                "text_encoder": (
                    ("CLIPLoader", "clip_name"),
                    ("CLIPLoaderGGUF", "clip_name"),
                ),
                "vae": (("VAELoader", "vae_name"),),
            }.get(kind, ())
            found: list[str] = []
            errors: list[Exception] = []
            loaded = False
            for loader, key_name in loaders:
                try:
                    options = comfy_options(endpoint, loader, key_name)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
                    continue
                loaded = True
                for option in options:
                    if option not in found:
                        found.append(option)
            if not loaded and errors:
                raise errors[0]
            return found

        try:
            if key in SUPPORTED_PROFILES:
                unet = resolve_filename(key, "unet", pcfg, profile)
                clip = resolve_filename(key, "text_encoder", pcfg, profile)
                vae = resolve_filename(key, "vae", pcfg, profile)
                model_files = {
                    "unet": visible_files("unet"),
                    "text_encoder": visible_files("text_encoder"),
                    "vae": visible_files("vae"),
                }
                if unet.lower().endswith(".gguf") and not comfy_node_exists(
                    endpoint, "UnetLoaderGGUF"
                ):
                    add_missing(
                        "node",
                        "ComfyUI-GGUF",
                        "ComfyUI-GGUF est requis pour charger ce modèle GGUF. "
                        "Installe le nœud puis redémarre ComfyUI.",
                    )
                if clip.lower().endswith(".gguf") and not comfy_node_exists(
                    endpoint, "CLIPLoaderGGUF"
                ):
                    add_missing(
                        "node",
                        "ComfyUI-GGUF",
                        "ComfyUI-GGUF est requis pour charger ce text encoder GGUF. "
                        "Installe le nœud puis redémarre ComfyUI.",
                    )
                def visible(kind: str, filename: str) -> bool:
                    return any(
                        same_model_file(option, filename)
                        for option in model_files.get(kind, [])
                    )

                if not visible("unet", unet):
                    add_missing("unet", unet)
                if not visible("text_encoder", clip):
                    add_missing("text_encoder", clip)
                if not visible("vae", vae):
                    add_missing("vae", vae)
                if files.get("lora") and mode == "edit":
                    lora = resolve_filename(key, "lora", pcfg, profile)
                    lora_options = comfy_options(
                        endpoint, "LoraLoaderModelOnly", "lora_name"
                    )
                    if not any(
                        same_model_file(option, lora) for option in lora_options
                    ):
                        add_missing("lora", lora)
                if key == MOSS_PROFILE and mode == "edit":
                    if not comfy_node_exists(
                        endpoint, "TextEncodeMOSSImageEdit"
                    ):
                        add_missing(
                            "node",
                            "TextEncodeMOSSImageEdit",
                            "Le nœud MOSS-Image Edit est natif dans "
                            "ComfyUI 0.43+ ; mets ComfyUI à jour.",
                        )
                needs_edit_nodes = mode == "edit" and key in KREA_PROFILES
                if needs_edit_nodes or key == QWEN_PROFILE:
                    for node in profile.get("requires_nodes", []):
                        if not comfy_node_exists(endpoint, node):
                            add_missing("node", node, "Nœud ComfyUI manquant.")
                if needs_edit_nodes or (key == "krea2_edit" and mode == "t2i"):
                    if not comfy_node_exists(endpoint, "EmptySD3LatentImage"):
                        add_missing("node", "EmptySD3LatentImage", "Nœud ComfyUI manquant.")
        except Exception as exc:  # noqa: BLE001
            error = short_error(exc)
        if error is None and model_files:
            self.queue.put(("model_files", key, model_files))
        if error is None and not self._sampler_choices_loaded:
            try:
                samplers = comfy_options(endpoint, "KSampler", "sampler_name")
                schedulers = comfy_options(endpoint, "KSampler", "scheduler")
            except Exception:  # noqa: BLE001
                samplers, schedulers = [], []
            if samplers and schedulers:
                self._sampler_choices_loaded = True
                self.queue.put(("samplers", samplers, schedulers))
        self.queue.put(("models", key, mode, missing, error))

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "status":
                    self._handle_status(item[1], item[2])
                elif kind == "models":
                    self._handle_models(item[1], item[2], item[3], item[4])
                elif kind == "model_files":
                    self._comfy_model_files_key = str(item[1])
                    self._comfy_model_files = {
                        str(name): [str(value) for value in values]
                        for name, values in (item[2] or {}).items()
                    }
                    self._populate_quantizations()
                    if self._model_manager is not None:
                        try:
                            if self._model_manager.winfo_exists():
                                self._model_manager.refresh()
                        except Exception:  # noqa: BLE001
                            pass
                elif kind == "samplers":
                    samplers = [str(value) for value in item[1]]
                    schedulers = [str(value) for value in item[2]]
                    if samplers and schedulers:
                        self._sampler_choices = samplers
                        self._scheduler_choices = schedulers
                        if hasattr(self, "sampler_combo"):
                            self.sampler_combo.config(values=samplers)
                            self.scheduler_combo.config(values=schedulers)
                            if self.sampler_var.get() not in samplers:
                                self.sampler_var.set(samplers[0])
                            if self.scheduler_var.get() not in schedulers:
                                self.scheduler_var.set(schedulers[0])
                elif kind == "progress":
                    self._handle_progress(item[1])
                elif kind.startswith("xyz_"):
                    if self.xyz_window is not None:
                        try:
                            if self.xyz_window.winfo_exists():
                                self.xyz_window.handle_event(kind, str(item[1]))
                        except Exception:  # noqa: BLE001
                            pass
                elif kind == "log":
                    self._log(str(item[1]))
                elif kind == "drop":
                    self._on_dropped_file(str(item[1]))
                elif kind == "preview":
                    self.preview_paths["document"] = str(item[1])
                    if self.preview_mode.get() == "document":
                        self._load_preview(str(item[1]))
                elif kind == "result":
                    self.preview_paths["result"] = str(item[1])
                    if self.preview_mode.get() == "result":
                        self._load_preview(str(item[1]))
                elif kind == "session_line":
                    self.pending_session_id = str(item[1])
                elif kind == "generation_line":
                    self.pending_generation = int(item[1])
                    if self.running:
                        self._refresh_running_session()
                        if self.job_kind != "xyz":
                            self._set_progress(
                                self.progress_value,
                                tr("Application dans PhotoCraft…"),
                            )
                elif kind == "update":
                    version = str(item[1])
                    self.update_url = str(item[2])
                    self.update_label.config(
                        text=tr(
                            "Mise à jour disponible : v{version} — ouvrir la page Releases",
                            version=version,
                        )
                    )
                elif kind == "krea_node":
                    self.krea_status = item[1]
                    self.krea_latest = item[2]
                    self._update_krea_node_label()
                elif kind == "error":
                    self.last_error = str(item[1])
                elif kind == "done":
                    self._finish(int(item[1]))
        except queue.Empty:
            pass
        if not self._closing:
            self.after(100, self._poll_queue)

    def _handle_status(self, pc: dict[str, Any], comfy: dict[str, Any]) -> None:
        self.pc_status.config(text=pc["text"], fg=GREEN if pc["ok"] else RED)
        self.comfy_status.config(text=comfy["text"], fg=GREEN if comfy["ok"] else RED)
        doc = pc.get("doc")
        if pc.get("ok"):
            self.current_selection = (
                list(doc["selectionBounds"])
                if doc and doc.get("hasSelection") and doc.get("selectionBounds")
                else None
            )
            self._sync_session_from_doc(doc, pc.get("doc_index"))
            if self.reference_is_pending and self.current_selection:
                if self.pending_reference_selection is None:
                    self.pending_reference_selection = list(self.current_selection)
                elif not self._same_selection(
                    self.pending_reference_selection, self.current_selection
                ):
                    self._clear_pending_reference()
        if doc:
            self.doc_status.config(
                text=tr(
                    "Document : {name} · {width}×{height} · {mode}/{depth} bits",
                    name=doc.get("name", "?"),
                    width=doc.get("width"),
                    height=doc.get("height"),
                    mode=doc.get("mode"),
                    depth=doc.get("depth"),
                ),
                fg=MUTED,
            )
            if doc.get("hasSelection"):
                x, y, w, h = doc.get("selectionBounds") or [0, 0, 0, 0]
                self.sel_status.config(
                    text=tr(
                        "Sélection : {width}×{height} à ({x},{y})",
                        width=w,
                        height=h,
                        x=x,
                        y=y,
                    ),
                    fg=GREEN,
                )
            elif self.session_id:
                self.sel_status.config(
                    text=tr("Sélection : aucune — galerie disponible"), fg=YELLOW
                )
            else:
                self.sel_status.config(
                    text=tr("Sélection : aucune — fais un lasso"), fg=YELLOW
                )
        else:
            self.doc_status.config(text=tr("Document : aucun"), fg=MUTED)
            self.sel_status.config(text=tr("Sélection : —"), fg=MUTED)
        was_comfy = self.comfy_ok
        self.pc_ok = bool(pc["ok"])
        self.comfy_ok = bool(comfy["ok"])
        if self.comfy_ok and not was_comfy and self.models_error is not None:
            self._check_models()
        self.has_selection = bool(doc and doc.get("hasSelection"))
        self._update_generate_state()

    def _handle_models(
        self, key: str, mode: str, missing: list[dict[str, Any]], error: str | None
    ) -> None:
        if key != self.profile_key or mode != self._mode():
            return
        self.models_checked = True
        self.missing_models = list(missing)
        self.models_error = error
        if error:
            self.models_ok = False
            self.models_status.config(
                text=tr("Modèles : vérification impossible ({error})", error=error),
                fg=YELLOW,
                cursor="hand2",
            )
            self._update_generate_state()
            if self._model_manager is not None:
                try:
                    if self._model_manager.winfo_exists():
                        self._model_manager.refresh()
                except Exception:  # noqa: BLE001
                    pass
            return
        if missing:
            self.models_ok = False
            names = ", ".join(str(item.get("label", "?")) for item in missing[:3])
            if len(missing) > 3:
                names += f" (+{len(missing) - 3})"
            self.models_status.config(
                text=tr("Modèles manquants : {names} — cliquer pour gérer", names=names),
                fg=RED,
                cursor="hand2",
            )
        else:
            self.models_ok = True
            self.models_status.config(
                text=tr("Modèles : OK"), fg=GREEN, cursor="arrow"
            )
        self._update_generate_state()
        self._populate_quantizations()
        if self._model_manager is not None:
            try:
                if self._model_manager.winfo_exists():
                    self._model_manager.refresh()
            except Exception:  # noqa: BLE001
                pass

    def _open_xyz(self) -> None:
        if self.running:
            return
        if not self.pc_ok or not self.comfy_ok:
            messagebox.showwarning(
                tr("XYZ Plot"),
                tr("PhotoCraft et ComfyUI doivent être connectés."),
            )
            return
        if not self.models_ok:
            self._open_model_manager()
            return
        if not (self.has_selection or self._reusable_session()):
            messagebox.showwarning(
                tr("Sélection vide"),
                tr(
                    "Fais un lasso, ou sélectionne un calque StableCraft pour "
                    "utiliser sa sélection d'origine."
                ),
            )
            return
        if not self.prompt_text.get("1.0", "end").strip():
            messagebox.showwarning(
                tr("Prompt vide"),
                tr("Écris le prompt à comparer dans la fenêtre principale."),
            )
            return
        if self.xyz_window is not None:
            try:
                if self.xyz_window.winfo_exists():
                    self.xyz_window.deiconify()
                    self.xyz_window.lift()
                    self.xyz_window.focus_force()
                    return
            except Exception:  # noqa: BLE001
                pass
        from xyz_plot_ui import XYZPlotWindow  # noqa: PLC0415

        self.xyz_window = XYZPlotWindow(self)

    def _start_xyz_bridge(self, job_path: Path, label: str) -> None:
        if self.running:
            return
        python, error = self._comfy_python()
        if error:
            messagebox.showerror(tr("Python ComfyUI introuvable"), error)
            return
        bridge = ROOT / "prototypes" / "bridge_cli.py"
        if not bridge.exists():
            messagebox.showerror(tr("Bridge introuvable"), str(bridge))
            return
        command = [
            python,
            str(bridge),
            "--config",
            str(self.config_path),
            "--xyz-job",
            str(job_path),
        ]
        self.job_kind = "xyz"
        self._start_bridge(command, label)
        if not self.running:
            self.job_kind = "generate"

    def _on_xyz_closed(self, window: Any) -> None:
        if self.xyz_window is window:
            self.xyz_window = None

    def _open_model_manager(self) -> None:
        from model_manager import ModelManager  # noqa: PLC0415 - avoids import cycle

        if self._model_manager is not None:
            try:
                if self._model_manager.winfo_exists():
                    if getattr(self._model_manager, "profile_key", None) != self.profile_key:
                        # The window title and file rows are built for one
                        # profile; recreate it instead of showing stale files.
                        self._model_manager.destroy()
                        self._model_manager = None
                    else:
                        self._model_manager.deiconify()
                        self._model_manager.lift()
                        self._model_manager.focus_force()
                        if hasattr(self._model_manager, "refresh"):
                            self._model_manager.refresh()
                        return
            except Exception:  # noqa: BLE001
                pass
        self._model_manager = ModelManager(self)

    def _model_store_dir(self) -> Path:
        configured = str(self.cfg.get("models", {}).get("store_dir", "") or "")
        path = Path(configured) if configured else ROOT / "models"
        return path if path.is_absolute() else ROOT / path

    def _visible_model_options(self, kind: str, filename: str) -> list[str]:
        endpoint = str(self.cfg["comfyui"]["endpoint"])
        loader_keys: list[tuple[str, str]] = []
        if kind == "unet":
            loader = "UnetLoaderGGUF" if filename.lower().endswith(".gguf") else "UNETLoader"
            loader_keys.append((loader, "unet_name"))
        elif kind == "lora":
            loader_keys.append(("LoraLoaderModelOnly", "lora_name"))
        elif kind == "text_encoder":
            loader_keys.append(("CLIPLoader", "clip_name"))
            loader_keys.append(("CLIPLoaderGGUF", "clip_name"))
        elif kind == "vae":
            loader_keys.append(("VAELoader", "vae_name"))
        found: list[str] = []
        for loader, key in loader_keys:
            try:
                options = comfy_options(endpoint, loader, key)
            except Exception:  # noqa: BLE001
                continue
            for option in options:
                if option == filename or Path(option).name == filename:
                    if option not in found:
                        found.append(option)
        return found

    def _comfy_running(self) -> bool:
        return bool(self.comfy_ok)

    # ------------------------------------------------------------------
    # Reference image
    # ------------------------------------------------------------------

    def _reference_supported(self) -> bool:
        if self.profile_key not in REFERENCE_PROFILES:
            return False
        if self._mode() == "t2i":
            return self.profile_key in T2I_REFERENCE_PROFILES
        return True

    def _reference_help(self) -> str:
        if self.profile_key not in REFERENCE_PROFILES:
            return tr(
                "Disponible sur Krea 2, FLUX.2 Klein 9B, FLUX.3 Klein et Qwen Image 2.1."
            )
        if self._mode() == "t2i":
            if self.profile_key == MOSS_PROFILE:
                return tr(
                    "MOSS-Image utilise la référence en EDIT ; en T2I, le modèle "
                    "ne prend pas d'image."
                )
            if self.profile_key in KREA_PROFILES:
                return tr(
                    "Krea 2 utilise la référence en EDIT ; en T2I, passe en EDIT "
                    "pour une génération guidée par l'image."
                )
            return tr("La référence guide la génération T2I.")
        return tr(
            "Disponible sur Krea 2, FLUX.2 Klein 9B, FLUX.3 Klein et Qwen Image 2.1."
        )

    def _update_reference_for_profile(self) -> None:
        supported = self._reference_supported()
        self.ref_check.config(
            state="normal" if supported and not self.running else "disabled"
        )
        if supported:
            self.ref_profile_hint.config(text="")
            if self.ref_var.get():
                self._show_reference_panel()
            else:
                self._hide_reference_panel()
        else:
            self.ref_profile_hint.config(text=self._reference_help())
            self._hide_reference_panel()
        self._update_reference_hint()

    def _show_reference_panel(self) -> None:
        if not self.ref_panel.winfo_manager():
            self.ref_panel.pack(fill="x", pady=(4, 0))

    def _hide_reference_panel(self) -> None:
        if self.ref_panel.winfo_manager():
            self.ref_panel.pack_forget()

    def _toggle_reference(self) -> None:
        if self.running:
            return
        if not self._reference_supported():
            self.ref_var.set(False)
            self.ref_profile_hint.config(text=self._reference_help())
            return
        enabled = bool(self.ref_var.get())
        if enabled:
            self._show_reference_panel()
        else:
            self._hide_reference_panel()
        self._set_session_reference_enabled(enabled)
        self._update_reference_hint()

    def _set_session_reference_enabled(self, enabled: bool) -> None:
        if not self.session_id or not self.session_data:
            return
        reference = self.session_data.get("reference")
        if isinstance(reference, dict):
            reference["enabled"] = enabled
            try:
                self.session_store.save(self.session_data)
            except Exception as exc:  # noqa: BLE001
                self._log(f"Référence : {short_error(exc)}")

    def _update_reference_hint(self) -> None:
        if not self._reference_supported():
            return
        if self.reference_path and self.reference_path.exists():
            self.ref_hint.config(
                text=(
                    tr(
                        "Image de référence pour le T2I. Décris ce que tu veux "
                        "en reprendre."
                    )
                    if self._mode() == "t2i"
                    else tr(
                        "Image 2 = référence. Décris dans le prompt ce que tu veux "
                        "en reprendre."
                    )
                )
            )
        else:
            self.ref_hint.config(text=tr("Clique ou dépose une image ici."))

    def _draw_reference_tile(self) -> None:
        self.ref_canvas.delete("all")
        if self.reference_thumb_image is not None:
            self.ref_canvas.create_image(56, 56, image=self.reference_thumb_image)
        else:
            self.ref_canvas.create_text(
                56,
                48,
                text="+ Image",
                fill=MUTED,
                font=("Segoe UI", 10, "bold"),
            )
            self.ref_canvas.create_text(
                56,
                70,
                text=tr("Clique ou dépose"),
                fill=MUTED,
                font=("Segoe UI", 7),
            )
        self.ref_name.config(text=self.reference_name or tr("Aucune image"))
        self.ref_remove.config(
            state="normal" if self.reference_path else "disabled"
        )
        self._update_reference_hint()

    def _display_reference(
        self,
        image_path: Path,
        thumb_path: Path,
        name: str,
        enabled: bool,
        *,
        pending: bool,
    ) -> None:
        self.reference_path = image_path
        self.reference_name = name
        self.reference_is_pending = pending
        if not pending:
            self.pending_reference_selection = None
        self.reference_thumb_image = None
        source = thumb_path if thumb_path.exists() else image_path
        try:
            image = tk.PhotoImage(file=str(source))
            factor = max(
                1, math.ceil(max(image.width() / 104, image.height() / 104))
            )
            if factor > 1:
                image = image.subsample(factor, factor)
            self.reference_thumb_image = image
        except Exception as exc:  # noqa: BLE001
            self._log(f"Référence : aperçu indisponible ({short_error(exc)})")
        self.ref_var.set(enabled)
        self._draw_reference_tile()
        if enabled and self._reference_supported():
            self._show_reference_panel()
        else:
            self._hide_reference_panel()

    def _reload_session_reference(self) -> bool:
        """Restore the layer's reference when coming back from T2I to EDIT."""
        if not self.session_id or not self.session_data or not self._reference_supported():
            return False
        reference = self.session_data.get("reference")
        if not isinstance(reference, dict):
            return False
        directory = self.session_store.directory(str(self.session_id))
        image_path = directory / str(reference.get("image", "reference.png"))
        thumb_path = directory / str(reference.get("thumb", "reference_thumb.png"))
        if not image_path.exists():
            return False
        name = str(reference.get("name") or tr("Image de référence"))
        if name == "reference.png":
            name = tr("Image de référence")
        self._display_reference(
            image_path,
            thumb_path,
            name,
            bool(reference.get("enabled", True)),
            pending=False,
        )
        return True

    def _load_reference_for_session(self) -> None:
        generations = self.session_data.get("generations", []) if self.session_data else []
        current = int(self.session_data.get("current", -1)) if self.session_data else -1
        used_by_current = (
            0 <= current < len(generations)
            and bool(generations[current].get("reference"))
        )
        if not used_by_current:
            # The session may still keep reference.png for future use, but the
            # UI must not show it again if the latest generation did not use it.
            self._clear_reference_ui()
            return

        reference = self.session_data.get("reference") if self.session_data else None
        if isinstance(reference, dict):
            directory = self.session_store.directory(str(self.session_id))
            image_path = directory / str(reference.get("image", "reference.png"))
            thumb_path = directory / str(
                reference.get("thumb", "reference_thumb.png")
            )
            if image_path.exists():
                name = str(reference.get("name") or tr("Image de référence"))
                if name == "reference.png":
                    name = tr("Image de référence")
                self._display_reference(
                    image_path,
                    thumb_path,
                    name,
                    True,
                    pending=False,
                )
                return
        self._clear_reference_ui()

    def _clear_reference_ui(self) -> None:
        self.reference_path = None
        self.reference_name = None
        self.reference_thumb_image = None
        self.reference_is_pending = False
        self.pending_reference_selection = None
        self.ref_var.set(False)
        self._hide_reference_panel()
        self._draw_reference_tile()

    def _pending_files(self) -> tuple[Path, Path]:
        root = self._pending_root()
        return root / "reference.png", root / "reference_thumb.png"

    def _clear_pending_reference(self) -> None:
        if self.reference_is_pending:
            for path in self._pending_files():
                try:
                    path.unlink()
                except OSError:
                    pass
        if not self.session_id:
            self._clear_reference_ui()

    def _choose_reference(self) -> None:
        if self.running:
            return
        if not self._reference_supported():
            messagebox.showinfo(
                tr("Image de référence"),
                self._reference_help(),
            )
            return
        selected = filedialog.askopenfilename(
            title=tr("Choisir une image de référence"),
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                (tr("Tous les fichiers"), "*.*"),
            ],
        )
        if selected:
            self._set_reference_from_source(Path(selected))

    def _paste_reference(self) -> None:
        if self.running:
            return
        if not self._reference_supported():
            messagebox.showinfo(tr("Image de référence"), self._reference_help())
            return
        python, error = self._comfy_python()
        if error:
            messagebox.showerror(tr("Python ComfyUI introuvable"), error)
            return
        script = ROOT / "prototypes" / "clipboard_image.py"
        if not script.exists():
            messagebox.showerror(tr("Presse-papiers"), str(script))
            return
        output = self._pending_root() / "clipboard.png"
        flags = 0x08000000 if os.name == "nt" else 0
        try:
            result = subprocess.run(
                [python, str(script), "--output", str(output)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(tr("Presse-papiers"), short_error(exc))
            return
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            messagebox.showerror(
                tr("Presse-papiers"),
                tr(
                    "Impossible de lire le presse-papiers.\n\n{details}",
                    details=details[:800],
                ),
            )
            return
        try:
            info = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            info = {}
        path = Path(str(info.get("path") or output))
        if not path.exists():
            messagebox.showerror(
                tr("Presse-papiers"),
                tr("Le presse-papiers ne contient pas d'image."),
            )
            return
        display = (
            path.name
            if str(info.get("source") or "") == "file"
            else tr("Presse-papiers") + ".png"
        )
        self._set_reference_from_source(path, display_name=display)

    def _set_reference_from_source(
        self, source: Path, display_name: str | None = None
    ) -> None:
        if self.running:
            return
        if not self._reference_supported():
            messagebox.showinfo(
                tr("Image de référence"),
                self._reference_help(),
            )
            return
        python, error = self._comfy_python()
        if error:
            messagebox.showerror(tr("Python ComfyUI introuvable"), error)
            return
        script = ROOT / "prototypes" / "reference_image.py"
        if self.session_id and self.session_data:
            directory = self.session_store.directory(str(self.session_id))
            pending = False
        else:
            directory = self._pending_root()
            pending = True
        image_path = directory / "reference.png"
        thumb_path = directory / "reference_thumb.png"
        command = [
            python,
            str(script),
            "--source",
            str(source),
            "--image",
            str(image_path),
            "--thumb",
            str(thumb_path),
        ]
        flags = 0x08000000 if os.name == "nt" else 0
        try:
            result = subprocess.run(
                command,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(tr("Image de référence"), short_error(exc))
            return
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            messagebox.showerror(
                tr("Image de référence"),
                tr(
                    "Impossible de préparer l'image.\n\n{details}",
                    details=details[:800],
                ),
            )
            return

        info: dict[str, Any] = {}
        try:
            info = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            pass

        display = display_name or source.name
        if not pending and self.session_data:
            self.session_data["reference"] = {
                "image": "reference.png",
                "thumb": "reference_thumb.png",
                "name": display,
                "enabled": True,
                "width": info.get("width"),
                "height": info.get("height"),
            }
            try:
                self.session_store.save(self.session_data)
            except Exception as exc:  # noqa: BLE001
                self._log(f"Référence : {short_error(exc)}")

        self._display_reference(
            image_path,
            thumb_path,
            display,
            True,
            pending=pending,
        )
        if pending:
            self.pending_reference_selection = (
                list(self.current_selection) if self.current_selection else None
            )
        self._show_reference_panel()
        self._log(f"Image de référence : {source}")

    def _remove_reference(self) -> None:
        if self.running:
            return
        if self.session_id and self.session_data:
            reference = self.session_data.get("reference")
            if isinstance(reference, dict):
                directory = self.session_store.directory(str(self.session_id))
                for key in ("image", "thumb"):
                    name = reference.get(key)
                    if name:
                        try:
                            (directory / str(name)).unlink()
                        except OSError:
                            pass
            self.session_data["reference"] = None
            try:
                self.session_store.save(self.session_data)
            except Exception as exc:  # noqa: BLE001
                self._log(f"Référence : {short_error(exc)}")
        else:
            for path in self._pending_files():
                try:
                    path.unlink()
                except OSError:
                    pass
        self._clear_reference_ui()
        self._log("Image de référence retirée.")

    def _reference_active_path(self) -> Path | None:
        if not self._reference_supported() or not self.ref_var.get():
            return None
        if self.reference_path and self.reference_path.exists():
            return self.reference_path
        return None

    # ------------------------------------------------------------------
    # LoRA
    # ------------------------------------------------------------------

    def _load_profile_loras(self) -> None:
        self.lora_settings = load_lora_settings()
        self.lora_enabled_var.set(bool(self.lora_settings.get("enabled", True)))
        blur = bool(self.lora_settings.get("blur_nsfw", True))
        if bool(self.lora_blur_var.get()) != blur:
            self.lora_blur_var.set(blur)
        self.lora_items = profile_lora_items(self.lora_settings, self.profile_key)
        self._update_lora_ui()

    def _active_loras(self) -> list[dict[str, Any]]:
        if not self.lora_enabled_var.get():
            return []
        return active_lora_items(self.lora_items)[:MAX_LORAS]

    def _toggle_loras(self) -> None:
        self.lora_settings = load_lora_settings()
        self.lora_settings["enabled"] = bool(self.lora_enabled_var.get())
        try:
            save_lora_settings(self.lora_settings)
        except Exception as exc:  # noqa: BLE001
            self._log(tr("LoRA : {error}", error=short_error(exc)))
        self._update_lora_ui()
        self._log(
            tr("LoRA activés.")
            if self.lora_enabled_var.get()
            else tr("LoRA désactivés.")
        )

    def _open_lora_manager(self) -> None:
        if self.running:
            return
        from lora_manager import LoraManager  # noqa: PLC0415

        if self.lora_manager is not None:
            try:
                if self.lora_manager.winfo_exists():
                    self.lora_manager.deiconify()
                    self.lora_manager.lift()
                    self.lora_manager.focus_force()
                    return
            except tk.TclError:
                pass
            self.lora_manager = None
        self.lora_manager = LoraManager(self)

    def _apply_lora_items(self, items: list[dict[str, Any]]) -> None:
        if self._closing:
            return
        normalized: list[dict[str, Any]] = []
        for entry in items[:MAX_LORAS]:
            value = normalize_lora_item(entry)
            if value is not None:
                normalized.append(value)
        self.lora_items = normalized
        self.lora_settings = load_lora_settings()
        set_profile_lora_items(self.lora_settings, self.profile_key, normalized)
        try:
            save_lora_settings(self.lora_settings)
        except Exception as exc:  # noqa: BLE001
            self._log(tr("LoRA : {error}", error=short_error(exc)))
        if self.session_id and self.session_data:
            self.session_data["loras"] = copy.deepcopy(normalized)
            try:
                self.session_store.save(self.session_data)
            except Exception as exc:  # noqa: BLE001
                self._log(tr("LoRA : {error}", error=short_error(exc)))
        self._update_lora_ui()
        self._update_generate_state()

    def _loras_signature(self, items: list[dict[str, Any]] | None = None) -> str:
        values = items if items is not None else self._active_loras()
        return lora_signature(values)

    def _update_lora_ui(self) -> None:
        if self._closing or not hasattr(self, "lora_summary"):
            return
        enabled = bool(self.lora_enabled_var.get())
        configured = len(self.lora_items)
        active = self._active_loras() if enabled else []
        if not enabled:
            summary = tr("LoRA désactivés ({count} configurés)", count=configured)
        elif not configured:
            summary = tr("Aucun LoRA — clique sur Gérer les LoRA…")
        elif not active:
            summary = tr("Aucun LoRA actif — vérifie les cases dans Gérer…")
        else:
            details = " · ".join(
                f"{short_lora_label(item.get('label'))} "
                f"{float(item.get('strength', 0.0)):.2f}"
                for item in active[:2]
            )
            if len(active) > 2:
                details += tr(" et {count} autre(s)", count=len(active) - 2)
            if len(active) == 1:
                summary = tr("1 LoRA actif · {details}", details=details)
            else:
                summary = tr(
                    "{count} LoRA actifs · {details}",
                    count=len(active),
                    details=details,
                )
        self.lora_summary.config(text=summary)

        hints: list[str] = []
        profile_label = self._profile_label()
        for item in active:
            family = str(item.get("arch") or "")
            if lora_compatibility(self.profile_key, family) == "incompatible":
                hints.append(
                    tr(
                        "⚠ {label} semble destiné à {arch}, pas à {profile}.",
                        label=str(item.get("label") or "?"),
                        arch=lora_family_label(family),
                        profile=profile_label,
                    )
                )
        if self._lora_available is not None:
            missing = [
                str(item.get("label") or "?")
                for item in active
                if str(item.get("name") or "").replace("\\", "/").casefold()
                not in self._lora_available
            ]
            if missing:
                hints.append(
                    tr(
                        "LoRA introuvable dans ComfyUI : {names}",
                        names=", ".join(missing),
                    )
                )
        self.lora_hint.config(text="\n".join(hints))
        state = "disabled" if self.running else "normal"
        try:
            self.lora_check.config(state=state)
            self.lora_manage_btn.config(state=state)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Prompt guide
    # ------------------------------------------------------------------

    def _show_prompt_guide(self) -> None:
        if self.guide_window is not None and self.guide_window.winfo_exists():
            self.guide_window.deiconify()
            self.guide_window.lift()
            self.guide_window.focus_force()
            return

        window = tk.Toplevel(self)
        self.guide_window = window
        window.title(tr("Guide de prompt — StableCraft"))
        width, height = 660, 720
        x = self.winfo_rootx() + self.winfo_width() + 12
        y = self.winfo_rooty() + 40
        x = max(0, min(x, self.winfo_screenwidth() - width - 20))
        y = max(0, min(y, self.winfo_screenheight() - height - 40))
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.minsize(520, 520)
        window.configure(bg=BG)

        footer = tk.Frame(window, bg=BG)
        footer.pack(fill="x", side="bottom", padx=12, pady=8)
        tk.Button(
            footer,
            text=tr("Fermer"),
            command=window.destroy,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
        ).pack(side="right")

        text = tk.Text(
            window,
            wrap="word",
            bg=PANEL,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            bd=0,
            padx=16,
            pady=12,
            font=("Segoe UI", 9),
        )
        scroll = ttk.Scrollbar(window, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)

        text.tag_configure(
            "h1", font=("Segoe UI", 14, "bold"), foreground=FG, spacing1=6, spacing3=8
        )
        text.tag_configure(
            "h2", font=("Segoe UI", 10, "bold"), foreground=ACCENT, spacing1=12, spacing3=4
        )
        text.tag_configure("body", foreground=FG, spacing3=4)
        text.tag_configure(
            "code",
            font=("Consolas", 9),
            background="#141418",
            foreground="#d1d5db",
            lmargin1=12,
            lmargin2=12,
            spacing1=3,
            spacing3=6,
        )
        text.tag_configure("warn", foreground=YELLOW, spacing3=4)

        def add(value: str, tag: str = "body") -> None:
            text.insert("end", tr(value) + "\n", tag)

        add("Guide de prompt", "h1")
        add(
            "En mode EDIT, StableCraft envoie au modèle le crop de ta scène "
            "(sélection + contexte), puis applique le résultat dans le lasso. En mode "
            "T2I, aucune scène n'est envoyée : le prompt décrit l'image à générer, "
            "puis PhotoCraft la masque avec la sélection.",
            "body",
        )

        add("0. EDIT ou T2I ?", "h2")
        add("• EDIT : modifier une image existante. Décris le résultat final dans la scène.", "body")
        add("• T2I : créer une image sans image source. Décris la scène complète.", "body")
        add(
            "• En T2I, utilise une sélection rectangulaire : l'image est générée au "
            "format du crop puis masquée. Le lasso donne une forme irrégulière au masque.",
            "warn",
        )

        add("1. La bonne attitude, sans référence", "h2")
        add("• Écris en anglais : ces modèles répondent mieux aux prompts anglais.", "body")
        add("• Décris l'état final : couleur, matière, objet, position.", "body")
        add("• Dis explicitement ce qui doit rester inchangé : pose, visage, peau, fond, lumière.", "body")
        add("• Sois concret plutôt que poétique. Évite les négations : à CFG 1, le negative prompt agit peu.", "body")
        add("• Sélectionne l'objet entier, avec un peu de contexte autour.", "body")
        add(
            "Change the dress fabric to deep red. Keep the exact silhouette, skin, "
            "pose, lighting and background unchanged.",
            "code",
        )

        add("2. Avec une image de référence", "h2")
        add("Image 1 = la scène, c'est-à-dire ton image PhotoCraft.", "body")
        add("Image 2 = l'image de référence que tu as ajoutée.", "body")
        add("Qwen Image 2.1 les appelle <image1> et <image2> dans son prompt.", "body")
        add(
            "En T2I, FLUX.2 Klein 9B, FLUX.3 Klein et Qwen Image 2.1 utilisent la "
            "référence comme image 1 pour guider une nouvelle image. Krea 2 "
            "utilise la référence en EDIT.",
            "body",
        )
        add(
            "La référence n'est active que si la case est cochée et qu'une image est chargée. "
            "Elle n'est jamais collée : elle sert d'inspiration au modèle.",
            "warn",
        )
        add("Dis ce que tu prends de l'image 2, et où tu l'appliques dans l'image 1.", "body")
        add(
            "Add the black leather glove from the reference image to the man's right "
            "hand. Keep the hand pose, arm, skin tone, lighting and background unchanged.",
            "code",
        )
        add(
            "Use the reference image for the fabric pattern only. Keep the garment "
            "shape, folds, lighting and the rest of the scene unchanged.",
            "code",
        )
        add(
            "Replace the surfboard's design with the pattern from the reference image. "
            "Keep the board shape, feet, water, splash and lighting unchanged.",
            "code",
        )

        add("3. Ce qui marche le mieux", "h2")
        add("• Un objet seul, détouré ou sur un fond simple, est plus facile à transférer.", "body")
        add("• Une référence avec beaucoup de fond peut être confondue avec la scène.", "body")
        add("• Pour un vêtement, demande la couleur/matière ; pour un accessoire, décris sa position.", "body")
        add("• Krea 2, FLUX.2 Klein 9B, FLUX.3 Klein et Qwen Image 2.1 acceptent la référence.", "body")
        add("• Si le résultat copie trop la référence, précise « only » / « keep unchanged » dans le prompt.", "body")

        add("4. Rappel", "h2")
        add(
            "La référence est propre au calque StableCraft courant. Si tu changes de calque, "
            "l'UI recharge la référence de ce calque ; une nouvelle sélection repart sans référence.",
            "body",
        )
        text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Windows drag & drop
    # ------------------------------------------------------------------

    def _enable_windows_drop(self) -> None:
        if os.name != "nt" or self._closing or self._drop_enabled:
            return
        import ctypes
        from ctypes import wintypes

        hwnd: int | None = None
        try:
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32

            hwnd = int(self.winfo_id())
            parent = int(user32.GetParent(hwnd))
            if parent:
                hwnd = parent
            self._drop_hwnd = hwnd
            self._win_user32 = user32
            self._win_shell32 = shell32

            shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
            shell32.DragAcceptFiles(hwnd, True)
            shell32.DragQueryFileW.argtypes = [
                wintypes.HANDLE,
                wintypes.UINT,
                wintypes.LPWSTR,
                wintypes.UINT,
            ]
            shell32.DragQueryFileW.restype = wintypes.UINT
            shell32.DragFinish.argtypes = [wintypes.HANDLE]

            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_void_p,
            ]
            user32.CallWindowProcW.restype = ctypes.c_ssize_t
            user32.CallWindowProcW.argtypes = [
                ctypes.c_void_p,
                wintypes.HWND,
                ctypes.c_uint,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]

            wndproc_type = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t,
                wintypes.HWND,
                ctypes.c_uint,
                wintypes.WPARAM,
                wintypes.LPARAM,
            )

            def handler(hwnd_value: int, message: int, wparam: int, lparam: int) -> int:
                if message == 0x0233:  # WM_DROPFILES
                    try:
                        count = shell32.DragQueryFileW(
                            wintypes.HANDLE(wparam), 0xFFFFFFFF, None, 0
                        )
                        if count:
                            buffer = ctypes.create_unicode_buffer(32768)
                            if shell32.DragQueryFileW(
                                wintypes.HANDLE(wparam),
                                0,
                                buffer,
                                len(buffer),
                            ):
                                # This runs inside a native window procedure.
                                # Never call Tk here: after() re-enters Tcl
                                # from the callback and crashes Python 3.11
                                # with "PyEval_RestoreThread ... GIL is
                                # released". Let _poll_queue handle it.
                                if not self._closing:
                                    self.queue.put(("drop", buffer.value))
                    finally:
                        shell32.DragFinish(wintypes.HANDLE(wparam))
                    return 0
                return user32.CallWindowProcW(
                    self._old_wndproc,
                    hwnd_value,
                    message,
                    wparam,
                    lparam,
                )

            callback = wndproc_type(handler)
            old = user32.SetWindowLongPtrW(
                hwnd, -4, ctypes.cast(callback, ctypes.c_void_p)
            )
            if not old:
                raise OSError("SetWindowLongPtrW a échoué")
            self._drop_proc_ref = callback
            self._old_wndproc = old
            self._drop_enabled = True
            self._log("Drag & drop Windows activé.")
        except Exception as exc:  # noqa: BLE001
            if hwnd is not None:
                try:
                    ctypes.windll.shell32.DragAcceptFiles(hwnd, False)
                except Exception:  # noqa: BLE001
                    pass
            self._log(tr("Drag & drop indisponible : {error}", error=short_error(exc)))

    def _on_dropped_file(self, value: str) -> None:
        if self._closing:
            return
        path = Path(value)
        if path.suffix.lower() not in (
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".bmp",
            ".tif",
            ".tiff",
        ):
            self._log(
                tr(
                    "Fichier ignoré (format image attendu) : {name}",
                    name=path.name,
                )
            )
            return
        self._set_reference_from_source(path)

    def _disable_windows_drop(self) -> None:
        if not self._drop_enabled or self._drop_hwnd is None or self._win_user32 is None:
            return
        self._drop_enabled = False
        try:
            if self._win_shell32 is not None:
                self._win_shell32.DragAcceptFiles(self._drop_hwnd, False)
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._old_wndproc:
                self._win_user32.SetWindowLongPtrW(
                    self._drop_hwnd, -4, self._old_wndproc
                )
        except Exception:  # noqa: BLE001
            pass
        self._drop_hwnd = None

    # ------------------------------------------------------------------
    # Sessions / gallery
    # ------------------------------------------------------------------

    def _find_layer(self, layers: list[dict[str, Any]], layer_id: int) -> dict[str, Any] | None:
        for layer in layers:
            if layer.get("id") == layer_id:
                return layer
            found = self._find_layer(layer.get("children", []), layer_id)
            if found:
                return found
        return None

    @staticmethod
    def _document_context(
        doc: dict[str, Any] | None, doc_index: int | None
    ) -> tuple[Any, ...] | None:
        if not doc:
            return None
        return (
            doc_index,
            str(doc.get("name") or ""),
            int(doc.get("width") or 0),
            int(doc.get("height") or 0),
            doc.get("activeLayer"),
        )

    @staticmethod
    def _flatten_layers(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []
        for layer in layers:
            flat.append(layer)
            flat.extend(StableCraftApp._flatten_layers(layer.get("children", [])))
        return flat

    @staticmethod
    def _session_prompt_value(data: dict[str, Any]) -> str:
        generations = data.get("generations", [])
        current = int(data.get("current", -1))
        if 0 <= current < len(generations):
            return str(generations[current].get("prompt", "") or "")
        return ""

    def _rename_layer(self, layer_id: int, name: str) -> None:
        pc_cfg = self.cfg["photocraft"]
        token = read_token(Path(str(pc_cfg["control_token_file"])))
        client = ControlClient(
            str(pc_cfg["control_host"]),
            int(pc_cfg["control_port"]),
            token,
            timeout=10.0,
        )
        try:
            client.execute(
                "layer.renameLayer", {"layer": int(layer_id), "name": name}
            )
        finally:
            client.close_socket()

    def _maybe_split_duplicate_session(
        self,
        doc: dict[str, Any] | None,
        doc_index: int | None,
        session_id: str,
        active_layer: dict[str, Any],
    ) -> str | None:
        """Give a duplicated StableCraft layer its own session immediately."""
        if not doc:
            return None
        prefix = f"StableCraft [{session_id}]"
        layers = [
            layer
            for layer in self._flatten_layers(doc.get("layers", []))
            if str(layer.get("name", "")).startswith(prefix)
        ]
        if len(layers) < 2:
            return None
        data = (
            self.session_data
            if session_id == self.session_id and self.session_data
            else None
        )
        if data is None:
            try:
                data = self.session_store.load(session_id)
            except Exception:  # noqa: BLE001
                return None
        ids = {int(layer["id"]) for layer in layers}
        canonical: int | None = None
        try:
            stored = int(data.get("layer_id"))
            if stored in ids:
                canonical = stored
        except (TypeError, ValueError):
            pass
        if canonical is None:
            named = [
                layer
                for layer in layers
                if str(layer.get("name", "")) == str(data.get("layer_name", ""))
            ]
            canonical = (
                int(named[0]["id"]) if len(named) == 1 else min(ids)
            )
        active = int(active_layer["id"])
        if active == canonical:
            if data.get("layer_id") != canonical:
                data["layer_id"] = canonical
                try:
                    self.session_store.save(data)
                except Exception:  # noqa: BLE001
                    pass
            return None

        attempt = (int(doc_index) if doc_index is not None else -1, active, session_id)
        failed_at = self._duplicate_split_failed.get(attempt)
        if failed_at is not None and time.time() - failed_at < 30.0:
            return None
        if failed_at is not None:
            self._duplicate_split_failed.pop(attempt, None)
        new_id = self.session_store.new_id()
        while self.session_store.directory(new_id).exists():
            new_id = self.session_store.new_id()
        cloned: dict[str, Any] | None = None
        try:
            self.session_store.clone_directory(session_id, new_id)
            cloned = self.session_store.load(new_id)
            cloned["id"] = new_id
            cloned["layer_id"] = active
            cloned["layer_name"] = session_layer_name(
                new_id, self._session_prompt_value(cloned)
            )
            cloned["mask_channel"] = f"StableCraft Mask {new_id}"
            cloned["document"] = {
                "name": doc.get("name", ""),
                "path": doc.get("path"),
                "width": int(doc.get("width") or 0),
                "height": int(doc.get("height") or 0),
                "index": int(doc_index) if doc_index is not None else None,
            }
            self.session_store.save(cloned)
            self._rename_layer(active, str(cloned["layer_name"]))
        except Exception as exc:  # noqa: BLE001
            self._duplicate_split_failed[attempt] = time.time()
            if cloned is not None:
                import shutil  # noqa: PLC0415

                shutil.rmtree(
                    self.session_store.directory(str(cloned["id"])),
                    ignore_errors=True,
                )
            self._log(
                tr(
                    "Duplication de session impossible : {error}",
                    error=short_error(exc),
                )
            )
            return None
        self.session_id = new_id
        self.session_data = cloned
        self._populate_gallery()
        self._log(
            tr(
                "Calque dupliqué séparé : {old} → {new}",
                old=session_id,
                new=new_id,
            )
        )
        return new_id

    def _sync_session_from_doc(
        self, doc: dict[str, Any] | None, doc_index: int | None = None
    ) -> None:
        if self.running:
            return
        sid: str | None = None
        layer: dict[str, Any] | None = None
        if doc:
            layer = self._find_layer(doc.get("layers", []), doc.get("activeLayer"))
            if layer:
                sid = parse_session_id(str(layer.get("name", "")))
        fresh_clone = False
        if sid and layer:
            split_id = self._maybe_split_duplicate_session(
                doc, doc_index, sid, layer
            )
            if split_id:
                sid = split_id
                fresh_clone = True
        layer_key = (
            doc_index,
            str(doc.get("name") or "") if doc else "",
            str(doc.get("path") or "") if doc else "",
            doc.get("activeLayer") if doc else None,
        )
        layer_changed = (
            self._last_layer_key is None
            or layer_key != self._last_layer_key
        )
        self._last_layer_key = layer_key

        if (
            sid
            and sid == self.session_id
            and self.session_data is None
            and sid not in self._session_retry_done
            and self.session_store.session_path(sid).exists()
        ):
            # The first load can happen while the bridge is still writing the
            # session. Retry instead of staying on an empty gallery forever.
            self._session_retry_done.add(sid)
            self._load_session(sid, force=True)
        elif (
            sid
            and layer_changed
            and not fresh_clone
            and sid == self.session_id
            and self.session_data is not None
        ):
            # Two PhotoCraft layers can share the same session id after a
            # duplicate. Reload the session when the active layer changes so
            # unsaved prompt edits do not leak between them; the bridge splits
            # the duplicate into a real session on the next generation.
            # The layer created by our own generation must not overwrite the
            # fields the user edited while it was running.
            keep_fields = False
            if self._job_layer_id is not None:
                try:
                    active_layer = int(doc.get("activeLayer")) if doc else None
                except (TypeError, ValueError):
                    active_layer = None
                keep_fields = active_layer == self._job_layer_id
                self._job_layer_id = None
            self._load_session(sid, force=True, keep_fields=keep_fields)

        if sid and self.current_selection:
            data = (
                self.session_data
                if sid == self.session_id and self.session_data
                else None
            )
            if data is None:
                try:
                    data = self.session_store.load(sid)
                except Exception:  # noqa: BLE001
                    data = None
            stored = data.get("selection") if data else None
            if (
                stored
                and not self._same_selection(stored, self.current_selection)
                and not layer_changed
            ):
                # A new lasso on the same layer means a new session. Selecting
                # another layer (or reopening the saved project) must still
                # show that layer's existing gallery.
                sid = None

        context = self._document_context(doc, doc_index)
        selection = list(self.current_selection) if self.current_selection else None
        selection_changed = selection is not None and (
            self._context_selection is None
            or not self._same_selection(selection, self._context_selection)
        )
        changed = self._context_ready and (
            context != self._context_key or selection_changed
        )
        self._context_ready = True
        self._context_key = context
        self._context_selection = selection

        if sid != self.session_id:
            self._load_session(sid)
        elif changed and sid is None:
            # Same blank layer while the selection changed, or one blank layer
            # replaced another: this is a new selection, not the previous one.
            self._reset_generation_fields()

    def _refresh_running_session(self) -> None:
        """Reload the gallery after each image of a running batch."""
        session_id = self.pending_session_id or self.session_id
        if not session_id:
            return
        try:
            data = self.session_store.load(session_id)
        except Exception:  # noqa: BLE001
            return
        self._apply_pending_favorites(data)
        self.session_id = session_id
        self.session_data = data
        self._populate_gallery()

    def _load_session(
        self, session_id: str | None, force: bool = False, keep_fields: bool = False
    ) -> None:
        if session_id == self.session_id and not force:
            return
        previous = self.session_id
        self.session_id = session_id
        if session_id != previous:
            self._job_layer_id = None
        self.session_data = None
        if not session_id:
            # A fresh lasso starts in EDIT, even if the previous canvas was
            # generated in T2I.
            self.mode_var.set("edit")
            self._last_mode = "edit"
            self._update_mode_hint()
            self._load_profile_loras()
            # Never carry the previous layer's prompt/settings into a new
            # selection. The reference is cleared by the block below.
            self._reset_generation_fields(clear_reference=False)
        if session_id:
            try:
                self.session_data = self.session_store.load(session_id)
                self._apply_pending_favorites(self.session_data)
            except Exception as exc:  # noqa: BLE001
                self._log(tr("Session {session} : {error}", session=session_id, error=short_error(exc)))
        self._populate_gallery()
        if self.session_data:
            generations = self.session_data.get("generations", [])
            current = int(self.session_data.get("current", -1))
            if 0 <= current < len(generations):
                session_profile = str(generations[current].get("profile", ""))
                if (
                    session_profile in SUPPORTED_PROFILES
                    and session_profile != self.profile_key
                ):
                    self._load_profile(session_profile)
            # `_restore_session_fields` deliberately leaves the seed field alone:
            # the seed used by a generation is shown in the gallery hint, and the
            # user's field must stay on -1 unless they typed a value themselves.
            if not keep_fields:
                self._load_profile_loras()
                self._restore_session_fields(self.session_data)

        if session_id:
            self._clear_pending_reference()
            self._load_reference_for_session()
        elif previous is not None:
            self._clear_pending_reference()
            self._clear_reference_ui()
        else:
            self._draw_reference_tile()
        self._update_reference_for_profile()
        self._update_lora_ui()
        self._update_generate_state()
        self._check_models()

    def _restore_session_fields(self, sdata: dict[str, Any]) -> None:
        generations = sdata.get("generations", [])
        index = int(sdata.get("current", -1))
        if not (0 <= index < len(generations)):
            return
        generation = generations[index]
        saved_mode = str(generation.get("mode", "edit"))
        self.mode_var.set("t2i" if saved_mode == "t2i" else "edit")
        self._last_mode = self._mode()
        self._update_mode_hint()
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", str(generation.get("prompt", "")))
        self.neg_text.delete("1.0", "end")
        self.neg_text.insert("1.0", str(generation.get("negative", "")))
        self.neg_var.set(bool(generation.get("negative")))
        self._toggle_negative()
        self.padding_var.set(str(generation.get("padding", 96)))
        self.feather_var.set(str(generation.get("feather", 10)))
        self.steps_var.set(str(generation.get("steps", 16)))
        self.cfg_var.set(str(generation.get("cfg", 1.0)))
        if generation.get("sampler"):
            self.sampler_var.set(str(generation["sampler"]))
        if generation.get("scheduler"):
            self.scheduler_var.set(str(generation["scheduler"]))
        if "denoise" in generation:
            self.denoise_var.set(f"{float(generation.get('denoise', 1.0)):.2f}")
        self._update_denoise_for_profile()
        source = None
        if isinstance(sdata.get("loras"), list):
            source = sdata["loras"]
        elif isinstance(generation.get("loras"), list):
            # Sessions created from the CLI may only carry the active stack in
            # the generation entry.
            source = generation["loras"]
        if source is not None:
            restored: list[dict[str, Any]] = []
            for entry in source[:MAX_LORAS]:
                value = normalize_lora_item(entry)
                if value is not None:
                    restored.append(value)
            self.lora_items = restored
            self._update_lora_ui()

    def _set_result_preview(self, index: int | None) -> None:
        path: Path | None = None
        if self.session_data and self.session_id and index is not None:
            generations = self.session_data.get("generations", [])
            if 0 <= index < len(generations):
                relative = generations[index].get("result")
                if relative:
                    candidate = (
                        self.session_store.directory(str(self.session_id))
                        / str(relative)
                    )
                    if candidate.exists():
                        path = candidate
        self.preview_paths["result"] = str(path) if path else None
        if self.preview_mode.get() == "result":
            self._load_preview(self.preview_paths["result"])

    def _set_document_preview(self) -> None:
        path: Path | None = None
        if self.session_data and self.session_id:
            candidate = self.session_store.directory(str(self.session_id)) / "after.png"
            if candidate.exists():
                path = candidate
        self.preview_paths["document"] = str(path) if path else None
        if self.preview_mode.get() == "document":
            self._load_preview(self.preview_paths["document"])

    def _populate_gallery(self) -> None:
        generation_count = (
            len(self.session_data.get("generations", []))
            if self.session_data
            else 0
        )
        # Applying an existing generation repaints the gallery without adding
        # an item. Keep the scroll fraction in that case; a new generation or a
        # different session may scroll to the current item.
        preserve_y: float | None = None
        if (
            self.session_id is not None
            and self.session_id == self._gallery_last_session
            and self._gallery_last_count == generation_count
        ):
            try:
                preserve_y = self.gallery_canvas.yview()[0]
            except tk.TclError:
                preserve_y = None
        for child in self.gallery_inner.winfo_children():
            child.destroy()
        self.gallery_images.clear()
        self.gallery_buttons.clear()
        self.gallery_canvases.clear()
        self._gallery_items.clear()
        self._gallery_item_indices.clear()
        self._gallery_star_centers.clear()
        self._gallery_cell_w = GALLERY_CELL_W
        self._gallery_cell_h = GALLERY_CELL_H
        self._gallery_columns = 0

        if not self.session_data:
            self.gallery_title.config(text=tr("Aucune galerie"))
            self.gallery_hint.config(
                text=tr("Clique sur un calque StableCraft pour retrouver ses générations.")
            )
            self._set_document_preview()
            self._set_result_preview(None)
            self._gallery_scroll_to = None
            self._gallery_restore_y = None
            self._gallery_last_session = self.session_id
            self._gallery_last_count = 0
            self.gallery_canvas.configure(scrollregion=(0, 0, 0, 0))
            self.gallery_canvas.configure(height=160)
            return

        generations = self.session_data.get("generations", [])
        current = int(self.session_data.get("current", -1))
        self._update_gallery_title()
        if not generations:
            self.gallery_hint.config(text=tr("Aucune génération dans cette session."))
            self._set_document_preview()
            self._set_result_preview(None)
            self._gallery_scroll_to = None
            self._gallery_restore_y = None
            self._gallery_last_session = self.session_id
            self._gallery_last_count = 0
            self.gallery_canvas.configure(scrollregion=(0, 0, 0, 0))
            self.gallery_canvas.configure(height=160)
            return

        self._set_document_preview()
        self._set_result_preview(current if current >= 0 else None)
        session_dir = self.session_store.directory(str(self.session_id))
        photos: list[tuple[int, dict[str, Any], tk.PhotoImage, int, int]] = []
        for index, generation in enumerate(generations):
            thumb_rel = generation.get("thumb") or generation.get("result")
            thumb_path = session_dir / str(thumb_rel) if thumb_rel else None
            result_path = session_dir / str(generation.get("result", ""))
            path = thumb_path if thumb_path and thumb_path.exists() else result_path
            try:
                image = tk.PhotoImage(file=str(path))
            except Exception:  # noqa: BLE001
                continue
            if (
                image.width() > GALLERY_IMAGE_W
                or image.height() > GALLERY_IMAGE_H
            ):
                # Legacy square/portrait thumbnails do not fit the 4:3 box.
                # Prefer the full result, then subsample it to fit.
                if result_path.exists() and result_path != path:
                    try:
                        image = tk.PhotoImage(file=str(result_path))
                    except Exception:  # noqa: BLE001
                        pass
                factor = max(
                    1,
                    math.ceil(
                        max(
                            image.width() / GALLERY_IMAGE_W,
                            image.height() / GALLERY_IMAGE_H,
                        )
                    ),
                )
                if factor > 1:
                    image = image.subsample(factor, factor)
            photos.append((index, generation, image, image.width(), image.height()))

        if not photos:
            self.gallery_hint.config(
                text=tr("Aucune génération dans cette session.")
            )
            self._gallery_scroll_to = None
            self._gallery_restore_y = None
            self._gallery_last_session = self.session_id
            self._gallery_last_count = len(generations)
            self.gallery_canvas.configure(scrollregion=(0, 0, 0, 0))
            self.gallery_canvas.configure(height=160)
            return

        cell_w = GALLERY_CELL_W
        cell_h = GALLERY_CELL_H
        self._gallery_cell_w = cell_w
        self._gallery_cell_h = cell_h
        for index, generation, image, image_w, image_h in photos:
            self.gallery_images.append(image)
            selected = index == current
            canvas = self._make_gallery_item(
                index,
                generation,
                image,
                selected,
                cell_w,
                cell_h,
                image_w,
                image_h,
            )
            self.gallery_canvases[index] = canvas
            self.gallery_buttons[index] = canvas
            self._gallery_items.append(canvas)
            self._gallery_item_indices.append(index)

        self.gallery_hint.config(text=tr("Clique sur une vignette pour appliquer."))
        if preserve_y is not None:
            self._gallery_restore_y = preserve_y
            self._gallery_scroll_to = None
        else:
            self._gallery_restore_y = None
            self._gallery_scroll_to = (
                current if 0 <= current < len(generations) else 0
            )
        self._gallery_last_session = self.session_id
        self._gallery_last_count = len(generations)
        self._layout_gallery()
        self.gallery_inner.update_idletasks()
        bbox = self.gallery_canvas.bbox("all")
        if bbox:
            self.gallery_canvas.configure(scrollregion=bbox)

    def _apply_generation(self, index: int) -> None:
        if self.running or not self.session_id or not self.session_data:
            return
        self.job_kind = "generate"
        self._apply_only = True
        self._job_layer_id = None
        self._pending_favorites.clear()
        self._pending_favorites_session = None
        generations = self.session_data.get("generations", [])
        if not 0 <= index < len(generations):
            return
        # The Crop view follows the clicked gallery item, not the last one
        # produced during a generation.
        self._set_result_preview(index)
        python, error = self._comfy_python()
        if error:
            messagebox.showerror("Python ComfyUI introuvable", error)
            return
        bridge = ROOT / "prototypes" / "bridge_cli.py"
        command = [
            python,
            str(bridge),
            "--config",
            str(self.config_path),
            "--apply",
            self.session_id,
            "--generation",
            str(index),
            "--save-preview",
        ]
        self._start_bridge(command, f"Application de la génération #{index + 1}…")

    def _comfy_python(self) -> tuple[str | None, str | None]:
        if os.name != "nt":
            configured = (
                os.environ.get("STABLECRAFT_BRIDGE_PYTHON")
                or str(self.cfg.get("app", {}).get("bridge_python", "") or "")
            )
            candidates = [
                configured,
                str(ROOT / ".venv" / "bin" / "python"),
                sys.executable,
            ]
            for candidate in candidates:
                if candidate and Path(candidate).exists():
                    return candidate, None
            return None, tr(
                "Python du venv StableCraft introuvable. "
                "Crée-le avec install.sh ou installe requests et Pillow."
            )
        python = os.environ.get("STABLECRAFT_COMFY_PYTHON") or str(
            self.cfg["comfyui"].get("python") or ""
        )
        if not python or not Path(python).exists():
            return None, tr(
                "Renseigne [comfyui] python dans config.toml avec le python_embeded de ComfyUI."
            )
        return python, None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _generate(self) -> None:
        if self.running:
            return
        self.job_kind = "generate"
        self._apply_only = False
        self._job_layer_id = None
        self._pending_favorites.clear()
        self._pending_favorites_session = None
        batch = self._batch_count()
        if self.profile_key not in SUPPORTED_PROFILES:
            messagebox.showinfo(
                tr("Bientôt"), tr("Ce profil sera ajouté plus tard.")
            )
            return
        if not self.models_ok:
            self._open_model_manager()
            return
        reuse = self._reusable_session()
        if not self.has_selection and not reuse:
            messagebox.showwarning(
                tr("Sélection vide"),
                tr(
                    "Fais un lasso autour de la zone à modifier, ou sélectionne un "
                    "calque StableCraft pour régénérer avec sa sélection d'origine."
                ),
            )
            return
        duplicate = self._duplicate_generation() if batch == 1 else None
        if duplicate is not None:
            messagebox.showinfo(
                tr("Déjà généré"),
                tr(
                    "Cette combinaison existe déjà dans la galerie (#{index}).\n\n"
                    "Mets le seed à -1 ou change le prompt pour régénérer.",
                    index=duplicate + 1,
                ),
            )
            return
        if self.ref_var.get() and self._reference_supported():
            if self._reference_active_path() is None:
                messagebox.showwarning(
                    tr("Référence vide"),
                    tr(
                        "Ajoute une image de référence ou décoche la case "
                        "« Utiliser une image de référence »."
                    ),
                )
                return
        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning(
                tr("Prompt vide"),
                tr("Décris l'image à générer.")
                if self._mode() == "t2i"
                else tr("Écris ce que tu veux changer."),
            )
            return
        negative = self.neg_text.get("1.0", "end").strip() if self.neg_var.get() else ""
        python, error = self._comfy_python()
        if error:
            messagebox.showerror(tr("Python ComfyUI introuvable"), error)
            return
        bridge = ROOT / "prototypes" / "bridge_cli.py"
        if not bridge.exists():
            messagebox.showerror(tr("Bridge introuvable"), str(bridge))
            return

        command = [
            python,
            str(bridge),
            "--config",
            str(self.config_path),
            "--profile",
            self.profile_key,
            "--mode",
            self._mode(),
            "--prompt",
            prompt,
            "--padding",
            self.padding_var.get(),
            "--feather",
            self.feather_var.get(),
            "--steps",
            self.steps_var.get(),
            "--cfg",
            self.cfg_var.get(),
            "--sampler",
            self.sampler_var.get(),
            "--scheduler",
            self.scheduler_var.get(),
        ]
        if self._mode() == "edit":
            command += ["--denoise", self.denoise_var.get()]
        command += [
            "--seed",
            self.seed_var.get(),
            "--batch",
            str(batch),
            "--save-preview",
        ]
        if reuse:
            command += ["--session", self.session_id]
        else:
            command += ["--session-mode"]
        if not reuse:
            # A new session must receive the active reference explicitly. For
            # an existing session the bridge reloads it from session.json.
            reference = self._reference_active_path()
            if reference is not None:
                command += ["--reference", str(reference)]
                if self.reference_name:
                    command += ["--reference-name", self.reference_name]
        if negative:
            command += ["--negative", negative]
        for item in self._active_loras():
            name = str(item.get("name") or "")
            if not name:
                continue
            strength = max(0.0, min(1.0, float(item.get("strength", 1.0))))
            command += ["--lora", f"{name}={strength:.2f}"]
        self._start_bridge(
            command,
            tr("Régénération en cours…") if reuse else tr("Génération en cours…"),
        )

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def _draw_progress(self) -> None:
        try:
            self.progress_canvas.delete("all")
        except tk.TclError:
            return
        width = max(1, self.progress_canvas.winfo_width())
        height = max(1, self.progress_canvas.winfo_height())
        self.progress_canvas.create_rectangle(
            0, 0, width, height, fill=PANEL, outline=""
        )
        if self._progress_indeterminate:
            segment = max(40, width // 5)
            x = int(self._progress_position * (width + segment)) - segment
            x0, x1 = max(0, x), min(width, x + segment)
            if x1 > x0:
                self.progress_canvas.create_rectangle(
                    x0, 2, x1, height - 2, fill=ACCENT, outline=""
                )
        else:
            filled = int(width * max(0, min(100, self.progress_value)) / 100)
            if filled > 0:
                self.progress_canvas.create_rectangle(
                    0, 0, filled, height, fill=ACCENT, outline=""
                )
        text = self.progress_text or tr("Prêt.")
        self.progress_canvas.create_text(
            width // 2 + 1,
            height // 2 + 1,
            text=text,
            fill="#0b0b0d",
            font=("Segoe UI", 9, "bold"),
        )
        self.progress_canvas.create_text(
            width // 2,
            height // 2,
            text=text,
            fill="white",
            font=("Segoe UI", 9, "bold"),
        )

    def _set_progress(
        self, percent: float, text: str, *, indeterminate: bool = False
    ) -> None:
        self.progress_value = max(0.0, min(100.0, float(percent)))
        self.progress_text = text or tr("Prêt.")
        if indeterminate != self._progress_indeterminate:
            self._progress_indeterminate = indeterminate
            if indeterminate:
                self._start_progress_animation()
            else:
                self._stop_progress_animation()
        self._draw_progress()

    def _start_progress_animation(self) -> None:
        if self._progress_animation is not None:
            return

        def tick() -> None:
            if not self._progress_indeterminate:
                self._progress_animation = None
                return
            self._progress_position = (self._progress_position + 0.035) % 1.0
            self._draw_progress()
            self._progress_animation = self.after(50, tick)

        self._progress_animation = self.after(50, tick)

    def _stop_progress_animation(self) -> None:
        if self._progress_animation is not None:
            try:
                self.after_cancel(self._progress_animation)
            except tk.TclError:
                pass
            self._progress_animation = None

    def _progress_start(self, label: str) -> None:
        self._set_progress(0, label, indeterminate=True)
        self.progress_label.config(text=label, fg=YELLOW)

    def _progress_finish(self, text: str, color: str) -> None:
        self._set_progress(100 if color == GREEN else self.progress_value, text)
        self.progress_label.config(text=text, fg=color)

    def _handle_progress(self, data: dict[str, Any]) -> None:
        if self.job_kind == "xyz" and self.xyz_window is not None:
            try:
                if self.xyz_window.winfo_exists():
                    self.xyz_window.handle_progress(data)
            except Exception:  # noqa: BLE001
                pass
        percent = int(data.get("percent", 0) or 0)
        if data.get("unavailable"):
            self._set_progress(percent, tr("Progression indisponible…"), indeterminate=True)
            return
        stage = tr(str(data.get("stage") or ""))
        scope = str(data.get("scope") or "generate")
        try:
            index = int(data.get("index") or 0)
            count = int(data.get("count") or 1)
        except (TypeError, ValueError):
            index, count = 0, 1
        label = f"{stage} : {percent}%" if stage else f"{percent}%"
        if count > 1:
            prefix = (
                tr("Image {index}/{count}", index=index, count=count)
                if scope == "generate"
                else tr("Cellule {index}/{count}", index=index, count=count)
            )
            label = f"{prefix} · {label}"
        self._set_progress(percent, label, indeterminate=False)

    def _start_bridge(self, command: list[str], label: str) -> None:
        if self.running:
            return
        bridge = ROOT / "prototypes" / "bridge_cli.py"
        if not bridge.exists():
            messagebox.showerror(tr("Bridge introuvable"), str(bridge))
            return
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        flags = 0x08000000 if os.name == "nt" else 0
        try:
            self.proc = subprocess.Popen(
                command,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=flags,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(tr("Lancement impossible"), short_error(exc))
            return

        self.running = True
        self.last_error = None
        self._cancel_requested = False
        self.pending_session_id = None
        self.pending_generation = None
        self._progress_start(label)
        self.cancel_btn.config(state="normal")
        self._update_lora_ui()
        self._log("")
        self._log("$ " + " ".join(Path(part).name if i == 0 else part for i, part in enumerate(command)))
        self.proc_reader = threading.Thread(target=self._read_process, daemon=True)
        self._update_generate_state()
        self._update_reference_for_profile()
        self.proc_reader.start()

    def _read_process(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            self.queue.put(("done", -1))
            return
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            if line.startswith("PROGRESS:"):
                try:
                    data = json.loads(line.split(":", 1)[1].strip())
                except (ValueError, TypeError):
                    data = None
                if isinstance(data, dict):
                    self.queue.put(("progress", data))
                continue
            if line.startswith("XYZ_"):
                kind, _, payload = line.partition(":")
                self.queue.put((kind.strip().lower(), payload.strip()))
                continue
            self.queue.put(("log", line))
            if line.startswith("Preview:"):
                self.queue.put(("preview", line.split(":", 1)[1].strip()))
            elif line.startswith("Result:"):
                path = line.split(":", 1)[1].strip().split(" (")[0].strip()
                self.queue.put(("result", path))
            elif line.startswith("SESSION:"):
                self.queue.put(("session_line", line.split(":", 1)[1].strip()))
            elif line.startswith("GENERATION:"):
                try:
                    self.queue.put(("generation_line", int(line.split(":", 1)[1].strip())))
                except ValueError:
                    pass
            elif line.startswith("ERROR:"):
                self.queue.put(("error", line))
        code = proc.wait()
        self.queue.put(("done", code))

    def _finish(self, code: int) -> None:
        if self.job_kind == "xyz":
            self._finish_xyz(code)
            return
        self.running = False
        loras_before_reload = copy.deepcopy(self.lora_items)
        self._stop_progress_animation()
        self.cancel_btn.config(state="disabled")
        session_id = self.pending_session_id
        self.pending_session_id = None
        self.pending_generation = None
        self._update_reference_for_profile()
        if session_id:
            # Reload even after an apply error: the generated image is already
            # on disk and must remain selectable in the gallery.
            self._load_session(
                session_id, force=True, keep_fields=not self._apply_only
            )
            if not self._apply_only and self.session_data:
                try:
                    self._job_layer_id = int(self.session_data.get("layer_id"))
                except (TypeError, ValueError):
                    self._job_layer_id = None
        else:
            self._update_generate_state()
        if self.session_data is not None:
            self._apply_pending_favorites(self.session_data)
            if "loras" not in self.session_data:
                # The bridge records only the active stack in the generation.
                # Keep the full UI stack (including disabled entries) for the
                # layer snapshot.
                self.lora_items = loras_before_reload
            self.session_data["loras"] = copy.deepcopy(self.lora_items)
            try:
                self.session_store.save(self.session_data)
            except Exception as exc:  # noqa: BLE001
                self._log(tr("LoRA : {error}", error=short_error(exc)))
        self._pending_favorites.clear()
        self._pending_favorites_session = None
        self._update_lora_ui()
        self._update_generate_state()
        if code == 0 and not self.last_error:
            self._progress_finish(tr("Terminé — calque StableCraft prêt."), GREEN)
        elif self.last_error:
            self._set_progress(
                self.progress_value, tr("Erreur — voir le journal.")
            )
            self.progress_label.config(text=tr("Erreur — voir le journal."), fg=RED)
        elif self._cancel_requested:
            self._set_progress(self.progress_value, tr("Annulé."))
            self.progress_label.config(text=tr("Annulé."), fg=YELLOW)
        else:
            text = tr("Processus terminé (code {code}).", code=code)
            self._set_progress(self.progress_value, text)
            self.progress_label.config(text=text, fg=YELLOW)
        self.proc = None

    def _finish_xyz(self, code: int) -> None:
        self.running = False
        self._stop_progress_animation()
        self.cancel_btn.config(state="disabled")
        self._update_lora_ui()
        self._update_reference_for_profile()
        self._update_generate_state()
        window = self.xyz_window
        if window is not None:
            try:
                if window.winfo_exists():
                    window.on_bridge_done(code, self.last_error)
            except Exception:  # noqa: BLE001
                pass
        self.pending_session_id = None
        self.pending_generation = None
        self._set_progress(0, tr("Prêt."))
        self.progress_label.config(text=tr("Prêt."), fg=MUTED)
        self.job_kind = "generate"
        self.proc = None
        self._flush_pending_favorites()

    def _cancel(self) -> None:
        if self.proc and self.proc.poll() is None:
            self._cancel_requested = True
            self._log("Annulation demandée…")
            try:
                self.proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            try:
                endpoint = str(self.cfg["comfyui"]["endpoint"]).rstrip("/")
                request = urllib.request.Request(endpoint + "/interrupt", method="POST", data=b"")
                urllib.request.urlopen(request, timeout=2)
            except Exception:  # noqa: BLE001
                pass
            self._set_progress(self.progress_value, tr("Annulation…"))
            self.progress_label.config(text=tr("Annulation…"), fg=YELLOW)

    # ------------------------------------------------------------------
    # Update check
    # ------------------------------------------------------------------

    def _check_update(self) -> None:
        try:
            request = urllib.request.Request(
                LATEST_RELEASE_API,
                headers={"User-Agent": f"StableCraft/{APP_VERSION}"},
            )
            with urllib.request.urlopen(request, timeout=6) as response:
                data = json.load(response)
        except Exception:  # noqa: BLE001 - no release yet, private repo, offline
            return
        tag = str(data.get("tag_name", "") or "")
        if not tag:
            return
        if version_tuple(tag) > version_tuple(APP_VERSION):
            self.queue.put(
                (
                    "update",
                    tag.lstrip("v"),
                    data.get("html_url") or RELEASES_URL,
                )
            )

    def _open_release_page(self, _event: object = None) -> None:
        if self.update_url:
            webbrowser.open(self.update_url)

    def _on_language_change(self, _event: object = None) -> None:
        language = self.language_var.get().lower()
        if language == current_language():
            return
        try:
            text = self.config_path.read_text(encoding="utf-8")
            if re.search(r"(?m)^language\s*=.*$", text):
                text = re.sub(
                    r"(?m)^language\s*=.*$",
                    f'language = "{language}"',
                    text,
                    count=1,
                )
            elif re.search(r"(?m)^\[app\]\s*$", text):
                text = re.sub(
                    r"(?m)^\[app\]\s*$",
                    f'[app]\nlanguage = "{language}"',
                    text,
                    count=1,
                )
            else:
                text += f'\n[app]\nlanguage = "{language}"\n'
            self.config_path.write_text(text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(tr("Langue"), str(exc))
            return
        messagebox.showinfo(
            "Language / Langue",
            "Redémarre l'UI pour appliquer la langue.\n\n"
            "Restart the UI to apply the language.",
        )

    def _toggle_topmost(self) -> None:
        """Keep only the main window above other applications."""
        self._cancel_topmost_job()
        if not self.topmost_var.get():
            self._set_main_topmost(False)
            return
        self._set_main_topmost(True)
        self._maintain_topmost()

    def _set_main_topmost(self, state: bool) -> None:
        try:
            self.attributes("-topmost", state)
            self._topmost_state = state
        except tk.TclError:
            pass

    def _demote_for_child(self) -> None:
        """Release the main window as soon as a child window is used."""
        if self._closing or not self.topmost_var.get():
            return
        self._set_main_topmost(False)

    def _cancel_topmost_job(self) -> None:
        if self._topmost_job is not None:
            try:
                self.after_cancel(self._topmost_job)
            except tk.TclError:
                pass
            self._topmost_job = None

    def _maintain_topmost(self) -> None:
        self._topmost_job = None
        if self._closing or not self.topmost_var.get():
            self._set_main_topmost(False)
            return
        desired = not self._has_visible_child()
        if desired != self._topmost_state:
            self._set_main_topmost(desired)
        self._topmost_job = self.after(200, self._maintain_topmost)

    def _has_visible_child(self) -> bool:
        """True when a normal Toplevel (LoRA, models, XYZ, guide…) is visible."""
        def walk(widget: tk.Misc) -> bool:
            for child in widget.winfo_children():
                if isinstance(child, tk.Toplevel):
                    try:
                        if child.overrideredirect():
                            continue
                    except tk.TclError:
                        continue
                    try:
                        if (
                            child.winfo_exists()
                            and child.winfo_viewable()
                            and child.state() not in {"withdrawn", "iconic"}
                        ):
                            return True
                    except tk.TclError:
                        pass
                if walk(child):
                    return True
            return False

        return walk(self)

    def _check_krea_node(self) -> None:
        try:
            latest = latest_krea_release()
            status = krea_node_status(self.cfg, latest)
        except Exception:  # noqa: BLE001
            return
        self.queue.put(("krea_node", status, latest))

    def _update_krea_node_label(self) -> None:
        # The Krea node is only relevant to Krea profiles. Showing its install
        # banner on FLUX/Qwen profiles looks like a false missing dependency.
        if self.profile_key not in KREA_PROFILES:
            self.node_update_label.config(text="")
            if self.node_update_label.winfo_manager():
                self.node_update_label.pack_forget()
            return
        if not self.node_update_label.winfo_manager():
            self.node_update_label.pack(fill="x")
        status = self.krea_status or {}
        if status.get("needs_install"):
            self.node_update_label.config(
                text=tr(
                    "Nœud Krea 2 absent — installer v{version} (cliquer ici)",
                    version=status.get("latest") or "?",
                )
            )
        elif status.get("needs_update"):
            self.node_update_label.config(
                text=tr(
                    "Nœud Krea 2 : v{installed} installé, v{latest} disponible — "
                    "mettre à jour (cliquer ici)",
                    installed=status.get("installed"),
                    latest=status.get("latest"),
                )
            )
        else:
            self.node_update_label.config(text="")
            if self.node_update_label.winfo_manager():
                self.node_update_label.pack_forget()

    # ------------------------------------------------------------------
    # Preview / log
    # ------------------------------------------------------------------

    def _load_preview_mode(self) -> None:
        mode = self.preview_mode.get()
        path = self.preview_paths.get(mode)
        self._load_preview(path)

    def _load_preview(self, path: str | None) -> None:
        self.preview_canvas.delete("all")
        if not path or not Path(path).exists():
            self.preview_canvas.create_text(
                225,
                145,
                text=tr(
                    "Aucun aperçu.\nFais un lasso, écris un prompt, puis clique Générer."
                ),
                fill=MUTED,
                font=("Segoe UI", 9),
                justify="center",
            )
            self.preview_image = None
            return
        try:
            image = tk.PhotoImage(file=path)
        except Exception as exc:  # noqa: BLE001
            self.preview_canvas.create_text(
                225,
                145,
                text=tr("Aperçu indisponible : {error}", error=short_error(exc)),
                fill=RED,
                font=("Segoe UI", 9),
                justify="center",
            )
            self.preview_image = None
            return
        width, height = image.width(), image.height()
        factor = max(1, math.ceil(max(width / 440, height / 280)))
        if factor > 1:
            image = image.subsample(factor, factor)
        self.preview_image = image
        self.preview_canvas.create_image(225, 145, image=image)

    def _log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 600:
            self.log_text.delete("1.0", "200.0")
        self.log_text.configure(state="disabled")

    def _open_config(self) -> None:
        try:
            open_path(self.config_path)
        except Exception:  # noqa: BLE001
            self._log(tr("Config : {path}", path=self.config_path))

    def _on_close(self) -> None:
        self._closing = True
        self._cancel_topmost_job()
        self.stop_event.set()
        self._disable_windows_drop()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            try:
                endpoint = str(self.cfg["comfyui"]["endpoint"]).rstrip("/")
                request = urllib.request.Request(endpoint + "/interrupt", method="POST", data=b"")
                urllib.request.urlopen(request, timeout=1)
            except Exception:  # noqa: BLE001
                pass
        self._stop_progress_animation()
        self._flush_pending_favorites()
        if self.xyz_window is not None:
            try:
                self.xyz_window.destroy()
            except Exception:  # noqa: BLE001
                pass
        self.destroy()


def main() -> None:
    ap = argparse.ArgumentParser(description="StableCraft Tkinter MVP")
    ap.add_argument("--config", type=Path, default=ROOT / "config.toml")
    ap.add_argument("--profile", default=None, help="flux3_klein, flux2_klein_9b, or krea2_edit")
    ap.add_argument("--smoke-test", action="store_true", help="open, connect, then close after 3s")
    ap.add_argument("--smoke-generate", action="store_true", help="run one generation, then close")
    ap.add_argument("--smoke-apply", type=int, default=None, help="apply a gallery generation, then close")
    args = ap.parse_args()

    app = StableCraftApp(args.config, initial_profile=args.profile)
    if args.smoke_test:
        app.after(3000, app._on_close)
    if args.smoke_generate:
        app.after(3500, app._generate)

        def wait_done() -> None:
            if app.running:
                app.after(1000, wait_done)
            else:
                app.after(5000, app._on_close)

        app.after(5000, wait_done)
    if args.smoke_apply is not None:
        def start_apply() -> None:
            if app.session_data:
                app._apply_generation(args.smoke_apply)
            else:
                app.after(500, start_apply)

        app.after(1500, start_apply)

        def wait_apply() -> None:
            if app.running:
                app.after(1000, wait_apply)
            else:
                app.after(3000, app._on_close)

        app.after(5000, wait_apply)
    app.mainloop()
    if args.smoke_test or args.smoke_generate:
        print("SMOKE OK")


if __name__ == "__main__":
    main()
