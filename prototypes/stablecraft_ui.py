"""StableCraft — Tkinter MVP UI.

Zero extra dependency: the UI uses the standard library and Tkinter. The heavy
lifting (ComfyUI, Pillow, requests) runs in the ComfyUI embedded Python through
`prototypes/bridge_cli.py`.

Run:
    python prototypes/stablecraft_ui.py --config config.toml
"""

from __future__ import annotations

import argparse
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
from tkinter import filedialog, messagebox, ttk

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
from models_tools import (  # noqa: E402
    MONO_FONT,
    UI_FONT,
    download_options,
    open_path,
    ui_scale,
    krea_node_status,
    latest_krea_release,
    resolve_filename,
    set_selected_file,
)
from session_store import SessionStore, parse_session_id  # noqa: E402

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

KREA_PROFILES = {"krea2_edit", "krea2_general_edit"}
QWEN_PROFILE = "qwen_image_21"
SUPPORTED_PROFILES = {
    "flux3_klein",
    "flux2_klein_9b",
    "krea2_general_edit",
    "krea2_edit",
    QWEN_PROFILE,
}
REFERENCE_PROFILES = {"krea2_edit", "krea2_general_edit", "flux3_klein", QWEN_PROFILE}
T2I_REFERENCE_PROFILES = {"flux3_klein", QWEN_PROFILE}


