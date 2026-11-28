"""Tools launcher for StableCraft.

A single window lists the optional tools with a preview, a short description
and an open button.  Keeping the catalogue here makes adding future tools a
one-row change instead of another button in the crowded main panel.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any

from i18n import tr

BG = "#1b1b1f"
PANEL = "#25252b"
PANEL_2 = "#2d2d34"
FG = "#e8e8ea"
MUTED = "#9a9aa3"
ACCENT = "#3b82f6"
ACCENT_ACTIVE = "#2563eb"
BORDER = "#3a3a44"

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "tools"


class ToolsWindow(tk.Toplevel):
    """Catalogue of the optional StableCraft tools."""

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.app = app
        self._photos: list[tk.PhotoImage] = []
        self._open_buttons: list[tk.Button] = []
        self._busy = False

        self.title(tr("StableCraft — Outils"))
        self.geometry("860x520+540+80")
        self.minsize(760, 450)
        self.configure(bg=BG)
        # Deliberately not transient: minimizing StableCraft must not hide it.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        main = tk.Frame(self, bg=BG, padx=18, pady=16)
        main.pack(fill="both", expand=True)

        header = tk.Frame(main, bg=BG)
        header.pack(fill="x")
        tk.Label(
            header,
            text=tr("Outils"),
            bg=BG,
            fg=FG,
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left")
        tk.Label(
            main,
            text=tr(
                "Des outils pour préparer et comparer tes générations, "
                "sans quitter StableCraft."
            ),
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=800,
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(2, 12))

        rows = tk.Frame(main, bg=BG)
        rows.pack(fill="both", expand=True)

        self._add_row(
            rows,
            title=tr("XYZ Plot"),
            meta=tr("Planche X/Y/Z"),
            description=tr(
                "Compare un prompt sur plusieurs axes (sampler, steps, LoRA, "
                "CFG…) et génère une planche X/Y/Z avec les réglages de la "
                "fenêtre principale."
            ),
            image_name="xyz_plot.png",
            command=self._open_xyz,
        )
        self._add_row(
            rows,
            title=tr("Captioning"),
            meta=tr("Image → prompt"),
            description=tr(
                "Transforme n'importe quelle image en prompt adapté au modèle "
                "actif. Florence-2 PromptGen tourne en local, sans toucher au "
                "workflow de génération."
            ),
            image_name="caption.png",
            command=self._open_caption,
        )

        tk.Label(
            main,
            text=tr("D'autres outils pourront s'ajouter ici."),
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 8),
        ).pack(fill="x", pady=(6, 0))

    def _add_row(
        self,
        parent: tk.Misc,
        *,
        title: str,
        meta: str,
        description: str,
        image_name: str,
        command: Any,
    ) -> None:
        row = tk.Frame(parent, bg=PANEL, padx=12, pady=12)
        row.pack(fill="x", pady=(0, 10))

        thumb = tk.Canvas(
            row,
            width=200,
            height=112,
            bg="#111114",
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        thumb.pack(side="left")
        photo = self._load_photo(image_name)
        if photo is not None:
            thumb.create_image(100, 56, image=photo)
            self._photos.append(photo)
        else:
            thumb.create_text(
                100,
                56,
                text=tr("Aperçu"),
                fill=MUTED,
                font=("Segoe UI", 9),
            )

        body = tk.Frame(row, bg=PANEL)
        body.pack(side="left", fill="both", expand=True, padx=(14, 12))
        tk.Label(
            body,
            text=title,
            bg=PANEL,
            fg=FG,
            anchor="w",
            font=("Segoe UI", 13, "bold"),
        ).pack(fill="x")
        tk.Label(
            body,
            text=meta,
            bg=PANEL,
            fg=ACCENT,
            anchor="w",
            font=("Segoe UI", 8, "bold"),
        ).pack(fill="x", pady=(1, 4))
        tk.Label(
            body,
            text=description,
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=430,
            font=("Segoe UI", 9),
        ).pack(fill="x")

        button = tk.Button(
            row,
            text=tr("Ouvrir"),
            command=command,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_ACTIVE,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=16,
            pady=7,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            disabledforeground=MUTED,
        )
        button.pack(side="right", anchor="center")
        self._open_buttons.append(button)

    def _load_photo(self, name: str) -> tk.PhotoImage | None:
        path = ASSETS / name
        try:
            return tk.PhotoImage(file=str(path))
        except tk.TclError:
            return None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_xyz(self) -> None:
        if self._busy:
            return
        self.app._open_xyz()
        if self.app.xyz_window is not None:
            self._close_now()

    def _open_caption(self) -> None:
        if self._busy:
            return
        self.app._open_caption()
        if self.app.caption_window is not None:
            self._close_now()

    def set_app_busy(self, running: bool) -> None:
        self._busy = bool(running)
        state = "disabled" if self._busy else "normal"
        for button in self._open_buttons:
            try:
                button.config(state=state)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _close_now(self) -> None:
        self.app._on_tools_closed(self)
        self.destroy()

    def _on_close(self) -> None:
        self._close_now()
