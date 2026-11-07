"""X/Y/Z plot tool window for StableCraft.

The window is a pure Tkinter tool.  It validates the axes, writes a JSON job
and asks the main app to run the bridge with ``--xyz-job``.  The bridge does
the ComfyUI work and composes the PNG; this window shows progress and the
result preview.
"""

from __future__ import annotations

import json
import math
import os
import random
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from i18n import current_language, profile_text, tr
from lora_manager import LoraPicker
from lora_store import LoraApi
from platform_support import open_path
from xyz_axes import (
    AXIS_IDS,
    AXIS_TYPES,
    format_value,
    parse_values,
    sr_search,
    type_info,
)

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

# Kept in sync with stablecraft_ui.DENOISE_PROFILES.  Only FLUX.2 Klein EDIT
# starts from the source crop latent.
DENOISE_PROFILES = {"flux2_klein_9b"}

GUIDE_FR = """X = colonnes, Y = lignes. Chaque valeur de Z crée un sous-tableau placé côte à côte sur une page.
Le seed est fixe pour toutes les cellules.

Syntaxe
- Valeurs séparées par des virgules.
- Plages numériques : 5-15(+2) ou 5-15[5].
- Valeur contenant une virgule : "a, b".

Axes
- Sampler : euler, dpmpp_2m
- Scheduler : simple, karras
- Steps : 8, 12, 16, 20
- Denoise : 0.4, 0.6, 0.8, 1.0
  (FLUX.2 Klein 9B en EDIT uniquement)
- LoRA : choisir le LoRA, puis 0.25, 0.5, 0.75, 1.0
- CFG scale : 1.0, 2.0, 3.5
- Prompt S/R : 1re valeur = texte recherché (elle sert aussi de 1er remplacement).
  Ex. cat, dog, wolf — appliqué au prompt et au negative prompt.
- Negative prompt S/R : idem, uniquement le negative prompt.
  Ex. blurry, sharp

Limite : 100 cellules maximum.
Le résultat est un PNG séparé ; aucun calque n'est créé."""

GUIDE_EN = """X = columns, Y = rows. Each Z value creates its own sub-grid, placed side by side on one page.
The seed is fixed for every cell.

Syntax
- Comma-separated values.
- Numeric ranges: 5-15(+2) or 5-15[5].
- Value containing a comma: "a, b".

Axes
- Sampler: euler, dpmpp_2m
- Scheduler: simple, karras
- Steps: 8, 12, 16, 20
- Denoise: 0.4, 0.6, 0.8, 1.0
  (FLUX.2 Klein 9B EDIT only)
- LoRA: choose the LoRA, then 0.25, 0.5, 0.75, 1.0
- CFG scale: 1.0, 2.0, 3.5
- Prompt S/R: 1st value = search text (it is also the 1st replacement).
  E.g. cat, dog, wolf — applied to the prompt and the negative prompt.
- Negative prompt S/R: same, negative prompt only.
  E.g. blurry, sharp

Limit: 100 cells maximum.
The result is a separate PNG; no layer is created."""


