"""Captioning tool: ComfyUI-only engines, installed on demand.

Florence-2 stays the zero-install fallback.  CapRL-Qwen3VL-4B, Qwen3.5-9B
and JoyCaption Beta One run through ComfyUI custom nodes and GGUF models.
Nothing is installed by the main setup: the caption manager downloads the
node, the vision backend and the model only when the user asks for it.
"""

from __future__ import annotations

import json
import os
import queue
import random
import subprocess
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from caption_engines import (
    ENGINE_BY_ID,
    ENGINES,
    CaptionEngine,
    style_by_id,
)
from caption_install import engine_status
from i18n import profile_text, tr

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

ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"


class CaptionWindow(tk.Toplevel):
    """Image-to-prompt window with optional ComfyUI caption engines."""

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.app = app
        self.image_path: Path | None = None
        self.image_name = ""
        self.image_size: tuple[int, int] | None = None
        self.busy = False
        self.cancelled = False
        self._tag_warning = False
        self._closing = False
        self._app_busy = bool(getattr(app, "running", False))
        self._result = ""
        self._last_dir = Path.home()
        self._preview_photo: tk.PhotoImage | None = None

        self._model_options: list[str] = []
        self._models_loaded = False
        self._model_waiting = False
        self._model_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self._engines = list(ENGINES)
        self._engine_labels: list[str] = []
        self._engine_by_label: dict[str, str] = {}
        self._style_by_label: dict[str, str] = {}
        self._status_cache: dict[str, dict[str, Any]] = {}
        self._manager: Any = None

        self.title(tr("StableCraft — Captioning"))
        self.geometry("1000x720+520+30")
        self.minsize(900, 620)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        self._load_engines()
        self._load_models()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        main = tk.Frame(self, bg=BG, padx=16, pady=14)
        main.pack(fill="both", expand=True)

        header = tk.Frame(main, bg=BG)
        header.pack(fill="x")
        tk.Label(
            header,
            text=tr("Captioning"),
            bg=BG,
            fg=FG,
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left")
        tk.Label(
            main,
            text=tr(
                "Transforme une image en prompt. Choisis le moteur selon le "
                "résultat voulu : captioning pur, tags/LoRA, ou analyse "
                "généraliste. Tout passe par ComfyUI."
            ),
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=940,
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(2, 10))

        body = tk.Frame(main, bg=BG)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y")
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))

        self._build_image_column(left)
        self._build_settings_column(right)

    def _build_image_column(self, parent: tk.Misc) -> None:
        tk.Label(
            parent,
            text=tr("IMAGE"),
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).pack(fill="x")

        self.preview_canvas = tk.Canvas(
            parent,
            width=280,
            height=280,
            bg="#111114",
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.preview_canvas.pack(pady=(4, 6))
        self.preview_canvas.create_text(
            140,
            140,
            text=tr("Aucune image.\nChoisis un fichier ou colle une image."),
            fill=MUTED,
            font=("Segoe UI", 9),
            justify="center",
        )

        self.image_label = tk.Label(
            parent,
            text=tr("Aucune image."),
            bg=BG,
            fg=FG,
            anchor="w",
            justify="left",
            wraplength=280,
            font=("Segoe UI", 9, "bold"),
        )
        self.image_label.pack(fill="x")
        self.size_label = tk.Label(
            parent,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 8),
        )
        self.size_label.pack(fill="x", pady=(1, 8))

        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x")
        self.choose_btn = self._button(
            row, tr("Choisir une image…"), self._choose_image, width=17
        )
        self.choose_btn.pack(side="left")
        self.paste_btn = self._button(row, tr("Coller"), self._paste_image, width=8)
        self.paste_btn.pack(side="left", padx=(6, 0))
        tk.Label(
            parent,
            text=tr("PNG, JPG, WebP, BMP, TIFF. L'image est réduite à 2048 px."),
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=280,
            font=("Segoe UI", 8),
        ).pack(fill="x", pady=(6, 0))

    def _build_settings_column(self, parent: tk.Misc) -> None:
        tk.Label(
            parent,
            text=tr("RÉGLAGES"),
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).pack(fill="x")

        engine_row = tk.Frame(parent, bg=BG)
        engine_row.pack(fill="x", pady=(4, 0))
        tk.Label(
            engine_row,
            text=tr("Moteur"),
            bg=BG,
            fg=FG,
            width=14,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(side="left")
        self.engine_var = tk.StringVar()
        self.engine_combo = ttk.Combobox(
            engine_row,
            textvariable=self.engine_var,
            values=[],
            state="readonly",
            width=38,
        )
        self.engine_combo.pack(side="left")
        self.engine_combo.bind("<<ComboboxSelected>>", self._on_engine_change)
        self.manage_btn = self._button(
            engine_row, tr("Gérer les moteurs…"), self._open_manager, small=True
        )
        self.manage_btn.pack(side="left", padx=(6, 0))

        self.engine_status = tk.Label(
            parent,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=590,
            font=("Segoe UI", 8),
        )
        self.engine_status.pack(fill="x", pady=(2, 0))

        self.model_row = tk.Frame(parent, bg=BG)
        tk.Label(
            self.model_row,
            text=tr("Modèle Florence"),
            bg=BG,
            fg=FG,
            width=14,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(side="left")
        self.model_var = tk.StringVar(value=tr("Recherche…"))
        self.model_combo = ttk.Combobox(
            self.model_row,
            textvariable=self.model_var,
            values=[],
            state="disabled",
            width=42,
        )
        self.model_combo.pack(side="left")
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_change)
        self.reload_btn = self._button(
            self.model_row, tr("Recharger"), self._load_models, width=10, small=True
        )
        self.reload_btn.pack(side="left", padx=(6, 0))

        self.style_row = tk.Frame(parent, bg=BG)
        self.style_row.pack(fill="x", pady=(6, 0))
        tk.Label(
            self.style_row,
            text=tr("Style"),
            bg=BG,
            fg=FG,
            width=14,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(side="left")
        self.style_var = tk.StringVar()
        self.style_combo = ttk.Combobox(
            self.style_row,
            textvariable=self.style_var,
            values=[],
            state="readonly",
            width=42,
        )
        self.style_combo.pack(side="left")
        self.style_combo.bind("<<ComboboxSelected>>", self._on_style_change)

        self.model_row.pack(fill="x", pady=(6, 0), before=self.style_row)

        self.device_row = tk.Frame(parent, bg=BG)
        tk.Label(
            self.device_row,
            text=tr("Calcul"),
            bg=BG,
            fg=FG,
            width=14,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(side="left")
        self.device_var = tk.StringVar(value=tr("GPU (auto)"))
        self.device_combo = ttk.Combobox(
            self.device_row,
            textvariable=self.device_var,
            values=[tr("GPU (auto)"), tr("CPU")],
            state="readonly",
            width=16,
        )
        self.device_combo.pack(side="left")
        tk.Label(
            self.device_row,
            text=tr("CPU = plus lent, zéro VRAM."),
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(8, 0))

        self.task_hint = tk.Label(
            parent,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=590,
            font=("Segoe UI", 8),
        )
        self.task_hint.pack(fill="x", pady=(4, 0))

        self.profile_hint = tk.Label(
            parent,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=590,
            font=("Segoe UI", 8),
        )
        self.profile_hint.pack(fill="x", pady=(2, 6))
        profile = self.app.manifest["profiles"].get(self.app.profile_key, {})
        label = profile_text(profile, "label") or self.app.profile_key
        self.profile_hint.config(
            text=tr(
                "Profil actif : {profile}. Le résultat est en anglais, comme "
                "les prompts des modèles.",
                profile=label,
            )
        )

        self.analyse_btn = tk.Button(
            parent,
            text=tr("Analyser l'image"),
            command=self._analyze,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_ACTIVE,
            activeforeground="white",
            relief="flat",
            bd=0,
            pady=7,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            state="disabled",
            disabledforeground=MUTED,
        )
        self.analyse_btn.pack(fill="x", pady=(0, 4))

        self.status_label = tk.Label(
            parent,
            text=tr("Prêt."),
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=590,
            font=("Segoe UI", 8),
        )
        self.status_label.pack(fill="x")

        result_header = tk.Frame(parent, bg=BG)
        result_header.pack(fill="x", pady=(10, 2))
        tk.Label(
            result_header,
            text=tr("RÉSULTAT"),
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        self.count_label = tk.Label(
            result_header,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="e",
            font=("Segoe UI", 8),
        )
        self.count_label.pack(side="right")

        text_frame = tk.Frame(parent, bg=BG)
        text_frame.pack(fill="both", expand=True)
        self.result_text = tk.Text(
            text_frame,
            height=10,
            wrap="word",
            bg=PANEL,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            padx=8,
            pady=6,
            font=("Segoe UI", 9),
        )
        self.result_text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(
            text_frame, orient="vertical", command=self.result_text.yview
        )
        scrollbar.pack(side="right", fill="y")
        self.result_text.configure(yscrollcommand=scrollbar.set)
        self.result_text.bind("<KeyRelease>", lambda _event: self._sync_result())

        actions = tk.Frame(parent, bg=BG)
        actions.pack(fill="x", pady=(6, 0))
        self.replace_btn = self._button(
            actions,
            tr("Remplacer le prompt"),
            lambda: self._use_result(replace=True),
            primary=True,
        )
        self.replace_btn.pack(side="left")
        self.append_btn = self._button(
            actions,
            tr("Ajouter au prompt"),
            lambda: self._use_result(replace=False),
        )
        self.append_btn.pack(side="left", padx=(6, 0))
        self.copy_btn = self._button(actions, tr("Copier"), self._copy)
        self.copy_btn.pack(side="left", padx=(6, 0))
        self.clear_btn = self._button(actions, tr("Effacer"), self._clear)
        self.clear_btn.pack(side="left", padx=(6, 0))

        self.note_label = tk.Label(
            parent,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=590,
            font=("Segoe UI", 8),
        )
        self.note_label.pack(fill="x", pady=(6, 0))

        self._update_controls()

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        command: Any,
        *,
        width: int | None = None,
        primary: bool = False,
        small: bool = False,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            width=width or 0,
            bg=ACCENT if primary else PANEL_2,
            fg="white" if primary else FG,
            activebackground=ACCENT_ACTIVE if primary else BORDER,
            activeforeground="white" if primary else FG,
            relief="flat",
            bd=0,
            padx=10,
            pady=5 if small else 6,
            font=("Segoe UI", 8 if small else 9),
            cursor="hand2",
            disabledforeground=MUTED,
        )

    # ------------------------------------------------------------------
    # Engine selection
    # ------------------------------------------------------------------

    def _load_engines(self) -> None:
        if self.busy:
            return
        self._engines = list(ENGINES)
        self._engine_labels = [tr(engine.label) for engine in self._engines]
        self._engine_by_label = {
            tr(engine.label): engine.id for engine in self._engines
        }
        self.engine_combo.config(values=self._engine_labels)
        current = self._engine_id() if self.engine_var.get() else ""
        selected = ENGINE_BY_ID.get(current)
        if selected is None:
            selected = next(
                (
                    engine
                    for engine in self._engines
                    if engine.family != "florence"
                    and engine_status(engine, self.app.cfg)["ready"]
                ),
                ENGINE_BY_ID["florence2"],
            )
        self.engine_var.set(tr(selected.label))
        self._status_cache.clear()
        self._refresh_engine_ui()

    def _engine_id(self) -> str:
        label = self.engine_var.get() if hasattr(self, "engine_var") else ""
        return self._engine_by_label.get(label, "florence2")

    def _engine(self) -> CaptionEngine:
        return ENGINE_BY_ID.get(self._engine_id(), ENGINE_BY_ID["florence2"])

    def _engine_status(self, engine: CaptionEngine, *, refresh: bool = False) -> dict[str, Any]:
        if engine.family == "florence":
            return {
                "ready": self._models_loaded,
                "node": True,
                "loaded": self._models_loaded,
                "vision": True,
                "models": True,
                "missing": [] if self._models_loaded else ["florence"],
            }
        if refresh or engine.id not in self._status_cache:
            self._status_cache[engine.id] = engine_status(engine, self.app.cfg)
        return self._status_cache[engine.id]

    def _engine_missing_text(self, engine: CaptionEngine, status: dict[str, Any]) -> str:
        missing: list[str] = []
        if not status["node"]:
            missing.append(tr("node manquant"))
        elif not status["loaded"]:
            missing.append(tr("redémarrage de ComfyUI requis"))
        if not status["vision"]:
            missing.append(tr("backend vision manquant"))
        if not status["models"]:
            missing.append(
                tr("modèle manquant ({size} Go)", size=f"{engine.download_size_gb:.1f}")
            )
        return " · ".join(missing)

    def _refresh_engine_ui(self) -> None:
        engine = self._engine()
        status = self._engine_status(engine, refresh=True)
        if engine.family == "florence":
            if self._models_loaded:
                text = tr("Florence-2 · ComfyUI · prêt")
                color = GREEN
            elif self._model_waiting:
                text = tr("Florence-2 : vérification…")
                color = YELLOW
            else:
                text = tr("Florence-2 indisponible : voir le journal.")
                color = RED
        elif status["ready"]:
            text = tr("Prêt · node, backend vision et modèle installés")
            color = GREEN
        else:
            text = self._engine_missing_text(engine, status)
            color = YELLOW
            if not self.app.comfy_ok:
                text = tr("ComfyUI déconnecté · ") + text
                color = RED
        self.engine_status.config(text=text, fg=color)

        self._style_by_label = {
            tr(style.label): style.id for style in engine.styles
        }
        self.style_combo.config(values=[tr(style.label) for style in engine.styles])
        self.style_var.set(tr(engine.styles[0].label))
        self._on_style_change()

        if engine.family == "florence":
            if not self.model_row.winfo_manager():
                self.model_row.pack(fill="x", pady=(6, 0), before=self.style_row)
        else:
            if self.model_row.winfo_manager():
                self.model_row.pack_forget()

        if engine.family == "florence":
            if self.device_row.winfo_manager():
                self.device_row.pack_forget()
            self.note_label.config(
                text=tr(
                    "Florence-2 est chargé dans ComfyUI puis déchargé après "
                    "l'analyse. Aucun téléchargement supplémentaire."
                )
            )
        else:
            if not self.device_row.winfo_manager():
                self.device_row.pack(fill="x", pady=(6, 0), before=self.task_hint)
            self.note_label.config(
                text=tr(
                    "Le node et le modèle sont installés à la demande depuis "
                    "« Gérer les moteurs… ». Ils tournent dans ComfyUI ; aucun "
                    "serveur séparé. Le premier chargement peut être long."
                )
            )
        self._update_controls()

    def _on_engine_change(self, _event: object = None) -> None:
        self._refresh_engine_ui()

    def _on_style_change(self, _event: object = None) -> None:
        engine = self._engine()
        style = style_by_id(engine, self._style_key())
        text = tr(engine.description)
        if engine.family != "florence":
            text += "\n" + tr("Style : {style}.", style=tr(style.label))
        self.task_hint.config(text=text)

    def _style_key(self) -> str:
        engine = self._engine()
        return self._style_by_label.get(
            self.style_var.get(), engine.styles[0].id
        )

    def _open_manager(self) -> None:
        if self.busy:
            return
        if self._manager is not None:
            try:
                if self._manager.winfo_exists():
                    self._manager.deiconify()
                    self._manager.lift()
                    self._manager.focus_force()
                    return
            except Exception:  # noqa: BLE001
                pass
        from caption_manager import CaptionManager  # noqa: PLC0415

        self._manager = CaptionManager(
            self.app, on_changed=self._on_engines_changed
        )

    def _on_engines_changed(self) -> None:
        self._status_cache.clear()
        self._refresh_engine_ui()

    # ------------------------------------------------------------------
    # Florence model discovery
    # ------------------------------------------------------------------

    def _load_models(self) -> None:
        if self._model_waiting or self.busy:
            return
        endpoint = str(self.app.cfg["comfyui"]["endpoint"])
        self._models_loaded = False
        self._model_options = []
        self._model_waiting = True
        self.model_combo.config(values=[tr("Recherche…")], state="disabled")
        self.model_var.set(tr("Recherche…"))
        if self._engine_id() == "florence2":
            self.engine_status.config(
                text=tr("Florence-2 : vérification…"), fg=YELLOW
            )
        self._update_controls()
        threading.Thread(
            target=self._fetch_models_worker,
            args=(endpoint,),
            daemon=True,
        ).start()
        self.after(120, self._poll_model_queue)

    def _fetch_models_worker(self, endpoint: str) -> None:
        url = endpoint.rstrip("/") + "/object_info/Florence2ModelLoader"
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                info = json.load(response)
            spec = info["Florence2ModelLoader"]["input"]["required"]["model"]
            values = (
                list(spec[0])
                if isinstance(spec, list)
                and spec
                and isinstance(spec[0], list)
                else []
            )
            self._model_queue.put(("ok", values))
        except urllib.error.HTTPError:
            self._model_queue.put(("missing", ""))
        except Exception as exc:  # noqa: BLE001
            self._model_queue.put(("error", str(exc)))

    def _poll_model_queue(self) -> None:
        if self._closing:
            return
        try:
            while True:
                kind, payload = self._model_queue.get_nowait()
                self._model_waiting = False
                if kind == "ok":
                    self._apply_models(payload)
                elif kind == "missing":
                    self._models_failed(
                        tr(
                            "Le nœud comfyui-florence2 n'est pas installé. "
                            "Installe-le puis redémarre ComfyUI."
                        )
                    )
                else:
                    self._models_failed(
                        tr(
                            "Florence-2 indisponible : {error}",
                            error=str(payload)[:160],
                        )
                    )
        except queue.Empty:
            pass
        if self._model_waiting:
            self.after(120, self._poll_model_queue)

    def _apply_models(self, payload: Any) -> None:
        values = [str(value) for value in payload]
        values.sort(
            key=lambda name: (
                0
                if "promptgen" in name.lower()
                else 1
                if "large" in name.lower()
                else 2,
                name.lower(),
            )
        )
        if not values:
            self._models_failed(
                tr(
                    "Aucun modèle Florence-2 dans models/LLM. "
                    "Place Florence-2-base-PromptGen-v2.0 dans le dossier LLM."
                )
            )
            return
        self._model_options = values
        self._models_loaded = True
        self.model_combo.config(values=values)
        preferred = next(
            (name for name in values if "promptgen" in name.lower()), values[0]
        )
        self.model_var.set(preferred)
        self.status_label.config(text=tr("Prêt."), fg=MUTED)
        if self._engine_id() == "florence2":
            self._refresh_engine_ui()
        else:
            self._update_controls()

    def _models_failed(self, message: str) -> None:
        self._models_loaded = False
        self._model_options = []
        self.model_combo.config(values=[tr("Aucun")], state="disabled")
        self.model_var.set(tr("Aucun"))
        if self._engine_id() == "florence2":
            self.engine_status.config(text=message, fg=RED)
            self.status_label.config(text=message, fg=RED)
        self._update_controls()

    def _on_model_change(self, _event: object = None) -> None:
        model = self.model_var.get()
        if "promptgen" not in model.lower() and self._style_key() != "description":
            self.status_label.config(
                text=tr(
                    "Ce modèle Florence-2 ne gère que la description. "
                    "Choisis un PromptGen pour les tags et le prompt mixte."
                ),
                fg=YELLOW,
            )
        elif not self.busy:
            self.status_label.config(text=tr("Prêt."), fg=MUTED)

    # ------------------------------------------------------------------
    # Image handling
    # ------------------------------------------------------------------

    def _work_dir(self) -> Path:
        root = self.app.session_store.root.parent / "caption"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _choose_image(self) -> None:
        if self.busy:
            return
        selected = filedialog.askopenfilename(
            title=tr("Choisir une image à décrire"),
            initialdir=str(self._last_dir),
            filetypes=[
                ("Images", IMAGE_SUFFIXES),
                (tr("Tous les fichiers"), "*.*"),
            ],
        )
        if selected:
            self._last_dir = Path(selected).parent
            self._set_image(Path(selected))

    def _paste_image(self) -> None:
        if self.busy:
            return
        python, error = self.app._comfy_python()
        if error:
            messagebox.showerror(tr("Python ComfyUI introuvable"), error)
            return
        script = ROOT / "prototypes" / "clipboard_image.py"
        output = self._work_dir() / "clipboard.png"
        flags = 0x08000000 if os.name == "nt" else 0
        try:
            result = subprocess.run(
                [python, str(script), "--output", str(output)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                creationflags=flags,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(tr("Presse-papiers"), str(exc))
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
        self._set_image(path, display_name=display)

    def _set_image(self, source: Path, display_name: str | None = None) -> None:
        if self.busy:
            return
        # A caption belongs to one image; do not leave the previous result
        # looking valid for the new one.
        self.result_text.delete("1.0", "end")
        self._result = ""
        self._tag_warning = False
        self.count_label.config(text="")
        python, error = self.app._comfy_python()
        if error:
            messagebox.showerror(tr("Python ComfyUI introuvable"), error)
            return
        script = ROOT / "prototypes" / "reference_image.py"
        work = self._work_dir()
        image_path = work / "input.png"
        thumb_path = work / "thumb.png"
        self.status_label.config(text=tr("Préparation de l'image…"), fg=YELLOW)
        self.update_idletasks()
        flags = 0x08000000 if os.name == "nt" else 0
        try:
            result = subprocess.run(
                [
                    python,
                    str(script),
                    "--source",
                    str(source),
                    "--image",
                    str(image_path),
                    "--thumb",
                    str(thumb_path),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
                creationflags=flags,
            )
        except Exception as exc:  # noqa: BLE001
            self.status_label.config(text=str(exc)[:200], fg=RED)
            return
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            self.status_label.config(
                text=details[:200] or tr("Image invalide."), fg=RED
            )
            return
        try:
            info = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            info = {}
        try:
            self._preview_photo = tk.PhotoImage(file=str(thumb_path))
        except tk.TclError:
            self._preview_photo = None
        self.image_path = image_path
        self.image_name = display_name or source.name
        self.image_size = (
            int(info.get("width") or 0),
            int(info.get("height") or 0),
        )
        self.preview_canvas.delete("all")
        if self._preview_photo is not None:
            self.preview_canvas.create_image(
                140, 140, image=self._preview_photo
            )
        self.image_label.config(text=self.image_name)
        if self.image_size and all(self.image_size):
            self.size_label.config(
                text=tr(
                    "{width} × {height} px",
                    width=self.image_size[0],
                    height=self.image_size[1],
                )
            )
        else:
            self.size_label.config(text="")
        self.status_label.config(text=tr("Prêt."), fg=MUTED)
        self._update_controls()

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _analyze(self) -> None:
        if self.busy or self._app_busy:
            return
        if self.image_path is None:
            messagebox.showwarning(
                tr("Captioning"), tr("Choisis d'abord une image.")
            )
            return
        engine = self._engine()
        if engine.family == "florence":
            self._analyze_florence(engine)
        else:
            self._analyze_comfy(engine)

    def _analyze_florence(self, engine: CaptionEngine) -> None:
        if not self._models_loaded:
            messagebox.showwarning(
                tr("Captioning"),
                tr("Aucun modèle Florence-2 disponible dans ComfyUI."),
            )
            return
        model = self.model_var.get().strip()
        if model not in self._model_options:
            messagebox.showwarning(
                tr("Captioning"), tr("Choisis un modèle Florence-2.")
            )
            return
        if "promptgen" not in model.lower() and self._style_key() != "description":
            messagebox.showwarning(
                tr("Captioning"),
                tr(
                    "Ce modèle Florence-2 ne gère que la description. "
                    "Choisis un PromptGen pour les tags et le prompt mixte."
                ),
            )
            return
        if not self.app.comfy_ok:
            messagebox.showwarning(
                tr("Captioning"), tr("ComfyUI doit être connecté.")
            )
            return
        self._start_caption_job(
            {
                "engine": "florence2",
                "task": self._style_key(),
                "model": model,
                "image": str(self.image_path),
                "seed": random.randrange(1, 2**31 - 1),
                "profile": self.app.profile_key,
            }
        )

    def _analyze_comfy(self, engine: CaptionEngine) -> None:
        if not self.app.comfy_ok:
            messagebox.showwarning(
                tr("Captioning"), tr("ComfyUI doit être connecté.")
            )
            return
        status = self._engine_status(engine, refresh=True)
        if not status["ready"]:
            details = self._engine_missing_text(engine, status)
            if messagebox.askyesno(
                tr("Moteur non installé"),
                tr(
                    "{label} nécessite encore : {details}.\n\n"
                    "Ouvrir le gestionnaire pour l'installer ?",
                    label=tr(engine.label),
                    details=details,
                ),
            ):
                self._open_manager()
            return
        device = "cpu" if self.device_var.get().startswith(tr("CPU")) else "auto"
        self._start_caption_job(
            {
                "engine": engine.id,
                "style": self._style_key(),
                "model": engine.model_value or engine.catalog_name,
                "device": device,
                "image": str(self.image_path),
                "seed": random.randrange(1, 2**31 - 1),
                "profile": self.app.profile_key,
            }
        )

    def _start_caption_job(self, job: dict[str, Any]) -> None:
        jobs_dir = self.app.session_store.root.parent / "caption_jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        job_path = jobs_dir / (
            f"{time.strftime('%Y%m%d-%H%M%S')}-{os.urandom(2).hex()}.json"
        )
        try:
            job_path.write_text(
                json.dumps(job, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            messagebox.showerror(tr("Captioning"), str(exc))
            return
        self.cancelled = False
        self._tag_warning = False
        self.busy = True
        self._result = ""
        self.result_text.delete("1.0", "end")
        self.count_label.config(text="")
        self.analyse_btn.config(text=tr("Analyse…"))
        self.status_label.config(text=tr("Analyse de l'image…"), fg=YELLOW)
        self._update_controls()
        self.app._start_caption_bridge(job_path, tr("Captioning en cours…"))
        if not self.app.running:
            self.busy = False
            self.analyse_btn.config(text=tr("Analyser l'image"))
            self._update_controls()

    # ------------------------------------------------------------------
    # Result actions
    # ------------------------------------------------------------------

    def _show_result(self, text: str) -> None:
        text = str(text or "").strip()
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self._result = text
        self._sync_result()

    def on_caption_result(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            data = {"text": payload}
        text = str(data.get("text") or "").strip()
        self._show_result(text)
        self._tag_warning = data.get("tags_ok") is False
        seconds = data.get("elapsed")
        if self._tag_warning:
            self.status_label.config(
                text=tr(
                    "Le modèle n'a pas produit de tags ; le texte reste une "
                    "description."
                ),
                fg=YELLOW,
            )
        elif seconds:
            self.status_label.config(
                text=tr("Analyse terminée en {seconds} s.", seconds=seconds),
                fg=GREEN,
            )
        else:
            self.status_label.config(text=tr("Analyse terminée."), fg=GREEN)

    def on_bridge_done(
        self, code: int, error: str | None, cancelled: bool
    ) -> None:
        self.busy = False
        self.analyse_btn.config(text=tr("Analyser l'image"))
        if cancelled or self.cancelled:
            self.status_label.config(text=tr("Annulé."), fg=YELLOW)
        elif error or code != 0:
            self.status_label.config(
                text=tr("Erreur — voir le journal."), fg=RED
            )
        elif self._result.strip():
            if self._tag_warning:
                self.status_label.config(
                    text=tr(
                        "Le modèle n'a pas produit de tags ; le texte reste "
                        "une description."
                    ),
                    fg=YELLOW,
                )
            else:
                self.status_label.config(text=tr("Analyse terminée."), fg=GREEN)
        else:
            self.status_label.config(
                text=tr("Le moteur n'a renvoyé aucun texte."), fg=YELLOW
            )
        self._update_controls()

    def _current_result(self) -> str:
        return self.result_text.get("1.0", "end").strip()

    def _sync_result(self) -> None:
        self._result = self._current_result()
        self.count_label.config(
            text=tr("{count} caractères", count=len(self._result))
            if self._result
            else ""
        )
        self._update_controls()

    def _use_result(self, *, replace: bool) -> None:
        text = self._current_result()
        if not text:
            return
        if replace:
            self.app.prompt_text.delete("1.0", "end")
            self.app.prompt_text.insert("1.0", text)
        else:
            current = self.app.prompt_text.get("1.0", "end").strip()
            if current:
                self.app.prompt_text.insert("end", "\n\n" + text)
            else:
                self.app.prompt_text.insert("1.0", text)
        self.app._log(
            tr("Prompt remplacé par le captioning.")
            if replace
            else tr("Captioning ajouté au prompt.")
        )
        self.app.lift()
        self.app.focus_force()

    def _copy(self) -> None:
        text = self._current_result()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_label.config(text=tr("Résultat copié."), fg=GREEN)

    def _clear(self) -> None:
        self.result_text.delete("1.0", "end")
        self._result = ""
        self._tag_warning = False
        self.status_label.config(text=tr("Prêt."), fg=MUTED)
        self._update_controls()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _update_controls(self) -> None:
        enabled = not self.busy and not self._app_busy
        engine = self._engine()
        status = self._engine_status(engine)
        self.engine_combo.config(state="readonly" if enabled else "disabled")
        self.manage_btn.config(state="normal" if enabled else "disabled")
        self.style_combo.config(
            state="readonly" if enabled and engine.styles else "disabled"
        )
        self.device_combo.config(
            state=(
                "readonly"
                if enabled and engine.family != "florence"
                else "disabled"
            )
        )
        self.model_combo.config(
            state=(
                "readonly"
                if enabled
                and engine.family == "florence"
                and self._models_loaded
                else "disabled"
            )
        )
        self.reload_btn.config(
            state=(
                "normal"
                if enabled and engine.family == "florence"
                else "disabled"
            )
        )
        for button in (self.choose_btn, self.paste_btn):
            button.config(state="normal" if enabled else "disabled")
        analyse_enabled = enabled and status.get("ready") and self.image_path is not None
        self.analyse_btn.config(
            state="normal" if analyse_enabled else "disabled",
            bg=ACCENT if analyse_enabled else PANEL_2,
            fg="white" if analyse_enabled else MUTED,
            activebackground=ACCENT_ACTIVE if analyse_enabled else PANEL_2,
        )
        if not self.busy:
            self.analyse_btn.config(text=tr("Analyser l'image"))
        has_result = bool(self._current_result())
        result_enabled = has_result and not self.busy
        self.replace_btn.config(
            state="normal" if result_enabled else "disabled",
            bg=ACCENT if result_enabled else PANEL_2,
            fg="white" if result_enabled else MUTED,
            activebackground=ACCENT_ACTIVE if result_enabled else PANEL_2,
        )
        for button in (self.append_btn, self.copy_btn):
            button.config(state="normal" if result_enabled else "disabled")
        self.clear_btn.config(state="normal" if result_enabled else "disabled")
        self.count_label.config(
            text=tr("{count} caractères", count=len(self._result))
            if self._result
            else ""
        )

    def set_app_busy(self, running: bool) -> None:
        self._app_busy = bool(running)
        self._update_controls()
        if self._manager is not None:
            try:
                if self._manager.winfo_exists():
                    self._manager.set_app_busy(running)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        self._closing = True
        if self._manager is not None:
            try:
                self._manager.destroy()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        if self.busy:
            if not messagebox.askyesno(
                tr("Captioning"),
                tr("Une analyse est en cours. L'annuler et fermer ?"),
            ):
                return
            self.cancelled = True
            self.app._cancel()
        self._closing = True
        self.app._on_caption_closed(self)
        try:
            self.destroy()
        except tk.TclError:
            pass
