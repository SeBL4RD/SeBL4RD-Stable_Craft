"""Caption engine manager: install nodes, vision backend and GGUF models on demand."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from caption_engines import ENGINES, ENGINE_BY_ID, CaptionEngine
from caption_install import (
    engine_status,
    install_engine,
    restart_comfyui,
)
from i18n import tr
from models_tools import DownloadCancelled, DownloadToken, human_size

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


class CaptionManager(tk.Toplevel):
    """One row per optional caption engine, installed only on request."""

    def __init__(
        self,
        app: Any,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(app)
        self.app = app
        self.cfg = app.cfg
        self.on_changed = on_changed
        self.busy = False
        self._closing = False
        self._cancel: DownloadToken | None = None
        self.queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.rows: dict[str, dict[str, Any]] = {}

        self.title(tr("StableCraft — Moteurs de captioning"))
        self.geometry("820x620+560+70")
        self.minsize(720, 520)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        self._refresh()
        self.after(120, self._poll)

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
            text=tr("Moteurs de captioning"),
            bg=BG,
            fg=FG,
            font=("Segoe UI", 17, "bold"),
        ).pack(side="left")
        tk.Label(
            main,
            text=tr(
                "Les moteurs sont optionnels et installés à la demande. "
                "Rien n'est ajouté par le setup : le node, le backend vision "
                "et les modèles sont téléchargés seulement quand tu cliques."
            ),
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=780,
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(2, 10))

        body = tk.Frame(main, bg=BG)
        body.pack(fill="both", expand=True)

        for engine in ENGINES:
            self._add_row(body, engine)

        footer = tk.Frame(main, bg=BG)
        footer.pack(fill="x", pady=(10, 0))
        self.progress = ttk.Progressbar(footer, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        status_row = tk.Frame(footer, bg=BG)
        status_row.pack(fill="x", pady=(4, 0))
        self.status = tk.Label(
            status_row,
            text=tr("Prêt."),
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=740,
            font=("Segoe UI", 8),
        )
        self.status.pack(side="left", fill="x", expand=True)
        self.cancel_btn = self._button(
            status_row, tr("Annuler"), self._cancel_task, bg=PANEL_2
        )
        self.cancel_btn.pack(side="right")
        self.cancel_btn.config(state="disabled")

        actions = tk.Frame(main, bg=BG)
        actions.pack(fill="x", pady=(6, 0))
        self.restart_btn = self._button(
            actions, tr("Redémarrer ComfyUI"), self._restart, bg=PANEL_2
        )
        self.restart_btn.pack(side="left")
        self._button(actions, tr("Fermer"), self._on_close, bg=PANEL_2).pack(
            side="right"
        )

    def _add_row(self, parent: tk.Misc, engine: CaptionEngine) -> None:
        frame = tk.Frame(parent, bg=PANEL, padx=12, pady=10)
        frame.pack(fill="x", pady=(0, 8))

        head = tk.Frame(frame, bg=PANEL)
        head.pack(fill="x")
        tk.Label(
            head,
            text=tr(engine.label),
            bg=PANEL,
            fg=FG,
            anchor="w",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        size = (
            tr("{size} Go", size=f"{engine.download_size_gb:.1f}")
            if engine.download_size_gb
            else tr("inclus")
        )
        tk.Label(
            head,
            text=size,
            bg=PANEL,
            fg=MUTED,
            anchor="e",
            font=("Segoe UI", 8),
        ).pack(side="right")

        tk.Label(
            frame,
            text=tr(engine.description),
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=560,
            font=("Segoe UI", 8),
        ).pack(fill="x", pady=(2, 4))

        status_row = tk.Frame(frame, bg=PANEL)
        status_row.pack(fill="x")
        status_label = tk.Label(
            status_row,
            text="",
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=560,
            font=("Segoe UI", 8),
        )
        status_label.pack(side="left", fill="x", expand=True)
        install_btn = self._button(
            status_row,
            tr("Installer"),
            lambda key=engine.id: self._install(key),
            primary=True,
            small=True,
        )
        install_btn.pack(side="right")
        self.rows[engine.id] = {
            "frame": frame,
            "status": status_label,
            "button": install_btn,
        }

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        command: Any,
        *,
        primary: bool = False,
        bg: str = PANEL_2,
        small: bool = False,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT if primary else bg,
            fg="white" if primary else FG,
            activebackground=ACCENT_ACTIVE if primary else BORDER,
            activeforeground="white" if primary else FG,
            relief="flat",
            bd=0,
            padx=9,
            pady=3 if small else 5,
            font=("Segoe UI", 8 if small else 9),
            cursor="hand2",
            disabledforeground=MUTED,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        for engine in ENGINES:
            row = self.rows.get(engine.id)
            if row is None:
                continue
            if engine.family == "florence":
                row["status"].config(
                    text=tr("Inclus avec ComfyUI · aucun téléchargement"),
                    fg=GREEN,
                )
                row["button"].config(state="disabled", text=tr("Inclus"))
                continue
            status = engine_status(engine, self.cfg)
            parts: list[str] = []
            parts.append(
                tr("Node : OK")
                if status["loaded"]
                else (
                    tr("Node : installé, redémarrage requis")
                    if status["node"]
                    else tr("Node : manquant")
                )
            )
            parts.append(
                tr("Backend vision : OK")
                if status["vision"]
                else tr("Backend vision : manquant")
            )
            parts.append(
                tr("Modèle : OK") if status["models"] else tr("Modèle : manquant")
            )
            color = GREEN if status["ready"] else YELLOW
            row["status"].config(text=" · ".join(parts), fg=color)
            row["button"].config(
                state=(
                    "disabled"
                    if self.busy or self.app.running
                    else "normal"
                ),
                text=tr("Réinstaller") if status["ready"] else tr("Installer"),
                bg=ACCENT if not status["ready"] else PANEL_2,
                fg="white" if not status["ready"] else FG,
            )
        self.restart_btn.config(
            state="disabled" if self.busy else "normal"
        )

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def _install(self, engine_id: str) -> None:
        if self.busy:
            return
        if self.app.running:
            messagebox.showwarning(
                tr("Moteurs de captioning"),
                tr("Une génération est en cours. Attends la fin avant d'installer."),
                parent=self,
            )
            return
        engine = ENGINE_BY_ID.get(engine_id)
        if engine is None or engine.family == "florence":
            return
        status = engine_status(engine, self.cfg)
        if status["ready"]:
            question = tr(
                "{label} est déjà prêt. Réinstaller le node, le backend et le "
                "modèle ?",
                label=tr(engine.label),
            )
        else:
            lines = [
                tr(
                    "{label} va installer :",
                    label=tr(engine.label),
                )
            ]
            if not status["node"]:
                lines.append(tr("• le node {node}", node=engine.node_folder))
            if not status["vision"]:
                lines.append(
                    tr("• le backend vision llama.cpp (223 Mo, une fois)")
                )
            if not status["models"]:
                lines.append(
                    tr(
                        "• le modèle {size} Go",
                        size=f"{engine.download_size_gb:.1f}",
                    )
                )
            lines.append(
                tr("ComfyUI sera redémarré. Continuer ?")
            )
            question = "\n".join(lines)
        if not messagebox.askyesno(
            tr("Moteurs de captioning"), question, parent=self
        ):
            return

        self._start(
            tr("Installation de {label}…", label=tr(engine.label)),
            lambda progress, cancel, note: install_engine(
                engine,
                self.cfg,
                progress=progress,
                cancel=cancel,
                status=note,
            ),
            indeterminate=False,
        )

    def _restart(self) -> None:
        if self.busy:
            return
        if self.app.running:
            messagebox.showwarning(
                tr("Moteurs de captioning"),
                tr("Une génération est en cours. Attends la fin avant de redémarrer."),
                parent=self,
            )
            return
        if not messagebox.askyesno(
            tr("ComfyUI"),
            tr("Redémarrer ComfyUI ? Une génération en cours sera interrompue."),
            parent=self,
        ):
            return
        self._start(
            tr("Redémarrage de ComfyUI…"),
            lambda progress, cancel, note: restart_comfyui(
                self.cfg, status=note
            ),
            indeterminate=True,
        )

    def _start(
        self,
        label: str,
        function: Callable[[Any, DownloadToken, Callable[[str], None]], str],
        *,
        indeterminate: bool,
    ) -> None:
        self.busy = True
        self._cancel = DownloadToken()
        self.cancel_btn.config(state="normal")
        self.progress.config(mode="indeterminate" if indeterminate else "determinate")
        self.progress["value"] = 0
        if indeterminate:
            self.progress.start(15)
        self.status.config(text=label, fg=YELLOW)
        self._refresh()

        def progress(done: int, total: int) -> None:
            self.queue.put(("progress", done, total))

        def note(message: str) -> None:
            self.queue.put(("note", message))

        def worker() -> None:
            try:
                message = function(progress, self._cancel, note)
            except DownloadCancelled:
                self.queue.put(("cancelled", None))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("error", str(exc)))
            else:
                self.queue.put(("done", message))

        threading.Thread(target=worker, daemon=True).start()

    def _cancel_task(self) -> None:
        if not self.busy or self._cancel is None:
            return
        self._cancel.set()
        self.cancel_btn.config(state="disabled")
        self.status.config(text=tr("Annulation."), fg=YELLOW)

    def _finish(
        self, error: str | None, message: str | None, *, cancelled: bool = False
    ) -> None:
        self.busy = False
        self._cancel = None
        self.cancel_btn.config(state="disabled")
        self.progress.stop()
        if cancelled:
            self.progress.config(mode="determinate", value=0)
        else:
            self.progress.config(mode="determinate", value=0 if error else 100)
        if error:
            self.status.config(
                text=tr("Erreur : {error}", error=str(error)[:500]), fg=RED
            )
            messagebox.showerror(
                tr("Moteurs de captioning"), str(error)[:1500], parent=self
            )
        elif cancelled:
            self.status.config(
                text=message or tr("Installation annulée."), fg=YELLOW
            )
        elif message:
            self.status.config(text=message, fg=GREEN)
        self._refresh()
        if self.on_changed is not None:
            try:
                self.on_changed()
            except Exception:  # noqa: BLE001
                pass

    def _poll(self) -> None:
        if self._closing:
            return
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    done, total = int(item[1]), int(item[2])
                    if total > 0:
                        self.progress.stop()
                        self.progress.config(
                            mode="determinate",
                            maximum=total,
                            value=min(done, total),
                        )
                        self.status.config(
                            text=tr(
                                "{done} / {total}",
                                done=human_size(done),
                                total=human_size(total),
                            ),
                            fg=YELLOW,
                        )
                elif kind == "note":
                    self.status.config(text=str(item[1]), fg=YELLOW)
                elif kind == "error":
                    self._finish(str(item[1]), None)
                elif kind == "cancelled":
                    self._finish(None, tr("Installation annulée."), cancelled=True)
                elif kind == "done":
                    self._finish(None, str(item[1]))
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def set_app_busy(self, running: bool) -> None:
        self._refresh()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        if self.busy:
            if not messagebox.askyesno(
                tr("Moteurs de captioning"),
                tr("Une installation est en cours. L'annuler et fermer ?"),
                parent=self,
            ):
                return
            if self._cancel is not None:
                self._cancel.set()
        self._closing = True
        self.destroy()