class XYZPlotWindow(tk.Toplevel):
    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.app = app
        self.axis_rows: dict[str, dict[str, Any]] = {}
        self._label_to_type: dict[str, str] = {}
        self._closing = False
        self.busy = False
        self.cancelled = False
        self.run_dir: Path | None = None
        self.plot_path: Path | None = None
        self.preview_path: Path | None = None
        self.sub_grid_paths: list[str] = []
        self._preview_photo: tk.PhotoImage | None = None
        self._cells = 0
        self._guide_window: tk.Toplevel | None = None

        self.title(tr("StableCraft — XYZ Plot"))
        self.geometry("760x820+540+40")
        self.minsize(660, 700)
        self.configure(bg=BG)
        # Deliberately not transient: minimizing StableCraft must not minimize
        # the XYZ tool.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        self._load_defaults()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        main = tk.Frame(self, bg=BG, padx=14, pady=12)
        main.pack(fill="both", expand=True)

        header = tk.Frame(main, bg=BG)
        header.pack(fill="x")
        tk.Label(
            header,
            text="XYZ Plot",
            bg=BG,
            fg=FG,
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")
        tk.Button(
            header,
            text=tr("Guide"),
            command=self._show_guide,
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
        ).pack(side="right")
        self.summary_label = tk.Label(
            main,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=700,
            font=("Segoe UI", 8),
        )
        self.summary_label.pack(fill="x", pady=(2, 6))

        seed_row = tk.Frame(main, bg=BG)
        seed_row.pack(fill="x", pady=(2, 6))
        tk.Label(
            seed_row, text=tr("Seed XYZ"), bg=BG, fg=MUTED, font=("Segoe UI", 9)
        ).pack(side="left")
        self.seed_var = tk.StringVar(
            value=str(random.randrange(0, 2**31 - 1))
        )
        self.seed_entry = tk.Entry(
            seed_row,
            textvariable=self.seed_var,
            width=14,
            bg=PANEL_2,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self.seed_entry.pack(side="left", padx=(6, 4))
        tk.Button(
            seed_row,
            text=tr("Aléatoire"),
            command=self._random_seed,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            font=("Segoe UI", 8),
            cursor="hand2",
        ).pack(side="left")
        tk.Label(
            seed_row,
            text=tr("Même seed fixe pour toutes les cellules."),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(10, 0))

        axes_frame = tk.Frame(main, bg=BG)
        axes_frame.pack(fill="x", pady=(4, 0))
        axes_frame.columnconfigure(3, weight=1)
        self._type_options = [
            item
            for item in AXIS_TYPES
            if item["id"] != "denoise" or self._denoise_supported()
        ]
        self._type_labels = [tr(item["label"]) for item in self._type_options]
        self._label_to_type = {
            tr(item["label"]): item["id"] for item in self._type_options
        }

        for row_index, axis_id in enumerate(AXIS_IDS):
            row = row_index * 2
            tk.Label(
                axes_frame,
                text=axis_id.upper(),
                bg=BG,
                fg=FG,
                font=("Segoe UI", 10, "bold"),
            ).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=(4, 0))
            type_var = tk.StringVar(value=tr("Aucun"))
            type_combo = ttk.Combobox(
                axes_frame,
                textvariable=type_var,
                values=self._type_labels,
                state="readonly",
                width=22,
            )
            type_combo.grid(row=row, column=1, sticky="ew", padx=(0, 6), pady=(4, 0))
            lora_var = tk.StringVar()
            lora_btn = tk.Button(
                axes_frame,
                text=tr("Choisir un LoRA…"),
                command=lambda a=axis_id: self._choose_lora(a),
                bg=PANEL_2,
                fg=FG,
                activebackground=BORDER,
                activeforeground=FG,
                relief="flat",
                bd=0,
                padx=6,
                pady=2,
                width=24,
                anchor="w",
                font=("Segoe UI", 8),
                cursor="hand2",
            )
            lora_btn.grid(
                row=row, column=2, sticky="ew", padx=(0, 6), pady=(4, 0)
            )
            lora_btn.grid_remove()
            values_frame = tk.Frame(axes_frame, bg=PANEL_2)
            values_frame.grid(row=row, column=3, sticky="ew", pady=(4, 0))
            values_var = tk.StringVar()
            values_entry = tk.Entry(
                values_frame,
                textvariable=values_var,
                bg=PANEL_2,
                fg=FG,
                insertbackground=FG,
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER,
                highlightcolor=ACCENT,
            )
            values_entry.pack(fill="both", expand=True)
            placeholder = tk.Label(
                values_frame,
                text="",
                bg=PANEL_2,
                fg=MUTED,
                anchor="w",
                font=("Segoe UI", 8, "italic"),
            )
            placeholder.place(x=5, rely=0.5, anchor="w")
            placeholder.bind(
                "<Button-1>",
                lambda _event, entry=values_entry: entry.focus_set(),
            )
            fill_btn = tk.Button(
                axes_frame,
                text="…",
                command=lambda a=axis_id: self._fill_values(a),
                bg=PANEL_2,
                fg=FG,
                activebackground=BORDER,
                activeforeground=FG,
                relief="flat",
                bd=0,
                padx=7,
                pady=2,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
                state="disabled",
            )
            fill_btn.grid(row=row, column=4, padx=(4, 0), pady=(4, 0))
            hint = tk.Label(
                axes_frame,
                text="",
                bg=BG,
                fg=MUTED,
                anchor="w",
                justify="left",
                wraplength=650,
                font=("Segoe UI", 8),
            )
            hint.grid(row=row + 1, column=1, columnspan=4, sticky="w", pady=(0, 2))
            self.axis_rows[axis_id] = {
                "type_var": type_var,
                "type_combo": type_combo,
                "lora_var": lora_var,
                "lora_btn": lora_btn,
                "values_var": values_var,
                "values_entry": values_entry,
                "placeholder": placeholder,
                "fill_btn": fill_btn,
                "hint": hint,
            }
            type_combo.bind(
                "<<ComboboxSelected>>",
                lambda _event, a=axis_id: self._on_type_change(
                    a, clear_values=True
                ),
            )
            values_entry.bind(
                "<FocusIn>",
                lambda _event, a=axis_id: self._placeholder_update(a),
            )
            values_entry.bind(
                "<FocusOut>",
                lambda _event, a=axis_id: self._placeholder_update(a),
            )
            values_var.trace_add(
                "write", lambda *_args, a=axis_id: self._on_values_changed(a)
            )

        self.count_label = tk.Label(
            main,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        )
        self.count_label.pack(fill="x", pady=(8, 0))

        actions = tk.Frame(main, bg=BG)
        actions.pack(fill="x", pady=(6, 0))
        self.launch_btn = tk.Button(
            actions,
            text=tr("Lancer"),
            command=self._launch,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_ACTIVE,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        self.launch_btn.pack(side="left")
        self.cancel_btn = tk.Button(
            actions,
            text=tr("Annuler"),
            command=self._cancel,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=10,
            pady=7,
            font=("Segoe UI", 9),
            cursor="hand2",
            state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=(8, 0))
        tk.Button(
            actions,
            text=tr("Fermer"),
            command=self._on_close,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=10,
            pady=7,
            font=("Segoe UI", 9),
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(main, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(8, 0))
        self.progress_label = tk.Label(
            main,
            text=tr("Prêt."),
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9),
        )
        self.progress_label.pack(fill="x", pady=(2, 0))
        self.status_label = tk.Label(
            main,
            text="",
            bg=BG,
            fg=YELLOW,
            anchor="w",
            font=("Segoe UI", 8),
        )
        self.status_label.pack(fill="x")

        result = tk.Frame(main, bg=BG)
        result.pack(fill="both", expand=True, pady=(8, 0))
        self.preview_canvas = tk.Canvas(
            result,
            height=300,
            bg="#111114",
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.preview_canvas.pack(fill="both", expand=True)
        buttons = tk.Frame(result, bg=BG)
        buttons.pack(fill="x", pady=(4, 0))
        self.folder_btn = self._small_button(
            buttons, tr("Ouvrir le dossier"), self._open_folder, state="disabled"
        )
        self.folder_btn.pack(side="left")
        self.image_btn = self._small_button(
            buttons, tr("Ouvrir l'image"), self._open_image, state="disabled"
        )
        self.image_btn.pack(side="left", padx=(6, 0))
        self.reset_btn = self._small_button(
            buttons, tr("Nouveau plot"), self._reset_result
        )
        self.reset_btn.pack(side="left", padx=(6, 0))
        self._clear_preview(tr("Le résultat apparaîtra ici."))

    def _small_button(
        self,
        parent: tk.Misc,
        text: str,
        command: Any,
        *,
        state: str = "normal",
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            font=("Segoe UI", 8),
            cursor="hand2",
            state=state,
        )

    # ------------------------------------------------------------------
    # Defaults / helpers
    # ------------------------------------------------------------------

    def _denoise_supported(self) -> bool:
        return (
            self.app._mode() == "edit"
            and self.app.profile_key in DENOISE_PROFILES
        )

    def _load_defaults(self) -> None:
        profile = self.app.manifest["profiles"].get(self.app.profile_key, {})
        profile_label = (
            profile_text(profile, "label") or self.app.profile_key
        )
        self.summary_label.config(
            text=tr(
                "{profile} · {mode} · {selection}\n"
                "Prompt et réglages repris de la fenêtre principale.",
                profile=profile_label,
                mode=self.app._mode().upper(),
                selection=(
                    tr("sélection actuelle")
                    if self.app.has_selection
                    else tr("session sélectionnée")
                ),
            )
        )
        try:
            steps = int(self.app.steps_var.get())
        except (TypeError, ValueError):
            steps = 16
        values_list = sorted(
            {
                max(1, min(100, value))
                for value in (steps - 4, steps, steps + 4, steps + 8)
            }
        )
        values = ", ".join(str(value) for value in values_list)
        self._set_axis("x", "steps", values)
        self._set_axis("y", "none", "")
        self._set_axis("z", "none", "")
        self._update_count()

    def _set_axis(self, axis_id: str, type_id: str, values: str) -> None:
        row = self.axis_rows.get(axis_id)
        if row is None:
            return
        row["type_var"].set(tr(type_info(type_id)["label"]))
        row["values_var"].set(values)
        self._on_type_change(axis_id, clear_values=False)

    def _random_seed(self) -> None:
        self.seed_var.set(str(random.randrange(0, 2**31 - 1)))

    def _axis_type(self, axis_id: str) -> str:
        row = self.axis_rows.get(axis_id)
        if row is None:
            return "none"
        return self._label_to_type.get(row["type_var"].get(), "none")

    def _on_type_change(
        self, axis_id: str, *, clear_values: bool = False
    ) -> None:
        row = self.axis_rows.get(axis_id)
        if row is None:
            return
        if clear_values:
            # Switching category must never leave values from the previous
            # category in the field.
            row["values_var"].set("")
        type_id = self._axis_type(axis_id)
        info = type_info(type_id)
        is_lora = type_id == "lora"
        if is_lora:
            row["lora_btn"].grid()
            self._set_lora_button(axis_id, row["lora_var"].get())
        else:
            row["lora_btn"].grid_remove()
        fillable = type_id in {"sampler", "scheduler", "lora"}
        row["fill_btn"].config(state="normal" if fillable else "disabled")
        row["values_entry"].config(
            state="disabled" if info["kind"] == "none" else "normal"
        )
        hints = {
            "none": tr("Axe désactivé."),
            "sampler": tr("Ex. euler, dpmpp_2m"),
            "scheduler": tr("Ex. simple, karras"),
            "steps": tr("Ex. 8, 12, 16, 20 — plages 5-15(+2) ou 5-15[5]"),
            "denoise": tr("Ex. 0.4, 0.6, 0.8, 1.0"),
            "lora": tr("Forces : 0.25, 0.5, 0.75, 1.0"),
            "cfg": tr("Ex. 1.0, 2.0, 3.5"),
            "prompt_sr": tr(
                "1re valeur = texte recherché (aussi 1er remplacement). "
                "Ex. chat, chien, loup"
            ),
            "negative_sr": tr(
                "1re valeur = texte recherché, dans le negative prompt. "
                "Ex. flou, net"
            ),
        }
        hint = hints.get(type_id, "")
        if type_id == "lora" and not row["lora_var"].get():
            hint = tr("Choisis un LoRA avec le bouton, puis les forces.")
        row["hint"].config(text=hint, fg=MUTED)
        self._placeholder_update(axis_id)
        self._update_count()

    def _on_values_changed(self, axis_id: str) -> None:
        self._placeholder_update(axis_id)
        self._update_count()

    def _placeholder_text(self, type_id: str) -> str:
        examples = {
            "sampler": "euler, dpmpp_2m",
            "scheduler": "simple, karras",
            "steps": "8, 12, 16, 20",
            "denoise": "0.4, 0.6, 0.8, 1.0",
            "lora": "0.25, 0.5, 0.75, 1.0",
            "cfg": "1.0, 2.0, 3.5",
        }
        if type_id == "prompt_sr":
            return "chat, chien, loup" if current_language() == "fr" else "cat, dog, wolf"
        if type_id == "negative_sr":
            return "flou, net" if current_language() == "fr" else "blurry, sharp"
        return examples.get(type_id, "")

    def _placeholder_update(self, axis_id: str) -> None:
        row = self.axis_rows.get(axis_id)
        if row is None:
            return
        type_id = self._axis_type(axis_id)
        text = self._placeholder_text(type_id)
        focused = False
        try:
            focused = self.focus_get() is row["values_entry"]
        except tk.TclError:
            pass
        if (
            not text
            or focused
            or row["values_var"].get().strip()
            or type_id == "none"
        ):
            row["placeholder"].place_forget()
            return
        row["placeholder"].config(text=text)
        row["placeholder"].place(x=5, rely=0.5, anchor="w")

    def _set_lora_button(self, axis_id: str, name: str) -> None:
        row = self.axis_rows.get(axis_id)
        if row is None:
            return
        text = " ".join(str(name or "").split())
        if len(text) > 24:
            text = text[:23].rstrip() + "…"
        row["lora_btn"].config(text=text or tr("Choisir un LoRA…"))

    def _choose_lora(self, axis_id: str) -> None:
        if self.busy or getattr(self, "_lora_picker", None) is not None:
            return
        row = self.axis_rows.get(axis_id)
        if row is None:
            return
        used: set[str] = set()
        for other_id, other_row in self.axis_rows.items():
            if other_id == axis_id or self._axis_type(other_id) != "lora":
                continue
            name = str(other_row["lora_var"].get() or "").strip()
            if name:
                used.add(name.replace("\\", "/").casefold())
        try:
            api = LoraApi(str(self.app.cfg["comfyui"]["endpoint"]))
            picker = LoraPicker(
                self,
                api,
                self.app.profile_key,
                current=str(row["lora_var"].get() or ""),
                used=used,
                app=self.app,
            )
            self._lora_picker = picker
            self.wait_window(picker)
            self._lora_picker = None
        except Exception as exc:  # noqa: BLE001
            self._lora_picker = None
            messagebox.showerror(tr("LoRA"), str(exc))
            return
        result = picker.result
        if not result:
            return
        name = str(result.get("name") or "").strip()
        if not name:
            return
        row["lora_var"].set(name)
        self._on_type_change(axis_id, clear_values=False)

    def _fill_values(self, axis_id: str) -> None:
        row = self.axis_rows.get(axis_id)
        if row is None:
            return
        type_id = self._axis_type(axis_id)
        if type_id == "sampler":
            current = str(self.app.sampler_var.get() or "")
            choices = [str(value) for value in self.app._sampler_choices]
            values = [current] + [value for value in choices if value != current][:5]
        elif type_id == "scheduler":
            current = str(self.app.scheduler_var.get() or "")
            choices = [str(value) for value in self.app._scheduler_choices]
            values = [current] + [value for value in choices if value != current][:5]
        elif type_id == "lora":
            values = ["0.25", "0.5", "0.75", "1.0"]
        else:
            return
        row["values_var"].set(", ".join(value for value in values if value))
        self._update_count()

    def _collect_axes(self) -> tuple[list[dict[str, Any]], int]:
        axes: list[dict[str, Any]] = []
        total = 1
        enabled = 0
        for axis_id in AXIS_IDS:
            row = self.axis_rows[axis_id]
            type_id = self._axis_type(axis_id)
            info = type_info(type_id)
            lora = str(row["lora_var"].get() or "").strip()
            if info["kind"] == "none":
                axes.append(
                    {"axis": axis_id, "type": "none", "values": [], "lora": ""}
                )
                continue
            if type_id == "lora" and not lora:
                raise ValueError(
                    tr("Axe {axis} : choisis un LoRA.", axis=axis_id.upper())
                )
            raw = row["values_var"].get().strip()
            values = parse_values(raw, info["kind"])
            if not values:
                raise ValueError(
                    tr("Axe {axis} : aucune valeur.", axis=axis_id.upper())
                )
            if type_id == "steps":
                if any(value < 1 or value > 100 for value in values):
                    raise ValueError(
                        tr(
                            "Axe {axis} : Steps doit rester entre 1 et 100.",
                            axis=axis_id.upper(),
                        )
                    )
            elif type_id == "denoise":
                if not self._denoise_supported():
                    raise ValueError(
                        tr(
                            "L'axe Denoise n'est disponible qu'en EDIT avec "
                            "FLUX.2 Klein 9B."
                        )
                    )
                if any(value < 0 or value > 1 for value in values):
                    raise ValueError(
                        tr(
                            "Axe {axis} : Denoise doit rester entre 0 et 1.",
                            axis=axis_id.upper(),
                        )
                    )
            elif type_id == "cfg":
                if any(value < 0 or value > 20 for value in values):
                    raise ValueError(
                        tr(
                            "Axe {axis} : CFG doit rester entre 0 et 20.",
                            axis=axis_id.upper(),
                        )
                    )
            elif type_id == "lora":
                if not lora:
                    raise ValueError(
                        tr("Axe {axis} : choisis un LoRA.", axis=axis_id.upper())
                    )
                if any(value < 0 or value > 1 for value in values):
                    raise ValueError(
                        tr(
                            "Axe {axis} : force LoRA entre 0 et 1.",
                            axis=axis_id.upper(),
                        )
                    )
            elif type_id == "sampler":
                available = set(str(value) for value in self.app._sampler_choices)
                for value in values:
                    if str(value) not in available:
                        raise ValueError(
                            tr(
                                "Axe {axis} : sampler inconnu {value}.",
                                axis=axis_id.upper(),
                                value=value,
                            )
                        )
            elif type_id == "scheduler":
                available = set(
                    str(value) for value in self.app._scheduler_choices
                )
                for value in values:
                    if str(value) not in available:
                        raise ValueError(
                            tr(
                                "Axe {axis} : scheduler inconnu {value}.",
                                axis=axis_id.upper(),
                                value=value,
                            )
                        )
            elif type_id in {"prompt_sr", "negative_sr"}:
                search = sr_search(values)
                if not search:
                    raise ValueError(
                        tr(
                            "Axe {axis} : texte recherché vide.",
                            axis=axis_id.upper(),
                        )
                    )
                negative = (
                    self.app.neg_text.get("1.0", "end").strip()
                    if self.app.neg_var.get()
                    else ""
                )
                prompt = self.app.prompt_text.get("1.0", "end").strip()
                if type_id == "negative_sr":
                    if search not in negative:
                        raise ValueError(
                            tr(
                                "Axe {axis} : « {search} » absent du negative prompt.",
                                axis=axis_id.upper(),
                                search=search,
                            )
                        )
                elif search not in prompt and search not in negative:
                    raise ValueError(
                        tr(
                            "Axe {axis} : « {search} » absent du prompt et du "
                            "negative prompt.",
                            axis=axis_id.upper(),
                            search=search,
                        )
                    )
            axes.append(
                {
                    "axis": axis_id,
                    "type": type_id,
                    "values": values,
                    "lora": lora,
                }
            )
            enabled += 1
            total *= max(1, len(values))
        if enabled == 0:
            raise ValueError(tr("Choisis au moins un axe."))
        return axes, total

    def _update_count(self) -> None:
        try:
            _axes, total = self._collect_axes()
        except ValueError as exc:
            self.count_label.config(text=tr("— {error}", error=str(exc)), fg=RED)
            return
        text = tr("{count} image(s) à générer", count=total)
        if total > 16:
            text += tr(" — attention, cela peut être long.")
        self.count_label.config(text=text, fg=YELLOW if total > 16 else MUTED)

    # ------------------------------------------------------------------
    # Launch / cancel
    # ------------------------------------------------------------------

    def _launch(self) -> None:
        if self.busy or self.app.running:
            messagebox.showinfo(
                tr("XYZ Plot"), tr("Une génération est déjà en cours.")
            )
            return
        if not self.app.models_ok:
            messagebox.showwarning(
                tr("XYZ Plot"), tr("Installe les modèles manquants avant de lancer.")
            )
            return
        try:
            axes, total = self._collect_axes()
        except ValueError as exc:
            messagebox.showwarning(tr("XYZ Plot"), str(exc))
            return
        if total > 100:
            messagebox.showwarning(
                tr("XYZ Plot"),
                tr("Trop d'images : maximum 100 cellules pour un plot."),
            )
            return
        try:
            seed = int(self.seed_var.get().strip())
        except (TypeError, ValueError):
            seed = -1
        if seed < 0:
            messagebox.showwarning(
                tr("XYZ Plot"),
                tr("Le seed du XYZ plot doit être un entier positif fixe."),
            )
            return
        try:
            steps = int(self.app.steps_var.get())
            cfg = float(self.app.cfg_var.get().replace(",", "."))
            denoise = float(self.app.denoise_var.get().replace(",", "."))
            padding = int(self.app.padding_var.get())
            feather = int(self.app.feather_var.get())
        except (TypeError, ValueError):
            messagebox.showwarning(
                tr("XYZ Plot"),
                tr("Vérifie les réglages dans la fenêtre principale."),
            )
            return
        if not self._denoise_supported():
            denoise = 1.0
        prompt = self.app.prompt_text.get("1.0", "end").strip()
        negative = (
            self.app.neg_text.get("1.0", "end").strip()
            if self.app.neg_var.get()
            else ""
        )
        reference = self.app._reference_active_path()
        session_id = self.app.session_id if self.app._reusable_session() else None
        job = {
            "schema": 1,
            "profile": self.app.profile_key,
            "mode": self.app._mode(),
            "prompt": prompt,
            "negative": negative,
            "padding": padding,
            "feather": feather,
            "settings": {
                "steps": steps,
                "cfg": cfg,
                "sampler": self.app.sampler_var.get(),
                "scheduler": self.app.scheduler_var.get(),
                "denoise": denoise,
            },
            "loras": [
                {
                    "name": str(item.get("name") or ""),
                    "strength": float(item.get("strength", 1.0)),
                }
                for item in self.app._active_loras()
                if item.get("name")
            ],
            "reference": str(reference) if reference else None,
            "reference_name": self.app.reference_name,
            "session": session_id,
            "seed": seed,
            "axes": axes,
            "options": {"cell_max": 512, "preview_max": 1600, "dark": True},
        }
        jobs_dir = self.app.session_store.root.parent / "xyz_jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        job_path = jobs_dir / (
            f"{time.strftime('%Y%m%d-%H%M%S')}-{os.urandom(2).hex()}.json"
        )
        try:
            job_path.write_text(
                json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            messagebox.showerror(tr("XYZ Plot"), str(exc))
            return

        self.busy = True
        self.cancelled = False
        self.run_dir = None
        self.plot_path = None
        self.preview_path = None
        self.sub_grid_paths = []
        self._cells = total
        self.launch_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.folder_btn.config(state="disabled")
        self.image_btn.config(state="disabled")
        self.progress.config(mode="determinate")
        self.progress["value"] = 0
        self.progress_label.config(text=tr("Préparation…"), fg=YELLOW)
        self.status_label.config(text=tr("XYZ Plot en cours…"), fg=YELLOW)
        self._clear_preview(tr("Génération en cours…"))
        self.app._start_xyz_bridge(job_path, tr("XYZ Plot en cours…"))
        if not self.app.running:
            self.busy = False
            self.launch_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")

    def _cancel(self) -> None:
        if not self.busy:
            return
        self.cancelled = True
        self.cancel_btn.config(state="disabled")
        self.progress_label.config(text=tr("Annulation…"), fg=YELLOW)
        self.app._cancel()

    # ------------------------------------------------------------------
    # Bridge events
    # ------------------------------------------------------------------

    def handle_progress(self, data: dict[str, Any]) -> None:
        if data.get("unavailable"):
            self.progress["value"] = 0
            self.progress_label.config(
                text=tr("Progression indisponible…"), fg=YELLOW
            )
            return
        try:
            percent = int(data.get("percent", 0) or 0)
            index = int(data.get("index") or 0)
            count = int(data.get("count") or 1)
        except (TypeError, ValueError):
            return
        self.progress["value"] = max(0, min(100, percent))
        stage = tr(str(data.get("stage") or ""))
        label = f"{stage} : {percent}%" if stage else f"{percent}%"
        if count > 1:
            label = (
                tr("Cellule {index}/{count}", index=index, count=count)
                + " · "
                + label
            )
        self.progress_label.config(text=label, fg=MUTED)

    def handle_event(self, kind: str, payload: str) -> None:
        if kind == "xyz_start" and payload:
            self.run_dir = Path(payload)
            self.folder_btn.config(state="normal")
        elif kind == "xyz_result" and payload:
            self.plot_path = Path(payload)
            self.image_btn.config(state="normal")
            if self.preview_path is None:
                self._show_preview(self.plot_path)
        elif kind == "xyz_preview" and payload:
            self.preview_path = Path(payload)
            self._show_preview(self.preview_path)
        elif kind == "xyz_dir" and payload:
            self.run_dir = Path(payload)
            self.folder_btn.config(state="normal")
        elif kind == "xyz_subgrid" and payload:
            self.sub_grid_paths.append(payload)
        elif kind == "xyz_done" and payload:
            try:
                self._cells = int(payload)
            except ValueError:
                pass

    def on_bridge_done(self, code: int, error: str | None) -> None:
        self.busy = False
        self.launch_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        if self.cancelled:
            self.progress_label.config(text=tr("Annulé."), fg=YELLOW)
            self.status_label.config(
                text=tr("Annulé — les cellules déjà générées sont conservées."),
                fg=YELLOW,
            )
        elif error:
            self.progress_label.config(text=tr("Erreur."), fg=RED)
            self.status_label.config(
                text=tr("Erreur — voir le journal."), fg=RED
            )
        elif code == 0:
            self.progress["value"] = 100
            self.progress_label.config(text=tr("Terminé."), fg=GREEN)
            self.status_label.config(
                text=tr("{count} cellule(s) générée(s).", count=self._cells),
                fg=GREEN,
            )
            if self.preview_path is not None:
                self._show_preview(self.preview_path)
            elif self.plot_path is not None:
                self._show_preview(self.plot_path)
        else:
            self.progress_label.config(text=tr("Erreur."), fg=RED)
            self.status_label.config(
                text=tr("Erreur — voir le journal."), fg=RED
            )
        if self.run_dir is not None and self.run_dir.exists():
            self.folder_btn.config(state="normal")
        if self.plot_path is not None and self.plot_path.exists():
            self.image_btn.config(state="normal")

    # ------------------------------------------------------------------
    # Preview / result
    # ------------------------------------------------------------------

    def _clear_preview(self, text: str) -> None:
        self.preview_canvas.delete("all")
        width = max(1, self.preview_canvas.winfo_width())
        height = max(1, self.preview_canvas.winfo_height())
        if width <= 1:
            width, height = 680, 300
        self.preview_canvas.create_text(
            width // 2,
            height // 2,
            text=text,
            fill=MUTED,
            font=("Segoe UI", 9),
            justify="center",
        )
        self._preview_photo = None

    def _show_preview(self, path: Path) -> None:
        if not path.exists():
            self._clear_preview(tr("Aucun aperçu."))
            return
        try:
            image = tk.PhotoImage(file=str(path))
        except Exception as exc:  # noqa: BLE001
            self._clear_preview(
                tr("Aperçu indisponible : {error}", error=str(exc)[:160])
            )
            return
        width = max(1, self.preview_canvas.winfo_width())
        height = max(1, self.preview_canvas.winfo_height())
        if width <= 1:
            width, height = 680, 300
        factor = max(
            1,
            math.ceil(
                max(image.width() / max(1, width - 8), image.height() / max(1, height - 8))
            ),
        )
        if factor > 1:
            image = image.subsample(factor, factor)
        self._preview_photo = image
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(
            width // 2, height // 2, image=image, anchor="center"
        )

    def _open_folder(self) -> None:
        if self.run_dir is None:
            return
        try:
            open_path(self.run_dir)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(tr("XYZ Plot"), str(exc))

    def _open_image(self) -> None:
        if self.plot_path is None:
            return
        try:
            open_path(self.plot_path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(tr("XYZ Plot"), str(exc))

    def _reset_result(self) -> None:
        if self.busy:
            return
        self.plot_path = None
        self.preview_path = None
        self.sub_grid_paths = []
        self.image_btn.config(state="disabled")
        self.progress["value"] = 0
        self.progress_label.config(text=tr("Prêt."), fg=MUTED)
        self.status_label.config(text="", fg=YELLOW)
        self._clear_preview(tr("Le résultat apparaîtra ici."))
        self._update_count()

    # ------------------------------------------------------------------
    # Guide
    # ------------------------------------------------------------------

    def _show_guide(self) -> None:
        if self._guide_window is not None:
            try:
                if self._guide_window.winfo_exists():
                    self._guide_window.deiconify()
                    self._guide_window.lift()
                    self._guide_window.focus_force()
                    return
            except tk.TclError:
                pass
        guide = tk.Toplevel(self.app)
        guide.title(tr("Guide XYZ Plot"))
        guide.geometry("640x560+620+80")
        guide.minsize(480, 360)
        guide.configure(bg=BG)
        guide.protocol("WM_DELETE_WINDOW", lambda: self._close_guide(guide))

        body = tk.Frame(guide, bg=BG, padx=12, pady=12)
        body.pack(fill="both", expand=True)
        widget = tk.Text(
            body,
            wrap="word",
            bg="#141418",
            fg=FG,
            insertbackground=FG,
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
        )
        scroll = ttk.Scrollbar(body, orient="vertical", command=widget.yview)
        widget.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        widget.pack(side="left", fill="both", expand=True)
        widget.insert(
            "1.0", GUIDE_FR if current_language() == "fr" else GUIDE_EN
        )
        widget.configure(state="disabled")

        footer = tk.Frame(guide, bg=BG)
        footer.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(
            footer,
            text=tr("Fermer"),
            command=lambda: self._close_guide(guide),
            bg=PANEL_2,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            font=("Segoe UI", 9),
            cursor="hand2",
        ).pack(side="right")
        self._guide_window = guide

    def _close_guide(self, guide: tk.Toplevel) -> None:
        if self._guide_window is guide:
            self._guide_window = None
        try:
            guide.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        if self.busy:
            if not messagebox.askyesno(
                tr("XYZ Plot"),
                tr("Un XYZ Plot est en cours. L'annuler et fermer ?"),
            ):
                return
            self.cancelled = True
            self.app._cancel()
        self._closing = True
        self.app._on_xyz_closed(self)
        self.destroy()
