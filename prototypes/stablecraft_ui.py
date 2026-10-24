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
import subprocess
import sys
import threading
import time
import tomllib
import urllib.request
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
from control_client import ControlClient, ControlError, read_token  # noqa: E402
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

SUPPORTED_PROFILES = {"flux3_klein", "flux2_klein_9b", "krea2_edit"}


DEFAULTS: dict[str, Any] = {
    "app": {
        "default_profile": "flux3_klein",
        "sessions_dir": str(ROOT / "user" / "sessions"),
    },
    "photocraft": {
        "control_host": "127.0.0.1",
        "control_port": 7878,
        "control_token_file": str(ROOT / "user" / "control.token"),
        "automation_root": str(ROOT / "user"),
    },
    "comfyui": {
        "endpoint": "http://127.0.0.1:12452",
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


def file_name(path: str | None, fallback: str) -> str:
    return Path(path).name if path else fallback


class StableCraftApp(tk.Tk):
    def __init__(self, config_path: Path, initial_profile: str | None = None) -> None:
        super().__init__()
        self.config_path = config_path
        self.cfg = load_config(config_path)
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
        self.profile_key = initial_profile or str(self.cfg["app"].get("default_profile", "flux3_klein"))
        self.models_ok = True
        self._closing = False

        self.pc_ok = False
        self.comfy_ok = False
        self.has_selection = False

        self.title("StableCraft — PhotoCraft × ComfyUI")
        self.geometry("500x930+20+20")
        self.minsize(460, 760)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._style()
        self._build()
        self._load_profile(self.profile_key)
        self._load_preview(None)

        self.after(100, self._poll_queue)
        threading.Thread(target=self._refresh_loop, daemon=True).start()
        self._check_models()

    def _sessions_root(self) -> Path:
        configured = self.cfg.get("app", {}).get("sessions_dir")
        if configured:
            path = Path(str(configured))
            return path if path.is_absolute() else (ROOT / path)
        return ROOT / "user" / "sessions"

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

    def _text(self, parent: tk.Misc, height: int, font: tuple[str, int] | tuple[str, int, str] = ("Segoe UI", 10)) -> tk.Text:
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

    def _section(self, parent: tk.Misc, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=(8, 0))
        tk.Label(frame, text=title, bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
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
        self.main_canvas.bind_all(
            "<MouseWheel>",
            lambda event: self.main_canvas.yview_scroll(int(-event.delta / 120), "units"),
        )

        header = tk.Frame(main, bg=BG)
        header.pack(fill="x")
        tk.Label(header, text="StableCraft", bg=BG, fg=FG, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(
            header,
            text="Le lasso de Stable.art, dans PhotoCraft, avec ComfyUI.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 6))

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

        prompt_frame = self._section(main, "PROMPT")
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

        prof_frame = self._section(main, "PROFIL")
        self.profile_var = tk.StringVar()
        self.profile_labels: list[str] = []
        self.label_to_key: dict[str, str] = {}
        for key, profile in self.manifest["profiles"].items():
            label = profile["label"]
            if key not in SUPPORTED_PROFILES:
                label += " — bientôt"
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
        self.profile_detail = tk.Label(prof_frame, text="", bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 9))
        self.profile_detail.pack(fill="x")

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
        self.action_hint = tk.Label(
            main, text="", bg=BG, fg=YELLOW, anchor="w", font=("Segoe UI", 8)
        )
        self.action_hint.pack(fill="x", pady=(3, 0))

        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack(fill="x", pady=(10, 0))
        self.progress_label = tk.Label(main, text="Prêt.", bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 9))
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
            font=("Segoe UI", 8),
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
            text=f"Config : {self.config_path}",
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

    # ------------------------------------------------------------------
    # Profile / settings
    # ------------------------------------------------------------------

    def _profile_label(self) -> str:
        for label, key in self.label_to_key.items():
            if key == self.profile_key:
                return label
        return self.profile_labels[0] if self.profile_labels else ""

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
        detail = f"{self.steps_var.get()} steps · CFG {self.cfg_var.get()}"
        if weights:
            detail += f" · {weights} Go de poids"
        if vram:
            detail += f" · ~{vram} Go VRAM"
        if key not in SUPPORTED_PROFILES:
            detail += " · bientôt disponible"
        self.profile_detail.config(text=detail)
        self._update_generate_state()
        self._check_models()

    @staticmethod
    def _same_selection(
        left: list[int] | None, right: list[int] | None, tolerance: int = 2
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
            return {
                "seed": int(self.seed_var.get().strip()),
                "steps": int(self.steps_var.get()),
                "cfg": float(self.cfg_var.get().replace(",", ".")),
                "padding": int(self.padding_var.get()),
                "feather": int(self.feather_var.get()),
                "profile": self.profile_key,
                "prompt": self.prompt_text.get("1.0", "end").strip(),
                "negative": (
                    self.neg_text.get("1.0", "end").strip() if self.neg_var.get() else ""
                ),
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
                    and str(generation.get("prompt", "")).strip() == values["prompt"]
                    and str(generation.get("negative", "")).strip() == values["negative"]
                    and int(generation.get("steps", -1)) == values["steps"]
                    and abs(float(generation.get("cfg", -1)) - values["cfg"]) < 1e-6
                    and int(generation.get("padding", -1)) == values["padding"]
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
        enabled = (
            not self.running
            and self.profile_key in SUPPORTED_PROFILES
            and self.pc_ok
            and self.comfy_ok
            and self.models_ok
            and has_input
            and values is not None
            and duplicate is None
        )
        self.generate_btn.config(
            text="Régénérer" if reuse else "Générer",
            state="normal" if enabled else "disabled",
            bg=ACCENT if enabled else PANEL_2,
        )
        if duplicate is not None:
            self.action_hint.config(
                text=(
                    f"Cette combinaison existe déjà (#{duplicate + 1}). "
                    "Mets le seed à -1 ou change le prompt."
                )
            )
        elif values is None:
            self.action_hint.config(text="Vérifie les réglages (seed, steps, CFG…).")
        elif not has_input:
            self.action_hint.config(
                text="Fais un lasso, ou sélectionne un calque StableCraft pour régénérer."
            )
        else:
            self.action_hint.config(text="")
        for button in self.gallery_buttons.values():
            button.config(state="disabled" if self.running else "normal")

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
            pc: dict[str, Any] = {"ok": False, "text": "PhotoCraft : déconnecté", "doc": None}
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
                        "text": "PhotoCraft : connecté",
                        "doc": inspect,
                    }
                else:
                    pc = {"ok": True, "text": "PhotoCraft : connecté (aucun document)", "doc": None}
            except Exception as exc:  # noqa: BLE001 - status must never crash the UI
                pc["text"] = f"PhotoCraft : {short_error(exc)}"
            finally:
                if client is not None:
                    client.close_socket()

            comfy: dict[str, Any] = {"ok": False, "text": "ComfyUI : déconnecté"}
            try:
                stats = comfy_json(endpoint, "/system_stats", timeout=3.0)
                system = stats.get("system", {})
                devices = stats.get("devices", [])
                gpu = devices[0].get("name", "") if devices else ""
                vram = devices[0].get("vram_free", 0) / 1e9 if devices else 0
                comfy = {
                    "ok": True,
                    "text": f"ComfyUI : {system.get('comfyui_version', '?')} · {gpu} · {vram:.1f} Go libres",
                }
            except Exception as exc:  # noqa: BLE001
                comfy["text"] = f"ComfyUI : {short_error(exc)}"

            self.queue.put(("status", pc, comfy))
            self.stop_event.wait(3.0)

    def _check_models(self) -> None:
        threading.Thread(target=self._check_models_loop, daemon=True).start()

    def _check_models_loop(self) -> None:
        key = self.profile_key
        profile = self.manifest["profiles"].get(key, {})
        pcfg = self.cfg.get("profiles", {}).get(key, {})
        files = profile.get("files", {})
        endpoint = str(self.cfg["comfyui"]["endpoint"])
        missing: list[str] = []
        error: str | None = None
        try:
            if key in SUPPORTED_PROFILES:
                unet = file_name(pcfg.get("unet"), files["unet"]["filename"])
                clip = file_name(pcfg.get("text_encoder"), files["text_encoder"]["filename"])
                vae = file_name(pcfg.get("vae"), files["vae"]["filename"])
                clip_loader = "CLIPLoaderGGUF" if clip.lower().endswith(".gguf") else "CLIPLoader"
                if unet not in comfy_options(endpoint, "UnetLoaderGGUF", "unet_name"):
                    missing.append(unet)
                if clip not in comfy_options(endpoint, clip_loader, "clip_name"):
                    missing.append(clip)
                if vae not in comfy_options(endpoint, "VAELoader", "vae_name"):
                    missing.append(vae)
                for node in profile.get("requires_nodes", []):
                    try:
                        comfy_json(endpoint, f"/object_info/{node}")
                    except Exception:  # noqa: BLE001
                        missing.append(node)
                if key == "krea2_edit":
                    try:
                        comfy_json(endpoint, "/object_info/EmptySD3LatentImage")
                    except Exception:  # noqa: BLE001
                        missing.append("EmptySD3LatentImage")
        except Exception as exc:  # noqa: BLE001
            error = short_error(exc)
        self.queue.put(("models", key, missing, error))

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "status":
                    self._handle_status(item[1], item[2])
                elif kind == "models":
                    self._handle_models(item[1], item[2], item[3])
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
        if doc:
            self.doc_status.config(
                text=f"Document : {doc.get('name', '?')} · {doc.get('width')}×{doc.get('height')} · {doc.get('mode')}/{doc.get('depth')} bits",
                fg=MUTED,
            )
            if doc.get("hasSelection"):
                x, y, w, h = doc.get("selectionBounds") or [0, 0, 0, 0]
                self.sel_status.config(text=f"Sélection : {w}×{h} à ({x},{y})", fg=GREEN)
            elif self.session_id:
                self.sel_status.config(text="Sélection : aucune — galerie disponible", fg=YELLOW)
            else:
                self.sel_status.config(text="Sélection : aucune — fais un lasso", fg=YELLOW)
        else:
            self.doc_status.config(text="Document : aucun", fg=MUTED)
            self.sel_status.config(text="Sélection : —", fg=MUTED)
        self.pc_ok = bool(pc["ok"])
        self.comfy_ok = bool(comfy["ok"])
        self.has_selection = bool(doc and doc.get("hasSelection"))
        self._update_generate_state()

    def _handle_models(self, key: str, missing: list[str], error: str | None) -> None:
        if key != self.profile_key:
            return
        if error:
            self.models_ok = False
            self.models_status.config(text=f"Modèles : vérification impossible ({error})", fg=YELLOW)
            self._update_generate_state()
            return
        if missing:
            self.models_ok = False
            self.models_status.config(text=f"Modèles manquants : {', '.join(missing)}", fg=RED)
        else:
            self.models_ok = True
            self.models_status.config(text="Modèles : OK", fg=GREEN)
        self._update_generate_state()

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
        self.session_id = session_id
        self.session_data = None
        if session_id:
            try:
                self.session_data = self.session_store.load(session_id)
            except Exception as exc:  # noqa: BLE001
                self._log(f"Session {session_id} : {short_error(exc)}")
        self._populate_gallery()
        if self.session_data:
            # `_restore_session_fields` deliberately leaves the seed field alone:
            # the seed used by a generation is shown in the gallery hint, and the
            # user's field must stay on -1 unless they typed a value themselves.
            self._restore_session_fields(self.session_data)
        self._update_generate_state()

    def _restore_session_fields(self, sdata: dict[str, Any]) -> None:
        generations = sdata.get("generations", [])
        index = int(sdata.get("current", -1))
        if not (0 <= index < len(generations)):
            return
        generation = generations[index]
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

    def _populate_gallery(self) -> None:
        for child in self.gallery_inner.winfo_children():
            child.destroy()
        self.gallery_images.clear()
        self.gallery_buttons.clear()

        if not self.session_data:
            self.gallery_title.config(text="Aucune galerie")
            self.gallery_hint.config(
                text="Clique sur un calque StableCraft pour retrouver ses générations."
            )
            return

        generations = self.session_data.get("generations", [])
        current = int(self.session_data.get("current", -1))
        self.gallery_title.config(
            text=f"Galerie — StableCraft [{self.session_id}] · {len(generations)} génération(s)"
        )
        if not generations:
            self.gallery_hint.config(text="Aucune génération dans cette session.")
            return

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
                font=("Segoe UI", 8),
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
                    f"#{current + 1} · {generation.get('profile', '?')} · "
                    f"seed {generation.get('seed', '?')} · {prompt}"
                )
            )
        else:
            self.gallery_hint.config(text="Clique sur une vignette pour appliquer cette génération.")
        self.gallery_canvas.update_idletasks()
        self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))

    def _apply_generation(self, index: int) -> None:
        if self.running or not self.session_id or not self.session_data:
            return
        generations = self.session_data.get("generations", [])
        if not 0 <= index < len(generations):
            return
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
            return None, (
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
            messagebox.showinfo("Bientôt", "Ce profil sera ajouté plus tard.")
            return
        reuse = self._reusable_session()
        if not self.has_selection and not reuse:
            messagebox.showwarning(
                "Sélection vide",
                "Fais un lasso autour de la zone à modifier, ou sélectionne un "
                "calque StableCraft pour régénérer avec sa sélection d'origine.",
            )
            return
        duplicate = self._duplicate_generation()
        if duplicate is not None:
            messagebox.showinfo(
                "Déjà généré",
                f"Cette combinaison existe déjà dans la galerie (#{duplicate + 1}).\n\n"
                "Mets le seed à -1 ou change le prompt pour régénérer.",
            )
            return
        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("Prompt vide", "Écris ce que tu veux changer.")
            return
        negative = self.neg_text.get("1.0", "end").strip() if self.neg_var.get() else ""
        python, error = self._comfy_python()
        if error:
            messagebox.showerror("Python ComfyUI introuvable", error)
            return
        bridge = ROOT / "prototypes" / "bridge_cli.py"
        if not bridge.exists():
            messagebox.showerror("Bridge introuvable", str(bridge))
            return

        command = [
            python,
            str(bridge),
            "--config",
            str(self.config_path),
            "--profile",
            self.profile_key,
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
        if negative:
            command += ["--negative", negative]
        self._start_bridge(
            command,
            "Régénération en cours…" if reuse else "Génération en cours…",
        )

    def _start_bridge(self, command: list[str], label: str) -> None:
        if self.running:
            return
        bridge = ROOT / "prototypes" / "bridge_cli.py"
        if not bridge.exists():
            messagebox.showerror("Bridge introuvable", str(bridge))
            return
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
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
            messagebox.showerror("Lancement impossible", short_error(exc))
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
        if session_id:
            # Reload even after an apply error: the generated image is already
            # on disk and must remain selectable in the gallery.
            self._load_session(session_id, force=True)
        else:
            self._update_generate_state()
        if code == 0 and not self.last_error:
            self.progress_label.config(text="Terminé — calque StableCraft prêt.", fg=GREEN)
        elif self.last_error:
            self.progress_label.config(text="Erreur — voir le journal.", fg=RED)
        else:
            self.progress_label.config(text=f"Processus terminé (code {code}).", fg=YELLOW)
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
            self.progress_label.config(text="Annulation…", fg=YELLOW)

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
                text="Aucun aperçu.\nFais un lasso, écris un prompt, puis clique Générer.",
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
                text=f"Aperçu indisponible : {short_error(exc)}",
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
            os.startfile(str(self.config_path))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            self._log(f"Config : {self.config_path}")

    def _on_close(self) -> None:
        self._closing = True
        self.stop_event.set()
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
