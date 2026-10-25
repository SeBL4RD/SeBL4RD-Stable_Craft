"""Model manager: locate or download missing files, install Krea 2 nodes."""

from __future__ import annotations

import os
import queue
import shutil
import threading
import time
import tkinter as tk
import urllib.parse
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from i18n import profile_text, tr
from models_tools import (
    FOLDER_FOR_KIND,
    ensure_extra_model_paths,
    human_size,
    install_krea_node,
    krea_node_status,
    latest_krea_release,
    set_selected_file,
    start_comfyui,
    stop_comfyui,
    wait_for_comfyui,
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


class ModelManager(tk.Toplevel):
    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.app = app
        self.cfg = app.cfg
        self.manifest = app.manifest
        self.profile_key = app.profile_key
        self.profile = self.manifest["profiles"].get(self.profile_key, {})
        self.queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.busy = False
        self._closing = False
        self.node_status: dict[str, Any] | None = None
        self._needs_restart = False
        self._rows: list[dict[str, Any]] = []

        self.title(
            tr(
                "Modèles — {profile}",
                profile=profile_text(self.profile, "label") or self.profile_key,
            )
        )
        self.geometry("760x620+560+80")
        self.minsize(640, 480)
        self.configure(bg=BG)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        self.after(80, self._poll)
        self.app._check_models()
        self.refresh()
        threading.Thread(target=self._check_node_async, daemon=True).start()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        header = tk.Frame(self, bg=BG, padx=14, pady=10)
        header.pack(fill="x")
        tk.Label(
            header,
            text=profile_text(self.profile, "label") or self.profile_key,
            bg=BG,
            fg=FG,
            font=("Segoe UI", 15, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            header,
            text=profile_text(self.profile, "description"),
            bg=BG,
            fg=MUTED,
            justify="left",
            wraplength=710,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(2, 0))
        warning = profile_text(self.profile, "warning").strip()
        if warning:
            tk.Label(
                header,
                text=f"⚠ {warning}",
                bg=BG,
                fg=YELLOW,
                justify="left",
                wraplength=710,
                anchor="w",
                font=("Segoe UI", 8),
            ).pack(fill="x", pady=(3, 0))
        self.restart_label = tk.Label(
            header,
            text="",
            bg=BG,
            fg=YELLOW,
            anchor="w",
            wraplength=710,
            justify="left",
            font=("Segoe UI", 8),
        )
        self.restart_label.pack(fill="x", pady=(4, 0))

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(self.window_id, width=event.width),
        )

        self.summary = tk.Label(
            self.inner,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=700,
            font=("Segoe UI", 9),
        )
        self.summary.pack(fill="x", pady=(2, 6))

        self.node_frame = tk.Frame(self.inner, bg=PANEL, padx=10, pady=8, highlightthickness=1, highlightbackground=BORDER)
        self.node_frame.pack(fill="x", pady=(0, 8))
        self.node_label = tk.Label(
            self.node_frame,
            text=tr("Nœud Krea 2 : vérification…"),
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=650,
            font=("Segoe UI", 9),
        )
        self.node_label.pack(fill="x")
        node_actions = tk.Frame(self.node_frame, bg=PANEL)
        node_actions.pack(fill="x", pady=(5, 0))
        self.node_button = self._button(
            node_actions, tr("Installer / mettre à jour"), self._install_node, bg=PANEL
        )
        self.node_button.pack(side="left")
        self.node_button.config(state="disabled")
        self.node_link = tk.Label(
            node_actions,
            text="",
            bg=PANEL,
            fg=ACCENT,
            cursor="hand2",
            font=("Segoe UI", 8),
        )
        self.node_link.pack(side="left", padx=(10, 0))
        self.node_link.bind("<Button-1>", self._open_node_release)

        self.rows_frame = tk.Frame(self.inner, bg=BG)
        self.rows_frame.pack(fill="x")

        footer = tk.Frame(self, bg=BG, padx=14, pady=10)
        footer.pack(fill="x", side="bottom")
        self.progress = ttk.Progressbar(footer, mode="determinate")
        self.progress.pack(fill="x")
        self.status = tk.Label(
            footer,
            text=tr("Prêt."),
            bg=BG,
            fg=MUTED,
            anchor="w",
            wraplength=730,
            justify="left",
            font=("Segoe UI", 8),
        )
        self.status.pack(fill="x", pady=(3, 4))
        actions = tk.Frame(footer, bg=BG)
        actions.pack(fill="x")
        self._button(actions, tr("Vérifier"), self._verify).pack(side="left")
        self._button(actions, tr("Dossier des modèles"), self._open_store).pack(
            side="left", padx=(6, 0)
        )
        self.restart_button = self._button(
            actions, tr("Redémarrer ComfyUI"), self._restart_comfyui, bg=PANEL_2
        )
        self.restart_button.pack(side="left", padx=(6, 0))
        self._button(actions, tr("Fermer"), self._on_close, bg=PANEL_2).pack(
            side="right"
        )

    def _button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        bg: str = PANEL_2,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=FG,
            activebackground=BORDER,
            activeforeground=FG,
            relief="flat",
            bd=0,
            padx=9,
            pady=4,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )

    # ------------------------------------------------------------------
    # Rows
    # ------------------------------------------------------------------

    def _verify(self) -> None:
        self.status.config(text=tr("Vérification des modèles…"), fg=YELLOW)
        token = time.time()
        self._verify_token = token
        self.app._check_models()
        self.after(20000, lambda: self._verify_timeout(token))

    def _verify_timeout(self, token: float) -> None:
        if getattr(self, "_verify_token", None) != token or self.app.models_checked:
            return
        message = tr(
            "Toujours en cours. Vérifie que ComfyUI tourne, puis clique Vérifier."
        )
        self.summary.config(text=message, fg=YELLOW)
        self.status.config(text=message, fg=YELLOW)

    def refresh(self) -> None:
        if self._closing:
            return
        self.profile = self.manifest["profiles"].get(self.profile_key, {})
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._rows.clear()

        if not self.app.models_checked:
            self.summary.config(text=tr("Vérification des modèles…"), fg=YELLOW)
        elif self.app.models_error:
            self.summary.config(
                text=tr(
                    "Vérification impossible : {error}. ComfyUI doit être démarré.",
                    error=self.app.models_error,
                ),
                fg=YELLOW,
            )
        elif not self.app.missing_models:
            self.summary.config(
                text=tr("Tous les fichiers requis sont visibles par ComfyUI."),
                fg=GREEN,
            )
        else:
            self.summary.config(
                text=tr(
                    "{count} fichier(s) manquant(s). Tu peux localiser un fichier existant "
                    "ou le télécharger avec ton accord.",
                    count=len(self.app.missing_models),
                ),
                fg=RED,
            )
            for item in self.app.missing_models:
                self._add_missing_row(item)

        self._update_restart_label()
        if hasattr(self, "restart_button"):
            self.restart_button.config(
                text=tr("Redémarrer ComfyUI")
                if self.app.comfy_ok
                else tr("Démarrer ComfyUI")
            )

    def _add_missing_row(self, item: dict[str, Any]) -> None:
        kind = str(item.get("kind", "?"))
        filename = str(item.get("filename", "?"))
        options: list[dict[str, Any]] = list(item.get("options") or [])
        label = str(item.get("label", kind))
        title = label if len(options) > 1 else f"{label} · {filename}"
        frame = tk.Frame(
            self.rows_frame,
            bg=PANEL,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        frame.pack(fill="x", pady=(0, 6))
        top = tk.Frame(frame, bg=PANEL)
        top.pack(fill="x")
        tk.Label(
            top,
            text=title,
            bg=PANEL,
            fg=FG,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", fill="x", expand=True)
        if item.get("note"):
            tk.Label(
                frame,
                text=str(item["note"]),
                bg=PANEL,
                fg=MUTED,
                anchor="w",
                justify="left",
                wraplength=680,
                font=("Segoe UI", 8),
            ).pack(fill="x", pady=(2, 3))

        option_var: tk.StringVar | None = None
        option_by_label: dict[str, dict[str, Any]] = {}
        size_label: tk.Label | None = None
        if options:
            labels: list[str] = []
            for option in options:
                label = str(option.get("label", option.get("filename", "?")))
                base_label = label
                index = 2
                while label in option_by_label:
                    label = f"{base_label} ({index})"
                    index += 1
                option_by_label[label] = option
                labels.append(label)
            option_var = tk.StringVar(value=labels[0])
            chooser = ttk.Combobox(
                frame,
                textvariable=option_var,
                values=labels,
                state="readonly",
                width=18,
            )
            chooser.pack(side="left", anchor="w", pady=(3, 0))

            size_label = tk.Label(
                frame,
                text="",
                bg=PANEL,
                fg=MUTED,
                anchor="w",
                font=("Segoe UI", 8),
            )
            size_label.pack(side="left", padx=(8, 0), pady=(3, 0))

            def update_size(_event: object = None) -> None:
                option = option_by_label.get(option_var.get(), {})
                if size_label is not None:
                    size_label.config(text=human_size(option.get("size")))

            chooser.bind("<<ComboboxSelected>>", update_size)
            update_size()

        actions = tk.Frame(frame, bg=PANEL)
        actions.pack(side="right", padx=(8, 0), pady=(3, 0))
        if kind == "node":
            tk.Label(
                actions,
                text=tr("Voir le nœud Krea 2 ci-dessus ou mettre à jour ComfyUI."),
                bg=PANEL,
                fg=YELLOW,
                font=("Segoe UI", 8),
            ).pack(side="left", padx=(5, 0))
        else:
            self._button(
                actions,
                tr("Localiser"),
                lambda i=item: self._locate(i),
                bg=PANEL_2,
            ).pack(side="left")
            if options:
                self._button(
                    actions,
                    tr("Télécharger"),
                    lambda i=item, v=option_var, m=option_by_label: self._download(i, v, m),
                    bg=ACCENT,
                ).pack(side="left", padx=(5, 0))
            else:
                tk.Label(
                    actions,
                    text=tr("Fichier local uniquement"),
                    bg=PANEL,
                    fg=MUTED,
                    font=("Segoe UI", 8),
                ).pack(side="left", padx=(5, 0))

        self._rows.append(
            {
                "item": item,
                "frame": frame,
                "option_var": option_var,
                "option_by_label": option_by_label,
            }
        )

    # ------------------------------------------------------------------
    # Locate / download
    # ------------------------------------------------------------------

    def _locate(self, item: dict[str, Any]) -> None:
        if self.busy:
            return
        kind = str(item.get("kind", ""))
        patterns = "*.gguf" if kind in {"unet", "lora"} else "*.safetensors *.sft"
        selected = filedialog.askopenfilename(
            parent=self,
            title=tr("Localiser {label}", label=item.get("label", kind)),
            filetypes=[
                (tr("Modèles"), patterns),
                (tr("Tous les fichiers"), "*.*"),
            ],
        )
        if not selected:
            return
        source = Path(selected)
        if not source.is_file():
            messagebox.showerror(tr("Fichier introuvable"), str(source), parent=self)
            return
        visible: list[str] = []
        if self.app.comfy_ok:
            try:
                visible = self.app._visible_model_options(kind, source.name)
            except Exception:  # noqa: BLE001
                visible = []
        if visible:
            set_selected_file(self.app.profile_key, kind, visible[0])
            self.status.config(
                text=tr("{filename} est déjà visible par ComfyUI.", filename=visible[0]),
                fg=GREEN,
            )
            self.app._check_models()
            self.refresh()
            return

        store = self.app._model_store_dir()
        folder = str(item.get("folder") or FOLDER_FOR_KIND.get(kind, "unet"))
        destination = store / folder / source.name
        source_resolved = source.resolve()
        store_resolved = store.resolve()
        try:
            under_store = source_resolved.is_relative_to(store_resolved)
        except AttributeError:  # Python < 3.9
            under_store = str(source_resolved).startswith(str(store_resolved))

        if source_resolved == destination.resolve():
            self._use_local_file(destination, kind)
            return

        if under_store:
            if destination.exists():
                if destination.stat().st_size == source.stat().st_size:
                    remove_duplicate = messagebox.askyesno(
                        tr("Doublon détecté"),
                        tr(
                            "Le fichier est déjà rangé ici :\n{destination}\n\n"
                            "La copie déjà rangée va être utilisée. Supprimer le "
                            "doublon :\n{source} ?",
                            destination=destination,
                            source=source,
                        ),
                        parent=self,
                    )
                    if remove_duplicate:
                        try:
                            source.unlink()
                        except OSError as exc:
                            messagebox.showerror(
                                tr("Suppression impossible"), str(exc), parent=self
                            )
                    self._use_local_file(destination, kind)
                    return
                if not messagebox.askyesno(
                    tr("Remplacer le fichier ?"),
                    tr(
                        "{destination} existe déjà avec une autre taille.\n\n"
                        "Le remplacer par ce fichier (déplacement, pas copie) ?",
                        destination=destination,
                    ),
                    parent=self,
                ):
                    return
            elif not messagebox.askyesno(
                tr("Déplacer le modèle ?"),
                tr(
                    "Ce fichier est déjà dans le dossier des modèles mais pas dans "
                    "le sous-dossier attendu.\n\n"
                    "Le déplacer vers :\n{destination}\n\n"
                    "Aucune copie ne sera créée.",
                    destination=destination,
                ),
                parent=self,
            ):
                return
            self._run_task(
                tr("Déplacement de {filename}…", filename=source.name),
                lambda progress: self._move_and_select(
                    source, destination, kind, progress
                ),
            )
            return

        if not messagebox.askyesno(
            tr("Copier le modèle ?"),
            tr(
                "Ce fichier est hors du dossier des modèles.\n\n"
                "Le copier dans :\n{destination}\n\n"
                "Puis ajouter le dossier aux chemins ComfyUI ?",
                destination=destination,
            ),
            parent=self,
        ):
            return
        self._run_task(
            tr("Copie de {filename}…", filename=source.name),
            lambda progress: self._copy_and_select(source, destination, kind, progress),
        )

    def _use_local_file(self, path: Path, kind: str) -> None:
        changed, error = ensure_extra_model_paths(self.cfg)
        if error:
            messagebox.showerror(tr("Chemins ComfyUI"), error, parent=self)
            return
        set_selected_file(self.app.profile_key, kind, path.name)
        self._needs_restart = True
        self.status.config(
            text=tr(
                "{filename} est dans le dossier des modèles. Redémarre ComfyUI "
                "pour le voir.",
                filename=path.name,
            ),
            fg=GREEN,
        )
        self._update_restart_label()
        self.after(200, self._maybe_restart_after_change)

    def _move_and_select(
        self,
        source: Path,
        destination: Path,
        kind: str,
        progress: Callable[[int, int], None],
    ) -> str:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        shutil.move(str(source), str(destination))
        changed, error = ensure_extra_model_paths(self.cfg)
        if error:
            raise RuntimeError(error)
        set_selected_file(self.app.profile_key, kind, destination.name)
        self._needs_restart = True
        return tr("Déplacé : {filename}", filename=destination.name)

    def _copy_and_select(
        self,
        source: Path,
        destination: Path,
        kind: str,
        progress: Callable[[int, int], None],
    ) -> str:
        from models_tools import copy_file  # noqa: PLC0415

        copy_file(source, destination, progress=progress)
        changed, error = ensure_extra_model_paths(self.cfg)
        if error:
            raise RuntimeError(error)
        set_selected_file(self.app.profile_key, kind, destination.name)
        self._needs_restart = True
        return tr("Copié : {filename}", filename=destination.name)

    def _download(
        self,
        item: dict[str, Any],
        option_var: tk.StringVar | None,
        option_by_label: dict[str, dict[str, Any]],
    ) -> None:
        if self.busy or option_var is None:
            return
        if not bool(self.cfg.get("models", {}).get("allow_downloads", True)):
            messagebox.showinfo(
                tr("Téléchargements désactivés"),
                tr(
                    "Les téléchargements sont désactivés dans config.toml "
                    "([models] allow_downloads = false)."
                ),
                parent=self,
            )
            return
        option = option_by_label.get(option_var.get())
        if not option or not option.get("download_url"):
            messagebox.showerror(
                tr("Téléchargement indisponible"),
                tr("Aucune URL publique pour ce fichier."),
                parent=self,
            )
            return
        filename = str(option.get("filename", "?"))
        size = human_size(option.get("size"))
        if not messagebox.askyesno(
            tr("Télécharger le modèle ?"),
            tr(
                "Télécharger {filename} ({size}) ?\n\n"
                "Source : {url}\n\n"
                "Le téléchargement ne démarre qu'après cette confirmation.",
                filename=filename,
                size=size,
                url=str(option["download_url"]),
            ),
            parent=self,
        ):
            return

        from models_tools import download_file  # noqa: PLC0415

        store = self.app._model_store_dir()
        folder = str(item.get("folder") or FOLDER_FOR_KIND.get(str(item.get("kind")), "unet"))
        destination = store / folder / filename
        if destination.exists():
            expected = int(option.get("size") or 0)
            if expected and destination.stat().st_size == expected:
                if messagebox.askyesno(
                    tr("Fichier déjà présent"),
                    tr(
                        "{filename} est déjà présent dans le dossier. "
                        "L'utiliser sans le retélécharger ?",
                        filename=filename,
                    ),
                    parent=self,
                ):
                    set_selected_file(self.app.profile_key, str(item.get("kind")), filename)
                    changed, error = ensure_extra_model_paths(self.cfg)
                    if error:
                        messagebox.showerror(tr("Chemins ComfyUI"), error, parent=self)
                        return
                    self._needs_restart = True
                    self.refresh()
                    return
            elif not messagebox.askyesno(
                tr("Remplacer le fichier ?"),
                tr("{filename} existe déjà. Le remplacer ?", filename=filename),
                parent=self,
            ):
                return

        def work(progress: Callable[[int, int], None]) -> str:
            download_file(
                str(option["download_url"]),
                destination,
                expected_sha256=(
                    str(option.get("sha256")) if option.get("sha256") else None
                ),
                progress=progress,
            )
            changed, error = ensure_extra_model_paths(self.cfg)
            if error:
                raise RuntimeError(error)
            set_selected_file(self.app.profile_key, str(item.get("kind")), filename)
            self._needs_restart = True
            return tr("Téléchargé : {filename}", filename=filename)

        self._run_task(tr("Téléchargement de {filename}…", filename=filename), work)

    # ------------------------------------------------------------------
    # Krea 2 node
    # ------------------------------------------------------------------

    def _check_node_async(self) -> None:
        latest = latest_krea_release()
        status = krea_node_status(self.cfg, latest)
        self.queue.put(("node_status", status, latest))

    def _install_node(self) -> None:
        if self.busy:
            return
        latest = latest_krea_release()
        if not latest:
            messagebox.showerror(
                tr("Nœud Krea 2"),
                tr("Impossible de contacter GitHub pour trouver la dernière version."),
                parent=self,
            )
            return
        status = krea_node_status(self.cfg, latest)
        action = tr("Mettre à jour") if status.get("installed") else tr("Installer")
        if not messagebox.askyesno(
            tr("Nœud Krea 2"),
            tr(
                "{action} comfyui-krea2edit {version} ?\n\n"
                "Le nœud sera installé dans ComfyUI/custom_nodes, puis ComfyUI "
                "devra être redémarré.",
                action=action,
                version=latest.get("version", "?"),
            ),
            parent=self,
        ):
            return

        def work(progress: Callable[[int, int], None]) -> str:
            version = install_krea_node(self.cfg, latest, progress=progress)
            self._needs_restart = True
            return tr("Nœud Krea 2 v{version} installé.", version=version)

        self._run_task(tr("Installation du nœud Krea 2…"), work, refresh_node=True)

    def _open_node_release(self, _event: object = None) -> None:
        url = ""
        if self.node_status:
            latest = self.node_status.get("latest")
            if latest:
                url = f"https://github.com/lbouaraba/comfyui-krea2edit/releases/tag/v{latest}"
        if url:
            import webbrowser

            webbrowser.open(url)

    def _update_node_ui(self) -> None:
        status = self.node_status
        if not status:
            self.node_label.config(text=tr("Nœud Krea 2 : vérification…"), fg=MUTED)
            self.node_button.config(state="disabled")
            return
        if status.get("needs_install"):
            text = tr("Nœud Krea 2 : absent. Version disponible : v{version}.")
            self.node_label.config(text=text.format(version=status.get("latest") or "?"), fg=RED)
            self.node_button.config(state="normal" if not self.busy else "disabled")
        elif status.get("needs_update"):
            self.node_label.config(
                text=tr(
                    "Nœud Krea 2 : v{installed} installé, v{latest} disponible.",
                    installed=status.get("installed"),
                    latest=status.get("latest"),
                ),
                fg=YELLOW,
            )
            self.node_button.config(state="normal" if not self.busy else "disabled")
        else:
            self.node_label.config(
                text=tr("Nœud Krea 2 : v{version} installé.", version=status.get("installed") or "?"),
                fg=GREEN,
            )
            self.node_button.config(state="disabled")
        self.node_link.config(
            text=tr("Page Releases") if status.get("needs_install") or status.get("needs_update") else ""
        )
        self.restart_button.config(
            text=tr("Démarrer ComfyUI") if not self.app.comfy_ok else tr("Redémarrer ComfyUI")
        )

    # ------------------------------------------------------------------
    # Restart / tasks
    # ------------------------------------------------------------------

    def _update_restart_label(self) -> None:
        if self._needs_restart:
            self.restart_label.config(
                text=tr(
                    "ComfyUI doit être redémarré pour voir les nouveaux fichiers ou nœuds."
                )
            )
        else:
            self.restart_label.config(text="")

    def _maybe_restart_after_change(self) -> None:
        if not self._needs_restart or self.busy or self._closing:
            return
        question = (
            tr(
                "Les fichiers sont prêts. Redémarrer ComfyUI maintenant ? "
                "Une génération en cours sera interrompue."
            )
            if self.app.comfy_ok
            else tr("Les fichiers sont prêts. Démarrer ComfyUI maintenant ?")
        )
        if messagebox.askyesno(tr("ComfyUI"), question, parent=self):
            self._restart_comfyui(confirm=False)
        else:
            self.status.config(
                text=tr(
                    "Redémarre ComfyUI plus tard pour voir les nouveaux fichiers."
                ),
                fg=YELLOW,
            )

    def _restart_comfyui(self, confirm: bool = True) -> None:
        if self.busy:
            return
        endpoint = str(self.cfg.get("comfyui", {}).get("endpoint", ""))
        host = (urllib.parse.urlparse(endpoint).hostname or "").lower()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            messagebox.showerror(
                tr("ComfyUI"),
                tr(
                    "Le redémarrage automatique n'est disponible que pour un "
                    "ComfyUI local."
                ),
                parent=self,
            )
            return
        if confirm:
            text = (
                tr("Démarrer ComfyUI ?")
                if not self.app.comfy_ok
                else tr(
                    "Redémarrer ComfyUI ? Une génération en cours sera interrompue."
                )
            )
            if not messagebox.askyesno(tr("ComfyUI"), text, parent=self):
                return

        def work(progress: Callable[[int, int], None]) -> str:
            progress(0, 0)
            stop_comfyui(self.cfg)
            start_comfyui(self.cfg)
            if not wait_for_comfyui(self.cfg, 240):
                raise RuntimeError(tr("ComfyUI n'a pas redémarré dans les 4 minutes."))
            self._needs_restart = False
            return tr("ComfyUI est prêt.")

        self._run_task(tr("Redémarrage de ComfyUI…"), work, refresh_node=True)

    def _run_task(
        self,
        label: str,
        function: Callable[[Callable[[int, int], None]], str],
        *,
        refresh_node: bool = False,
    ) -> None:
        if self.busy:
            return
        self.busy = True
        self.progress.config(mode="determinate", value=0, maximum=100)
        self.status.config(text=label, fg=YELLOW)
        for row in self._rows:
            for child in row["frame"].winfo_children():
                try:
                    child.configure(state="disabled")
                except tk.TclError:
                    pass
        self.node_button.config(state="disabled")
        self.restart_button.config(state="disabled")

        def progress(done: int, total: int) -> None:
            self.queue.put(("progress", done, total))

        def worker() -> None:
            try:
                message = function(progress)
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("error", str(exc)))
            else:
                self.queue.put(("done", message, refresh_node))

        threading.Thread(target=worker, daemon=True).start()

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
                        self.progress.config(
                            maximum=total, value=min(done, total)
                        )
                        self.status.config(
                            text=tr(
                                "{done} / {total}",
                                done=human_size(done),
                                total=human_size(total),
                            ),
                            fg=YELLOW,
                        )
                    else:
                        self.progress.config(mode="indeterminate")
                        self.progress.start(15)
                elif kind == "done":
                    self.busy = False
                    self.progress.stop()
                    self.progress.config(mode="determinate", value=0)
                    self.status.config(text=str(item[1]), fg=GREEN)
                    self.app._log(str(item[1]))
                    if item[2]:
                        threading.Thread(target=self._check_node_async, daemon=True).start()
                    self.app._check_models()
                    self.refresh()
                    if self._needs_restart:
                        self.after(200, self._maybe_restart_after_change)
                elif kind == "error":
                    self.busy = False
                    self.progress.stop()
                    self.progress.config(mode="determinate", value=0)
                    self.status.config(text=str(item[1]), fg=RED)
                    self.app._log(f"Modèles : {item[1]}")
                    messagebox.showerror(tr("Erreur"), str(item[1]), parent=self)
                    self.refresh()
                elif kind == "node_status":
                    self.node_status = item[1]
                    self._update_node_ui()
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _open_store(self) -> None:
        path = self.app._model_store_dir()
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(tr("Dossier des modèles"), str(exc), parent=self)

    def _on_close(self) -> None:
        self._closing = True
        try:
            self.destroy()
        except Exception:  # noqa: BLE001
            pass