DEFAULTS: dict[str, Any] = {
    "app": {
        "language": "en",
        "default_profile": "flux3_klein",
        "sessions_dir": str(ROOT / "user" / "sessions"),
    },
    "photocraft": {
        "control_host": "127.0.0.1",
        "control_port": 7990,
        "control_token_file": str(ROOT / "user" / "control.token"),
        "automation_root": str(ROOT / "user"),
    },
    "comfyui": {
        "endpoint": "http://127.0.0.1:8188",
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


def comfy_json(endpoint: str, path: str, timeout: float = 3.0) -> Any:
    with urllib.request.urlopen(endpoint.rstrip("/") + path, timeout=timeout) as response:
        return json.load(response)


def comfy_options(endpoint: str, node: str, key: str) -> list[str]:
    info = comfy_json(endpoint, f"/object_info/{node}")
    spec = info[node]["input"]["required"][key]
    if isinstance(spec, list) and spec and isinstance(spec[0], list):
        return list(spec[0])
    return []


def short_error(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()
    return (text[0] if text else exc.__class__.__name__)[:90]


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
        self.ui_scale = ui_scale()
        if self.ui_scale != 1.0:
            self.tk.call("tk", "scaling", float(self.tk.call("tk", "scaling")) * self.ui_scale)
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
        self.gallery_buttons: dict[int, tk.Button] = {}
        self.pending_session_id: str | None = None
        self.pending_generation: int | None = None
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
        self._closing = False

        self.pc_ok = False
        self.comfy_ok = False
        self.has_selection = False

        self.title(f"StableCraft v{APP_VERSION} — PhotoCraft × ComfyUI")
        s = self.ui_scale
        self.geometry(f"{int(500 * s)}x{int(930 * s)}+20+20")
        self.minsize(int(460 * s), int(760 * s))
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
        style.configure("Title.TLabel", background=BG, foreground=FG, font=(UI_FONT, 18, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=(UI_FONT, 9))
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

    def _text(self, parent: tk.Misc, height: int, font: tuple[str, int] | tuple[str, int, str] = (UI_FONT, 10)) -> tk.Text:
        return tk.Text(
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
            header, text=tr(title), bg=BG, fg=MUTED, font=(UI_FONT, 9, "bold")
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
                font=(UI_FONT, 8),
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
            font=(UI_FONT, 20, "bold"),
        ).pack(side="left")
        tk.Label(
            title_row,
            text=f"v{APP_VERSION}",
            bg=PANEL_2,
            fg=ACCENT,
            padx=6,
            pady=1,
            font=(UI_FONT, 8, "bold"),
        ).pack(side="left", padx=(7, 0), pady=(5, 0))
        language_box = tk.Frame(title_row, bg=BG)
        language_box.pack(side="right")
        tk.Label(
            language_box,
            text=tr("Langue"),
            bg=BG,
            fg=MUTED,
            font=(UI_FONT, 8),
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
        tk.Label(
            header,
            text="Le lasso de Stable.art, dans PhotoCraft, avec ComfyUI.",
            bg=BG,
            fg=MUTED,
            font=(UI_FONT, 9),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=tr("par {author} · {repo}", author=AUTHOR, repo=REPO_URL),
            bg=BG,
            fg=MUTED,
            font=(UI_FONT, 7),
        ).pack(anchor="w", pady=(1, 4))
        self.update_label = tk.Label(
            header,
            text="",
            bg=BG,
            fg=YELLOW,
            anchor="w",
            font=(UI_FONT, 8),
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
            font=(UI_FONT, 8),
            cursor="hand2",
        )
        self.node_update_label.pack(fill="x")
        self.node_update_label.bind("<Button-1>", lambda _event: self._open_model_manager())

        status = tk.Frame(main, bg=PANEL, padx=10, pady=8, highlightthickness=1, highlightbackground=BORDER)
        status.pack(fill="x", pady=(4, 0))
        self.pc_status = tk.Label(status, text="PhotoCraft : connexion…", bg=PANEL, fg=YELLOW, anchor="w", font=(UI_FONT, 9))
        self.pc_status.pack(fill="x")
        self.comfy_status = tk.Label(status, text="ComfyUI : connexion…", bg=PANEL, fg=YELLOW, anchor="w", font=(UI_FONT, 9))
        self.comfy_status.pack(fill="x")
        self.doc_status = tk.Label(status, text="Document : —", bg=PANEL, fg=MUTED, anchor="w", font=(UI_FONT, 9))
        self.doc_status.pack(fill="x")
        self.sel_status = tk.Label(status, text="Sélection : —", bg=PANEL, fg=MUTED, anchor="w", font=(UI_FONT, 9))
        self.sel_status.pack(fill="x")
        self.models_status = tk.Label(status, text="Modèles : vérification…", bg=PANEL, fg=YELLOW, anchor="w", font=(UI_FONT, 9))
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
            font=(UI_FONT, 9, "bold"),
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
            font=(UI_FONT, 9, "bold"),
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
            font=(UI_FONT, 8),
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
            font=(UI_FONT, 9),
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
            font=(UI_FONT, 9),
        )
        self.ref_check.pack(anchor="w", pady=(4, 0))
        self.ref_profile_hint = tk.Label(
            ref_frame,
            text="",
            bg=BG,
            fg=YELLOW,
            anchor="w",
            font=(UI_FONT, 8),
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
            font=(UI_FONT, 8, "bold"),
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
            font=(UI_FONT, 8),
        )
        self.ref_hint.pack(fill="x", pady=(2, 4))
        self.ref_remove = tk.Button(
            ref_side,
            text="Retirer",
            command=self._remove_reference,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            font=(UI_FONT, 8),
            cursor="hand2",
            state="disabled",
        )
        self.ref_remove.pack(anchor="w")
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
        self.profile_combo = ttk.Combobox(
            prof_frame,
            textvariable=self.profile_var,
            values=self.profile_labels,
            state="readonly",
        )
        self.profile_combo.pack(fill="x", pady=(4, 2))
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_change)
        self._lock_scroll_wheel(self.profile_combo)
        self.profile_detail = tk.Label(prof_frame, text="", bg=BG, fg=MUTED, anchor="w", font=(UI_FONT, 9))
        self.profile_detail.pack(fill="x")
        self.profile_warning = tk.Label(
            prof_frame,
            text="",
            bg=BG,
            fg=YELLOW,
            anchor="w",
            justify="left",
            wraplength=420,
            font=(UI_FONT, 8),
        )
        self.quant_frame = tk.Frame(prof_frame, bg=BG)
        tk.Label(
            self.quant_frame,
            text=tr("Quantification"),
            bg=BG,
            fg=MUTED,
            font=(UI_FONT, 9),
        ).pack(side="left")
        self.quant_var = tk.StringVar()
        self.quant_combo = ttk.Combobox(
            self.quant_frame,
            textvariable=self.quant_var,
            values=[],
            state="readonly",
            width=14,
        )
        self.quant_combo.pack(side="left", padx=(6, 0))
        self.quant_combo.bind("<<ComboboxSelected>>", self._on_quant_change)
        self._lock_scroll_wheel(self.quant_combo)
        self.quant_map: dict[str, str] = {}

        settings = self._section(main, "RÉGLAGES")
        grid = tk.Frame(settings, bg=BG)
        grid.pack(fill="x", pady=(4, 0))
        for col in (1, 3):
            grid.columnconfigure(col, weight=1)
        self.padding_var = tk.StringVar(value="96")
        self.feather_var = tk.StringVar(value="10")
        self.steps_var = tk.StringVar(value="16")
        self.cfg_var = tk.StringVar(value="1.0")
        self.seed_var = tk.StringVar(value="-1")
        fields = [
            ("Contexte (px)", self.padding_var, 0, 0, 0, 512, 16),
            ("Feather (px)", self.feather_var, 0, 2, 0, 100, 1),
            ("Steps", self.steps_var, 1, 0, 1, 60, 1),
            ("CFG", self.cfg_var, 1, 2, 0, 20, 0.1),
            ("Seed (-1 = aléatoire)", self.seed_var, 2, 0, -1, 2**31 - 1, 1),
        ]
        for label, var, row, col, lo, hi, step in fields:
            tk.Label(grid, text=label, bg=BG, fg=MUTED, font=(UI_FONT, 9)).grid(
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
            font=(UI_FONT, 10, "bold"),
            cursor="hand2",
        )
        self.generate_btn.pack(side="left", fill="x", expand=True)
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
        self.models_btn = tk.Button(
            actions,
            text=tr("Modèles"),
            command=self._open_model_manager,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=10,
            pady=9,
            font=(UI_FONT, 9),
            cursor="hand2",
        )
        self.models_btn.pack(side="left", padx=(8, 0))
        self.action_hint = tk.Label(
            main, text="", bg=BG, fg=YELLOW, anchor="w", font=(UI_FONT, 8)
        )
        self.action_hint.pack(fill="x", pady=(3, 0))

        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack(fill="x", pady=(10, 0))
        self.progress_label = tk.Label(main, text="Prêt.", bg=BG, fg=MUTED, anchor="w", font=(UI_FONT, 9))
        self.progress_label.pack(fill="x", pady=(2, 0))

        gallery_frame = self._section(main, "GALERIE")
        self.gallery_title = tk.Label(
            gallery_frame,
            text="Aucune galerie",
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=(UI_FONT, 9),
        )
        self.gallery_title.pack(fill="x")
        self.gallery_canvas = tk.Canvas(
            gallery_frame,
            height=124,
            bg="#111114",
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.gallery_inner = tk.Frame(self.gallery_canvas, bg="#111114")
        self.gallery_window = self.gallery_canvas.create_window(
            (0, 0), window=self.gallery_inner, anchor="nw"
        )
        self.gallery_scroll = ttk.Scrollbar(
            gallery_frame, orient="horizontal", command=self.gallery_canvas.xview
        )
        self.gallery_canvas.configure(xscrollcommand=self.gallery_scroll.set)
        self.gallery_canvas.pack(fill="x", pady=(4, 0))
        self.gallery_scroll.pack(fill="x")
        self.gallery_inner.bind(
            "<Configure>",
            lambda _event: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all")),
        )
        self.gallery_hint = tk.Label(
            gallery_frame,
            text="Clique sur un calque StableCraft pour retrouver ses générations.",
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=(UI_FONT, 8),
        )
        self.gallery_hint.pack(fill="x", pady=(2, 0))

        preview_frame = self._section(main, "APERÇU")
        preview_tools = tk.Frame(preview_frame, bg=BG)
        preview_tools.pack(fill="x")
        self.preview_mode = tk.StringVar(value="document")
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
            font=(UI_FONT, 9),
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
            font=(UI_FONT, 9),
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
            font=(MONO_FONT, 8),
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
            font=(UI_FONT, 8),
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
            font=(UI_FONT, 8),
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
        self._last_mode = mode
        self._update_mode_hint()
        self._update_reference_for_profile()
        self._update_generate_state()
        self._check_models()

    def _load_profile(self, key: str) -> None:
        self.profile_key = key
        label = self._profile_label()
        if label:
            self.profile_var.set(label)
        profile = self.manifest["profiles"].get(key, {})
        pcfg = self.cfg.get("profiles", {}).get(key, {})
        settings = profile.get("settings", {})
        self.padding_var.set(str(pcfg.get("context_padding", 96)))
        self.feather_var.set(str(pcfg.get("feather", 10)))
        self.steps_var.set(str(pcfg.get("steps", settings.get("steps", 16))))
        self.cfg_var.set(str(pcfg.get("cfg", settings.get("cfg", 1.0))))
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
        self._update_generate_state()
        self._check_models()

    def _populate_quantizations(self) -> None:
        profile = self.manifest["profiles"].get(self.profile_key, {})
        pcfg = self.cfg.get("profiles", {}).get(self.profile_key, {})
        spec = (profile.get("files") or {}).get("unet", {})
        options = spec.get("quantizations") or profile.get("quantizations") or []
        self.quant_map = {}
        if len(options) < 2:
            if self.quant_frame.winfo_manager():
                self.quant_frame.pack_forget()
            return
        current = resolve_filename(self.profile_key, "unet", pcfg, profile)
        labels: list[str] = []
        for option in options:
            filename = str(option.get("filename", "?"))
            label = str(option.get("label", filename))
            self.quant_map[label] = filename
            labels.append(label)
            if filename == current:
                self.quant_var.set(label)
        if not self.quant_var.get() or self.quant_var.get() not in labels:
            custom = tr("Personnalisé : {filename}", filename=current)
            self.quant_map[custom] = current
            labels.insert(0, custom)
            self.quant_var.set(custom)
        self.quant_combo.config(values=labels)
        if not self.quant_frame.winfo_manager():
            self.quant_frame.pack(fill="x", pady=(3, 0))
        self.quant_combo.config(state="disabled" if self.running else "readonly")

    def _on_quant_change(self, _event: object = None) -> None:
        filename = self.quant_map.get(self.quant_var.get())
        if not filename:
            return
        if filename == resolve_filename(
            self.profile_key,
            "unet",
            self.cfg.get("profiles", {}).get(self.profile_key, {}),
            self.manifest["profiles"].get(self.profile_key, {}),
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

    def _form_values(self) -> dict[str, Any] | None:
        try:
            reference = self._reference_active_path()
            return {
                "seed": int(self.seed_var.get().strip()),
                "steps": int(self.steps_var.get()),
                "cfg": float(self.cfg_var.get().replace(",", ".")),
                "padding": int(self.padding_var.get()),
                "feather": int(self.feather_var.get()),
                "profile": self.profile_key,
                "mode": self._mode(),
                "prompt": self.prompt_text.get("1.0", "end").strip(),
                "negative": (
                    self.neg_text.get("1.0", "end").strip() if self.neg_var.get() else ""
                ),
                "reference": reference.name if reference else None,
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
                    and int(generation.get("padding", -1)) == values["padding"]
                    and str(generation.get("reference") or "")
                    == str(values.get("reference") or "")
                )
            except (TypeError, ValueError):
                continue
            if same:
                return index
        return None

    def _update_generate_state(self) -> None:
        values = self._form_values()
        duplicate = self._duplicate_generation()
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
        for button in self.gallery_buttons.values():
            button.config(state="disabled" if self.running else "normal")
        radio_state = "disabled" if self.running else "normal"
        self.edit_radio.config(state=radio_state)
        self.t2i_radio.config(state=radio_state)
        self.models_btn.config(state="disabled" if self.running else "normal")
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
                    }
                else:
                    pc = {
                        "ok": True,
                        "text": tr("PhotoCraft : connecté (aucun document)"),
                        "doc": None,
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

        try:
            if key in SUPPORTED_PROFILES:
                unet = resolve_filename(key, "unet", pcfg, profile)
                clip = resolve_filename(key, "text_encoder", pcfg, profile)
                vae = resolve_filename(key, "vae", pcfg, profile)
                clip_loader = "CLIPLoaderGGUF" if clip.lower().endswith(".gguf") else "CLIPLoader"
                unet_loader = "UnetLoaderGGUF" if unet.lower().endswith(".gguf") else "UNETLoader"
                if unet not in comfy_options(endpoint, unet_loader, "unet_name"):
                    add_missing("unet", unet)
                if clip not in comfy_options(endpoint, clip_loader, "clip_name"):
                    add_missing("text_encoder", clip)
                if vae not in comfy_options(endpoint, "VAELoader", "vae_name"):
                    add_missing("vae", vae)
                if files.get("lora") and mode == "edit":
                    lora = resolve_filename(key, "lora", pcfg, profile)
                    if lora not in comfy_options(endpoint, "LoraLoaderModelOnly", "lora_name"):
                        add_missing("lora", lora)
                needs_edit_nodes = mode == "edit" and key in KREA_PROFILES
                if needs_edit_nodes or key == QWEN_PROFILE:
                    for node in profile.get("requires_nodes", []):
                        try:
                            comfy_json(endpoint, f"/object_info/{node}")
                        except Exception:  # noqa: BLE001
                            add_missing("node", node, "Nœud ComfyUI manquant.")
                if needs_edit_nodes or (key == "krea2_edit" and mode == "t2i"):
                    try:
                        comfy_json(endpoint, "/object_info/EmptySD3LatentImage")
                    except Exception:  # noqa: BLE001
                        add_missing("node", "EmptySD3LatentImage", "Nœud ComfyUI manquant.")
        except Exception as exc:  # noqa: BLE001
            error = short_error(exc)
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
                elif kind == "log":
                    self._log(str(item[1]))
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
        self.current_selection = (
            list(doc["selectionBounds"])
            if doc and doc.get("hasSelection") and doc.get("selectionBounds")
            else None
        )
        self._sync_session_from_doc(doc)
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
        self.pc_ok = bool(pc["ok"])
        self.comfy_ok = bool(comfy["ok"])
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

    def _open_model_manager(self) -> None:
        from model_manager import ModelManager  # noqa: PLC0415 - avoids import cycle

        if self._model_manager is not None:
            try:
                if self._model_manager.winfo_exists():
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
            return tr("Disponible sur Krea 2, FLUX.3 Klein et Qwen Image 2.1.")
        if self._mode() == "t2i":
            if self.profile_key in KREA_PROFILES:
                return tr(
                    "Krea 2 utilise la référence en EDIT ; en T2I, passe en EDIT "
                    "pour une génération guidée par l'image."
                )
            return tr("La référence guide la génération T2I.")
        return tr("Disponible sur Krea 2, FLUX.3 Klein et Qwen Image 2.1.")

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
                font=(UI_FONT, 10, "bold"),
            )
            self.ref_canvas.create_text(
                56,
                70,
                text=tr("Clique ou dépose"),
                fill=MUTED,
                font=(UI_FONT, 7),
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

    def _set_reference_from_source(self, source: Path) -> None:
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

        if not pending and self.session_data:
            self.session_data["reference"] = {
                "image": "reference.png",
                "thumb": "reference_thumb.png",
                "name": source.name,
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
            source.name,
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
        width, height = int(660 * self.ui_scale), int(720 * self.ui_scale)
        x = self.winfo_rootx() + self.winfo_width() + 12
        y = self.winfo_rooty() + 40
        x = max(0, min(x, self.winfo_screenwidth() - width - 20))
        y = max(0, min(y, self.winfo_screenheight() - height - 40))
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.minsize(int(520 * self.ui_scale), int(520 * self.ui_scale))
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
            font=(UI_FONT, 9),
        )
        scroll = ttk.Scrollbar(window, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)

        text.tag_configure(
            "h1", font=(UI_FONT, 14, "bold"), foreground=FG, spacing1=6, spacing3=8
        )
        text.tag_configure(
            "h2", font=(UI_FONT, 10, "bold"), foreground=ACCENT, spacing1=12, spacing3=4
        )
        text.tag_configure("body", foreground=FG, spacing3=4)
        text.tag_configure(
            "code",
            font=(MONO_FONT, 9),
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
            "En T2I, FLUX.3 Klein et Qwen Image 2.1 utilisent la référence comme "
            "image 1 pour guider une nouvelle image. Krea 2 utilise la référence "
            "en EDIT.",
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
        add("• Krea 2, FLUX.3 Klein et Qwen Image 2.1 acceptent la référence. FLUX.2 Klein 9B ne la propose pas.", "body")
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
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes

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
                                dropped = buffer.value
                                if (
                                    not self._closing
                                    and dropped.lower().endswith(
                                        (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
                                    )
                                ):
                                    self.after(
                                        0,
                                        lambda value=dropped: self._set_reference_from_source(
                                            Path(value)
                                        ),
                                    )
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
            self._log("Drag & drop Windows activé.")
        except Exception as exc:  # noqa: BLE001
            self._log(tr("Drag & drop indisponible : {error}", error=short_error(exc)))

    def _disable_windows_drop(self) -> None:
        if self._drop_hwnd is None or self._win_user32 is None:
            return
        try:
            if self._old_wndproc:
                self._win_user32.SetWindowLongPtrW(
                    self._drop_hwnd, -4, self._old_wndproc
                )
            if self._win_shell32 is not None:
                self._win_shell32.DragAcceptFiles(self._drop_hwnd, False)
        except Exception:  # noqa: BLE001
            pass

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

    def _sync_session_from_doc(self, doc: dict[str, Any] | None) -> None:
        if self.running:
            return
        sid: str | None = None
        if doc:
            layer = self._find_layer(doc.get("layers", []), doc.get("activeLayer"))
            if layer:
                sid = parse_session_id(str(layer.get("name", "")))
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
            if stored and not self._same_selection(stored, self.current_selection):
                # A new lasso means a new session/layer: leave the old gallery
                # behind even while its layer is still the active one.
                sid = None
        if sid != self.session_id:
            self._load_session(sid)

    def _load_session(self, session_id: str | None, force: bool = False) -> None:
        if session_id == self.session_id and not force:
            return
        previous = self.session_id
        self.session_id = session_id
        self.session_data = None
        if not session_id:
            # A fresh lasso starts in EDIT, even if the previous canvas was
            # generated in T2I.
            self.mode_var.set("edit")
            self._last_mode = "edit"
            self._update_mode_hint()
        if session_id:
            try:
                self.session_data = self.session_store.load(session_id)
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
        for child in self.gallery_inner.winfo_children():
            child.destroy()
        self.gallery_images.clear()
        self.gallery_buttons.clear()

        if not self.session_data:
            self.gallery_title.config(text=tr("Aucune galerie"))
            self.gallery_hint.config(
                text=tr("Clique sur un calque StableCraft pour retrouver ses générations.")
            )
            self._set_document_preview()
            self._set_result_preview(None)
            return

        generations = self.session_data.get("generations", [])
        current = int(self.session_data.get("current", -1))
        self.gallery_title.config(
            text=tr(
                "Galerie — StableCraft [{session}] · {count} génération(s)",
                session=self.session_id,
                count=len(generations),
            )
        )
        if not generations:
            self.gallery_hint.config(text=tr("Aucune génération dans cette session."))
            self._set_document_preview()
            self._set_result_preview(None)
            return

        self._set_document_preview()
        self._set_result_preview(current if current >= 0 else None)
        session_dir = self.session_store.directory(str(self.session_id))
        for index, generation in enumerate(generations):
            thumb_rel = generation.get("thumb") or generation.get("result")
            path = session_dir / str(thumb_rel) if thumb_rel else None
            if not path or not path.exists():
                path = session_dir / str(generation.get("result", ""))
            try:
                image = tk.PhotoImage(file=str(path))
            except Exception:  # noqa: BLE001
                continue
            factor = max(1, math.ceil(max(image.width() / 104, image.height() / 104)))
            if factor > 1:
                image = image.subsample(factor, factor)
            self.gallery_images.append(image)
            selected = index == current
            button = tk.Button(
                self.gallery_inner,
                image=image,
                text=f"#{index + 1}",
                compound="top",
                bg=ACCENT if selected else PANEL_2,
                fg="white" if selected else FG,
                activebackground=ACCENT_ACTIVE,
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=4,
                pady=3,
                font=(UI_FONT, 8),
                state="disabled" if self.running else "normal",
                command=lambda idx=index: self._apply_generation(idx),
            )
            button.pack(side="left", padx=3, pady=3)
            self.gallery_buttons[index] = button

        if 0 <= current < len(generations):
            generation = generations[current]
            prompt = " ".join(str(generation.get("prompt", "")).split())
            if len(prompt) > 72:
                prompt = prompt[:71] + "…"
            self.gallery_hint.config(
                text=(
                    f"#{current + 1} · {str(generation.get('mode', 'edit')).upper()} · "
                    f"{generation.get('profile', '?')} · "
                    f"seed {generation.get('seed', '?')} · {prompt}"
                )
            )
        else:
            self.gallery_hint.config(
                text=tr("Clique sur une vignette pour appliquer cette génération.")
            )
        self.gallery_canvas.update_idletasks()
        self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))

    def _apply_generation(self, index: int) -> None:
        if self.running or not self.session_id or not self.session_data:
            return
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
        duplicate = self._duplicate_generation()
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
            "--seed",
            self.seed_var.get(),
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
        self._start_bridge(
            command,
            tr("Régénération en cours…") if reuse else tr("Génération en cours…"),
        )

    def _start_bridge(self, command: list[str], label: str) -> None:
        if self.running:
            return
        bridge = ROOT / "prototypes" / "bridge_cli.py"
        if not bridge.exists():
            messagebox.showerror(tr("Bridge introuvable"), str(bridge))
            return
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        if os.name != "nt":
            env.pop("PYTHONPATH", None)
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
        self.pending_session_id = None
        self.pending_generation = None
        self.progress.start(12)
        self.progress_label.config(text=label, fg=YELLOW)
        self.cancel_btn.config(state="normal")
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
        self.running = False
        self.progress.stop()
        self.cancel_btn.config(state="disabled")
        session_id = self.pending_session_id
        self.pending_session_id = None
        self.pending_generation = None
        self._update_reference_for_profile()
        if session_id:
            # Reload even after an apply error: the generated image is already
            # on disk and must remain selectable in the gallery.
            self._load_session(session_id, force=True)
        else:
            self._update_generate_state()
        if code == 0 and not self.last_error:
            self.progress_label.config(
                text=tr("Terminé — calque StableCraft prêt."), fg=GREEN
            )
        elif self.last_error:
            self.progress_label.config(text=tr("Erreur — voir le journal."), fg=RED)
        else:
            self.progress_label.config(
                text=tr("Processus terminé (code {code}).", code=code), fg=YELLOW
            )
        self.proc = None

    def _cancel(self) -> None:
        if self.proc and self.proc.poll() is None:
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

    def _check_krea_node(self) -> None:
        try:
            latest = latest_krea_release()
            status = krea_node_status(self.cfg, latest)
        except Exception:  # noqa: BLE001
            return
        self.queue.put(("krea_node", status, latest))

    def _update_krea_node_label(self) -> None:
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
                font=(UI_FONT, 9),
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
                font=(UI_FONT, 9),
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
