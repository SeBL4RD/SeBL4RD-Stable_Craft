"""LoRA manager and picker windows for StableCraft."""

from __future__ import annotations

import copy
import json
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any
from urllib.parse import urlparse

from i18n import profile_text, tr
from lora_store import (
    MAX_LORAS,
    PREVIEW_CACHE_DIR,
    LoraApi,
    compatibility,
    family_label,
    normalize_api_item,
    normalize_item,
    preview_cache_key,
    preview_cache_path,
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

CREATE_NO_WINDOW = 0x08000000
PICKER_PAGE_SIZE = 40


def _short(text: str, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


class LoraManager(tk.Toplevel):
    """Manage up to 10 LoRA slots for the current profile/layer."""

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.app = app
        self.api = LoraApi(str(app.cfg["comfyui"]["endpoint"]))
        self.profile_key = str(app.profile_key)
        self.profile = app.manifest["profiles"].get(self.profile_key, {})
        self.items: list[dict[str, Any]] = []
        for entry in app.lora_items[:MAX_LORAS]:
            value = normalize_item(entry)
            if value is not None:
                self.items.append(value)
        self._closed = False
        self._applied = False
        self._queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self._available: set[str] | None = None
        self._availability_error: str | None = None
        self._row_vars: list[dict[str, Any]] = []
        self._picker: LoraPicker | None = None

        self.title(
            tr(
                "LoRA — {profile}",
                profile=profile_text(self.profile, "label") or self.profile_key,
            )
        )
        self.geometry("860x780+420+50")
        self.minsize(760, 620)
        self.configure(bg=BG)
        self.transient(app)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._apply_and_close)

        self._build()
        self.after(80, self._poll)
        threading.Thread(target=self._load_availability, daemon=True).start()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self) -> None:
        header = tk.Frame(self, bg=BG, padx=16, pady=12)
        header.pack(fill="x")
        tk.Label(
            header,
            text=tr("LoRA — {profile}", profile=profile_text(self.profile, "label") or self.profile_key),
            bg=BG,
            fg=FG,
            font=("Segoe UI", 15, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            header,
            text=tr(
                "Les LoRA sont lus depuis ComfyUI. Aucun fichier n'est copié : "
                "utilise la page LoRA Manager pour ajouter ou organiser tes fichiers."
            ),
            bg=BG,
            fg=MUTED,
            justify="left",
            wraplength=820,
            anchor="w",
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(2, 4))
        self.count_label = tk.Label(
            header,
            text="",
            bg=BG,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        )
        self.count_label.pack(fill="x")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rows_frame = tk.Frame(self.canvas, bg=BG)
        self.window_id = self.canvas.create_window(
            (0, 0), window=self.rows_frame, anchor="nw"
        )
        self.rows_frame.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(self.window_id, width=event.width),
        )
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.rows_frame.bind("<MouseWheel>", self._on_wheel)

        footer = tk.Frame(self, bg=BG, padx=16, pady=10)
        footer.pack(fill="x", side="bottom")
        self.status = tk.Label(
            footer,
            text=tr("Vérification des LoRA…"),
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=820,
            font=("Segoe UI", 8),
        )
        self.status.pack(fill="x", pady=(0, 6))
        actions = tk.Frame(footer, bg=BG)
        actions.pack(fill="x")
        self.add_btn = self._button(
            actions, tr("Ajouter un LoRA"), self._add, bg=ACCENT
        )
        self.add_btn.pack(side="left")
        self._button(
            actions, tr("Ouvrir la page LoRA Manager"), self._open_page, bg=PANEL_2
        ).pack(side="left", padx=(6, 0))
        self._button(actions, tr("Actualiser"), self._refresh, bg=PANEL_2).pack(
            side="left", padx=(6, 0)
        )
        self._button(actions, tr("Fermer"), self._apply_and_close, bg=PANEL_2).pack(
            side="right"
        )
        self._button(actions, tr("Annuler"), self._cancel_and_close, bg=PANEL_2).pack(
            side="right", padx=(0, 6)
        )
        self.bind("<Escape>", lambda _event: self._cancel_and_close())

        self._rebuild_rows()

    def _button(
        self, parent: tk.Misc, text: str, command: Any, bg: str = PANEL_2
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg="white" if bg == ACCENT else FG,
            activebackground=ACCENT_ACTIVE if bg == ACCENT else BORDER,
            activeforeground="white" if bg == ACCENT else FG,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            font=("Segoe UI", 9),
            cursor="hand2",
        )

    def _on_wheel(self, event: tk.Event) -> str:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    # ------------------------------------------------------------------
    # Rows
    # ------------------------------------------------------------------

    def _rebuild_rows(self) -> None:
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._row_vars = []
        if not self.items:
            tk.Label(
                self.rows_frame,
                text=tr(
                    "Aucun LoRA sélectionné. Clique sur « Ajouter un LoRA » "
                    "pour en choisir un."
                ),
                bg=BG,
                fg=MUTED,
                anchor="w",
                justify="left",
                wraplength=760,
                font=("Segoe UI", 9),
            ).pack(fill="x", pady=16)
        for index, item in enumerate(self.items):
            self._make_row(index, item)
        self.count_label.config(
            text=tr("{count}/{max} LoRA", count=len(self.items), max=MAX_LORAS)
        )
        self.add_btn.config(
            state="disabled" if len(self.items) >= MAX_LORAS else "normal"
        )
        self._update_status()

    def _make_row(self, index: int, item: dict[str, Any]) -> None:
        row = tk.Frame(
            self.rows_frame,
            bg=PANEL,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        row.pack(fill="x", pady=(0, 6))
        top = tk.Frame(row, bg=PANEL)
        top.pack(fill="x")
        enabled_var = tk.BooleanVar(value=bool(item.get("enabled", True)))
        tk.Checkbutton(
            top,
            variable=enabled_var,
            command=lambda i=index, v=enabled_var: self._toggle_item(i, v),
            bg=PANEL,
            fg=FG,
            selectcolor=PANEL_2,
            activebackground=PANEL,
            activeforeground=FG,
        ).pack(side="left")
        name_label = tk.Label(
            top,
            text=_short(str(item.get("label") or "?"), 52),
            bg=PANEL,
            fg=FG,
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        )
        name_label.pack(side="left", padx=(2, 8))
        folder = str(item.get("folder") or "")
        tk.Label(
            top,
            text=_short(folder, 30) if folder else "—",
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 8),
        ).pack(side="left")
        self._button(top, "×", lambda i=index: self._remove(i), bg=PANEL_2).pack(
            side="right"
        )
        self._button(top, tr("Choisir…"), lambda i=index: self._choose(i), bg=PANEL_2).pack(
            side="right", padx=(0, 6)
        )

        bottom = tk.Frame(row, bg=PANEL)
        bottom.pack(fill="x", pady=(6, 0))
        tk.Label(
            bottom,
            text=tr("Force"),
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(side="left")
        strength_var = tk.DoubleVar(value=max(0.0, min(1.0, float(item.get("strength", 1.0)))))
        strength_text = tk.StringVar(value=f"{strength_var.get():.2f}")
        scale = ttk.Scale(
            bottom,
            from_=0.0,
            to=1.0,
            variable=strength_var,
            command=lambda value, i=index: self._on_scale(i, value),
        )
        scale.pack(side="left", fill="x", expand=True, padx=(8, 8))
        spin = ttk.Spinbox(
            bottom,
            from_=0.0,
            to=1.0,
            increment=0.05,
            textvariable=strength_text,
            width=5,
            command=lambda i=index: self._on_spin(i),
        )
        spin.pack(side="left")
        spin.bind("<Return>", lambda _event, i=index: self._on_spin(i))
        spin.bind("<FocusOut>", lambda _event, i=index: self._on_spin(i))

        def on_var(*_args: Any, i: int = index, text_var: tk.StringVar = strength_text) -> None:
            value = max(0.0, min(1.0, float(strength_var.get())))
            text_var.set(f"{value:.2f}")
            if 0 <= i < len(self.items):
                self.items[i]["strength"] = value

        strength_var.trace_add("write", on_var)

        warning = self._row_warning(item)
        if warning:
            tk.Label(
                row,
                text=warning,
                bg=PANEL,
                fg=YELLOW,
                anchor="w",
                justify="left",
                wraplength=760,
                font=("Segoe UI", 8),
            ).pack(fill="x", pady=(4, 0))

        self._row_vars.append(
            {
                "enabled": enabled_var,
                "strength": strength_var,
                "strength_text": strength_text,
                "scale": scale,
                "spin": spin,
                "name": name_label,
            }
        )

    def _toggle_item(self, index: int, var: tk.BooleanVar) -> None:
        if 0 <= index < len(self.items):
            self.items[index]["enabled"] = bool(var.get())
            self._update_status()

    def _on_scale(self, index: int, value: str) -> None:
        if not 0 <= index < len(self.items):
            return
        try:
            number = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return
        self.items[index]["strength"] = number

    def _on_spin(self, index: int) -> None:
        if not 0 <= index < len(self.items) or index >= len(self._row_vars):
            return
        values = self._row_vars[index]
        text_var: tk.StringVar = values["strength_text"]
        strength_var: tk.DoubleVar = values["strength"]
        try:
            number = float(str(text_var.get()).replace(",", "."))
        except (TypeError, ValueError):
            number = float(self.items[index].get("strength", 1.0))
        number = max(0.0, min(1.0, number))
        text_var.set(f"{number:.2f}")
        strength_var.set(number)
        self.items[index]["strength"] = number

    def _row_warning(self, item: dict[str, Any]) -> str:
        warnings: list[str] = []
        name = str(item.get("name") or "")
        if (
            self._available is not None
            and name.replace("\\", "/").casefold() not in self._available
        ):
            warnings.append(tr("Introuvable dans ComfyUI."))
        family = str(item.get("arch") or "")
        state = compatibility(self.profile_key, family)
        if state == "incompatible":
            warnings.append(
                tr(
                    "Architecture {arch} — incompatible avec {profile}.",
                    arch=family_label(family),
                    profile=profile_text(self.profile, "label") or self.profile_key,
                )
            )
        if item.get("has_text_encoder"):
            warnings.append(tr("Contient un text encoder — seule la partie modèle est appliquée."))
        return "⚠ " + " ".join(warnings) if warnings else ""

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _load_availability(self) -> None:
        try:
            names = self.api.comfy_names()
            self._queue.put(("availability", names, None))
        except Exception as exc:  # noqa: BLE001
            self._queue.put(("availability", None, str(exc)))

    def _refresh(self) -> None:
        self.status.config(text=tr("Vérification des LoRA…"), fg=MUTED)
        self._available = None
        threading.Thread(target=self._load_availability, daemon=True).start()

    def _open_page(self) -> None:
        try:
            webbrowser.open(self.api.page_url())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(tr("LoRA Manager"), str(exc), parent=self)

    def _choose(self, index: int) -> None:
        if self.app.running or not 0 <= index < len(self.items):
            return
        used = {
            str(item.get("name") or "").replace("\\", "/").casefold()
            for position, item in enumerate(self.items)
            if position != index
        }
        picker = LoraPicker(
            self,
            self.api,
            self.profile_key,
            current=str(self.items[index].get("name") or ""),
            used=used,
            app=self.app,
        )
        self._picker = picker
        self.wait_window(picker)
        self._picker = None
        if self._closed:
            return
        self.grab_set()
        result = picker.result
        if not result:
            return
        previous = self.items[index]
        result["strength"] = previous.get("strength", 1.0)
        result["enabled"] = previous.get("enabled", True)
        value = normalize_item(result)
        if value is not None:
            self.items[index] = value
            self._rebuild_rows()

    def _add(self) -> None:
        if self.app.running:
            return
        if len(self.items) >= MAX_LORAS:
            messagebox.showinfo(
                tr("LoRA"),
                tr("Maximum {max} LoRA par profil.", max=MAX_LORAS),
                parent=self,
            )
            return
        used = {
            str(item.get("name") or "").replace("\\", "/").casefold()
            for item in self.items
        }
        picker = LoraPicker(
            self,
            self.api,
            self.profile_key,
            current="",
            used=used,
            app=self.app,
        )
        self._picker = picker
        self.wait_window(picker)
        self._picker = None
        if self._closed:
            return
        self.grab_set()
        result = picker.result
        if not result:
            return
        value = normalize_item(result)
        if value is not None:
            self.items.append(value)
            self._rebuild_rows()

    def _remove(self, index: int) -> None:
        if 0 <= index < len(self.items):
            self.items.pop(index)
            self._rebuild_rows()

    def _update_status(self) -> None:
        if self._availability_error:
            self.status.config(
                text=tr(
                    "ComfyUI/LoRA Manager indisponible : {error}",
                    error=self._availability_error,
                ),
                fg=RED,
            )
        elif self._available is not None:
            self.status.config(
                text=tr(
                    "Liste ComfyUI chargée : {count} LoRA visibles. "
                    "La génération validera chaque nom.",
                    count=len(self._available),
                ),
                fg=GREEN,
            )
        else:
            self.status.config(text=tr("Vérification des LoRA…"), fg=MUTED)

    def _poll(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "availability":
                    names = item[1]
                    error = item[2]
                    if names is None:
                        self._availability_error = str(error or "?")
                        self._available = set()
                        self.app._lora_available = None
                    else:
                        self._availability_error = None
                        self._available = {
                            str(name).replace("\\", "/").casefold()
                            for name in names
                        }
                        self.app._lora_available = set(self._available)
                    self._rebuild_rows()
                    self.app._update_lora_ui()
        except queue.Empty:
            pass
        if not self._closed:
            self.after(120, self._poll)

    def _apply_and_close(self) -> None:
        if self._closed:
            return
        self._applied = True
        values = []
        for entry in self.items[:MAX_LORAS]:
            value = normalize_item(entry)
            if value is not None:
                values.append(value)
        self.app._apply_lora_items(values)
        self._close()

    def _cancel_and_close(self) -> None:
        self._close()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class LoraPicker(tk.Toplevel):
    """Searchable LoRA picker with details and thumbnail grid views."""

    def __init__(
        self,
        parent: tk.Misc,
        api: LoraApi,
        profile_key: str,
        *,
        current: str = "",
        used: set[str] | None = None,
        app: Any = None,
    ) -> None:
        super().__init__(parent)
        self.parent = parent
        self.api = api
        self.profile_key = profile_key
        self.app = app
        self.current = current
        self.used = set(used or set())
        self.result: dict[str, Any] | None = None
        self.items: list[dict[str, Any]] = []
        self.page = 0
        self.total = 0
        self.total_pages = 0
        self.selected_name = ""
        self.view = "details"
        self._closed = False
        self._queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self._request_id = 0
        self._search_after: str | None = None
        self._page_loading = False
        self._comfy_names: list[str] = []
        self._comfy_loaded = False
        self._tiles: dict[str, dict[str, Any]] = {}
        self._thumb_images: dict[str, tk.PhotoImage] = {}
        self._thumb_keys: dict[str, str] = {}
        self._pending_thumbs: set[str] = set()
        self._thumbs_running = False
        self._thumb_proc: subprocess.Popen[str] | None = None
        self._thumb_total = 0
        self._thumb_done = 0
        self._fallback = False
        self._tree: ttk.Treeview | None = None

        profile = app.manifest["profiles"].get(profile_key, {}) if app else {}
        label = profile_text(profile, "label") or profile_key
        self.title(tr("Sélectionner un LoRA"))
        self.geometry("980x800+360+30")
        self.minsize(840, 620)
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._build(label)
        self.after(80, self._poll)
        self._schedule_search(immediate=True)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self, profile_label: str) -> None:
        header = tk.Frame(self, bg=BG, padx=14, pady=10)
        header.pack(fill="x")
        title_row = tk.Frame(header, bg=BG)
        title_row.pack(fill="x")
        tk.Label(
            title_row,
            text=tr("Sélectionner un LoRA"),
            bg=BG,
            fg=FG,
            font=("Segoe UI", 15, "bold"),
            anchor="w",
        ).pack(side="left")
        tk.Label(
            title_row,
            text=tr("Profil actuel : {profile}", profile=profile_label),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="e",
        ).pack(side="right")
        tk.Label(
            header,
            text=tr(
                "La liste et les miniatures viennent de ComfyUI LoRA Manager. "
                "Aucun fichier n'est copié."
            ),
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=930,
            font=("Segoe UI", 8),
        ).pack(fill="x", pady=(2, 8))

        search_row = tk.Frame(header, bg=BG)
        search_row.pack(fill="x")
        tk.Label(
            search_row,
            text=tr("Rechercher"),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left")
        self.search_var = tk.StringVar()
        search = tk.Entry(
            search_row,
            textvariable=self.search_var,
            bg=PANEL_2,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        search.pack(side="left", fill="x", expand=True, padx=(8, 10), ipady=3)
        search.bind("<KeyRelease>", lambda _event: self._schedule_search())
        self.search_entry = search

        self.details_btn = self._view_button(search_row, tr("Détails"), "details")
        self.details_btn.pack(side="left")
        self.grid_btn = self._view_button(search_row, tr("Grille"), "grid")
        self.grid_btn.pack(side="left", padx=(4, 0))
        self._update_view_buttons()

        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill="both", expand=True, padx=12)

        footer = tk.Frame(self, bg=BG, padx=14, pady=10)
        footer.pack(fill="x", side="bottom")
        self.status = tk.Label(
            footer,
            text=tr("Chargement de la liste…"),
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=930,
            font=("Segoe UI", 8),
        )
        self.status.pack(fill="x", pady=(0, 6))
        actions = tk.Frame(footer, bg=BG)
        actions.pack(fill="x")
        self.more_btn = self._button(actions, tr("Charger plus"), self._load_more, bg=PANEL_2)
        self.more_btn.pack(side="left")
        self.more_btn.pack_forget()
        self.use_btn = self._button(actions, tr("Utiliser ce LoRA"), self._use_selected, bg=ACCENT)
        self.use_btn.pack(side="right")
        self.use_btn.config(state="disabled")
        self._button(actions, tr("Annuler"), self._cancel, bg=PANEL_2).pack(
            side="right", padx=(0, 6)
        )
        self.bind("<Escape>", lambda _event: self._cancel())

    def _button(
        self, parent: tk.Misc, text: str, command: Any, bg: str = PANEL_2
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg="white" if bg == ACCENT else FG,
            activebackground=ACCENT_ACTIVE if bg == ACCENT else BORDER,
            activeforeground="white" if bg == ACCENT else FG,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            font=("Segoe UI", 9),
            cursor="hand2",
        )

    def _view_button(self, parent: tk.Misc, text: str, view: str) -> tk.Button:
        return self._button(
            parent,
            text,
            lambda target=view: self._set_view(target),
            bg=PANEL_2,
        )

    def _update_view_buttons(self) -> None:
        for view, button in (("details", self.details_btn), ("grid", self.grid_btn)):
            active = self.view == view
            button.config(
                bg=ACCENT if active else PANEL_2,
                activebackground=ACCENT_ACTIVE if active else BORDER,
                fg="white" if active else FG,
            )

    def _set_view(self, view: str) -> None:
        if view not in {"details", "grid"}:
            return
        if self.view == view:
            return
        self.view = view
        self._update_view_buttons()
        self._render_view()
        if self.view == "grid":
            self._start_thumbnails(self.items)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _schedule_search(self, immediate: bool = False) -> None:
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except tk.TclError:
                pass
            self._search_after = None
        if immediate:
            self._search()
        else:
            self._search_after = self.after(350, self._search)

    def _search(self) -> None:
        self._search_after = None
        self._request_id += 1
        self.page = 0
        self.total = 0
        self.total_pages = 0
        self.items = []
        self.selected_name = ""
        self._page_loading = False
        self._fallback = False
        self._thumb_keys.clear()
        self._pending_thumbs.clear()
        self._render_view()
        self._update_footer()
        self._start_page_load(1, self._request_id, reset=True)

    def _start_page_load(self, page: int, request_id: int, reset: bool) -> None:
        if self._page_loading:
            return
        self._page_loading = True
        self._update_footer()
        search = self.search_var.get().strip()
        self.status.config(text=tr("Chargement de la liste…"), fg=MUTED)

        def work() -> None:
            try:
                data = self.api.list_loras(page, PICKER_PAGE_SIZE, search)
                if not self._comfy_loaded:
                    try:
                        self._comfy_names = self.api.comfy_names()
                    except Exception:  # noqa: BLE001
                        self._comfy_names = []
                    self._comfy_loaded = True
                items = []
                for raw in data.get("items", []):
                    value = normalize_api_item(raw, self._comfy_names)
                    if value is not None:
                        items.append(value)
                self._fallback = False
                self._queue.put(("page", request_id, page, data, items, None))
            except Exception as exc:  # noqa: BLE001
                # Fallback: ComfyUI's own LoRA list, without thumbnails or
                # architecture metadata. The LoRA Manager custom node is optional.
                try:
                    names = self.api.comfy_names()
                    all_items: list[dict[str, Any]] = []
                    term = search.casefold()
                    for name in names:
                        path = Path(str(name).replace("\\", "/"))
                        folder = "" if str(path.parent) in {"", "."} else str(path.parent).replace("\\", "/")
                        label = path.name
                        if term and term not in label.casefold() and term not in folder.casefold():
                            continue
                        all_items.append(
                            {
                                "name": str(name),
                                "label": label,
                                "folder": folder,
                                "arch": "",
                                "architecture": "",
                                "has_text_encoder": False,
                                "strength": 1.0,
                                "enabled": True,
                                "file_path": "",
                                "preview_url": "",
                                "preview_file": "",
                                "modified": 0,
                            }
                        )
                    total = len(all_items)
                    start = max(0, (page - 1) * PICKER_PAGE_SIZE)
                    chunk = all_items[start : start + PICKER_PAGE_SIZE]
                    fallback_data = {
                        "items": [],
                        "total": total,
                        "page": page,
                        "page_size": PICKER_PAGE_SIZE,
                        "total_pages": max(1, (total + PICKER_PAGE_SIZE - 1) // PICKER_PAGE_SIZE),
                    }
                    self._fallback = True
                    self._queue.put(("page", request_id, page, fallback_data, chunk, None))
                except Exception as fallback_exc:  # noqa: BLE001
                    self._queue.put(
                        ("page", request_id, page, None, [], str(fallback_exc or exc))
                    )

        threading.Thread(target=work, daemon=True).start()

    def _load_more(self) -> None:
        if self.page < self.total_pages and not self._page_loading:
            self._start_page_load(self.page + 1, self._request_id, reset=False)

    def _poll(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "page":
                    self._handle_page(item)
                elif kind == "thumb":
                    self._handle_thumb(item[1], bool(item[2]), str(item[3]))
                elif kind == "thumbs_done":
                    self._thumbs_running = False
                    self._thumb_proc = None
                    self._update_footer()
                    if self.selected_name:
                        self._update_selection_status()
                    if self.view == "grid" and not self._closed:
                        self._start_thumbnails(self.items)
                elif kind == "thumb_error":
                    self._thumbs_running = False
                    self._thumb_proc = None
                    self._pending_thumbs.clear()
                    self.status.config(
                        text=tr("Miniatures indisponibles : {error}", error=str(item[1])),
                        fg=YELLOW,
                    )
        except queue.Empty:
            pass
        if not self._closed:
            self.after(100, self._poll)

    def _handle_page(self, item: tuple[Any, ...]) -> None:
        _kind, request_id, page, data, items, error = item
        if request_id != self._request_id or self._closed:
            return
        self._page_loading = False
        if error is not None or data is None:
            self._update_footer()
            self.status.config(text=tr("Erreur LoRA : {error}", error=error or "?"), fg=RED)
            return
        if page <= 1:
            self.items = list(items)
        else:
            known = {str(value.get("name") or "").casefold() for value in self.items}
            for value in items:
                key = str(value.get("name") or "").casefold()
                if key and key not in known:
                    self.items.append(value)
                    known.add(key)
        self.page = int(data.get("page", page) or page)
        self.total = int(data.get("total", len(self.items)) or 0)
        self.total_pages = int(data.get("total_pages", 1) or 1)
        if self.selected_name and not self._item_by_name(self.selected_name):
            self.selected_name = ""
        self._render_view()
        self._update_footer()
        if self._fallback:
            self.status.config(
                text=tr(
                    "LoRA Manager indisponible — liste ComfyUI, sans miniatures."
                ),
                fg=YELLOW,
            )
        if self.selected_name:
            self._update_selection_status()
        if self.view == "grid":
            self._start_thumbnails(self.items)

    def _item_by_name(self, name: str) -> dict[str, Any] | None:
        target = str(name or "").casefold()
        for item in self.items:
            if str(item.get("name") or "").casefold() == target:
                return item
        return None

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_view(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        self._tiles = {}
        self._thumb_keys.clear()
        self._tree = None
        if not self.items:
            text = (
                tr("Chargement…")
                if self._page_loading
                else tr("Aucun LoRA trouvé.")
            )
            tk.Label(
                self.content,
                text=text,
                bg=BG,
                fg=MUTED,
                anchor="w",
                font=("Segoe UI", 9),
            ).pack(fill="x", pady=20)
            return
        if self.view == "details":
            self._render_details()
        else:
            self._render_grid()

    def _render_details(self) -> None:
        container = tk.Frame(self.content, bg=BG)
        container.pack(fill="both", expand=True)
        style = ttk.Style(self)
        style.configure(
            "Lora.Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=FG,
            rowheight=24,
            borderwidth=0,
        )
        style.configure(
            "Lora.Treeview.Heading",
            background=PANEL_2,
            foreground=FG,
            relief="flat",
        )
        style.map(
            "Lora.Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", "white")],
        )
        self._tree = ttk.Treeview(
            container,
            columns=("name", "folder"),
            show="headings",
            selectmode="browse",
            style="Lora.Treeview",
        )
        self._tree.heading("name", text=tr("Nom"))
        self._tree.heading("folder", text=tr("Dossier"))
        self._tree.column("name", width=600, anchor="w")
        self._tree.column("folder", width=250, anchor="w")
        scrollbar = ttk.Scrollbar(
            container, orient="vertical", command=self._tree.yview
        )
        self._tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)
        self._tree.tag_configure("incompatible", foreground=YELLOW)
        self._tree.tag_configure("used", foreground=MUTED)
        selected_index = None
        for index, value in enumerate(self.items):
            tags = []
            if compatibility(self.profile_key, str(value.get("arch") or "")) == "incompatible":
                tags.append("incompatible")
            if str(value.get("name") or "").replace("\\", "/").casefold() in self.used:
                tags.append("used")
            self._tree.insert(
                "",
                "end",
                iid=str(index),
                values=(value.get("label") or "?", value.get("folder") or "—"),
                tags=tuple(tags),
            )
            if self.selected_name and str(value.get("name") or "").casefold() == self.selected_name.casefold():
                selected_index = index
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-1>", lambda _event: self._use_selected())
        if selected_index is not None:
            self._tree.selection_set(str(selected_index))
            self._tree.see(str(selected_index))

    def _render_grid(self) -> None:
        container = tk.Frame(self.content, bg=BG)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.grid_canvas = canvas
        inner = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window_id, width=event.width),
        )
        canvas.bind("<MouseWheel>", self._on_grid_wheel)
        inner.bind("<MouseWheel>", self._on_grid_wheel)
        for column in range(4):
            inner.columnconfigure(column, weight=1)

        for index, value in enumerate(self.items):
            tile = tk.Frame(
                inner,
                bg=PANEL_2,
                padx=6,
                pady=6,
                highlightthickness=2,
                highlightbackground=BORDER,
            )
            tile.grid(row=index // 4, column=index % 4, padx=6, pady=6, sticky="nsew")
            thumb_frame = tk.Frame(tile, bg="#111114", width=164, height=164)
            thumb_frame.pack()
            thumb_frame.pack_propagate(False)
            image_label = tk.Label(
                thumb_frame,
                text=tr("Aperçu"),
                bg="#111114",
                fg=MUTED,
                font=("Segoe UI", 8),
            )
            image_label.pack(expand=True)
            name_label = tk.Label(
                tile,
                text=_short(str(value.get("label") or "?"), 30),
                bg=PANEL_2,
                fg=FG,
                anchor="w",
                justify="left",
                wraplength=160,
                font=("Segoe UI", 8, "bold"),
            )
            name_label.pack(fill="x", pady=(4, 0))
            folder_label = tk.Label(
                tile,
                text=str(value.get("folder") or "—"),
                bg=PANEL_2,
                fg=MUTED,
                anchor="w",
                font=("Segoe UI", 7),
            )
            folder_label.pack(fill="x")
            for widget in (tile, thumb_frame, image_label, name_label, folder_label):
                widget.bind(
                    "<Button-1>", lambda _event, i=index: self._select_index(i)
                )
                widget.bind("<MouseWheel>", self._on_grid_wheel)
            self._tiles[str(index)] = {
                "frame": tile,
                "image": image_label,
                "index": index,
            }
            key = preview_cache_key(value)
            if key:
                self._thumb_keys[key] = str(index)
                path = preview_cache_path(key)
                if path.exists():
                    self._load_thumb(key, str(path))
        if self.selected_name:
            self._update_tile_styles()

    def _on_grid_wheel(self, event: tk.Event) -> str:
        canvas = getattr(self, "grid_canvas", None)
        if canvas is not None:
            canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _on_tree_select(self, _event: object = None) -> None:
        if self._tree is None:
            return
        selection = self._tree.selection()
        if not selection:
            return
        try:
            index = int(selection[0])
        except (TypeError, ValueError):
            return
        self._select_index(index, from_tree=True)

    def _select_index(self, index: int, from_tree: bool = False) -> None:
        if not 0 <= index < len(self.items):
            return
        value = self.items[index]
        self.selected_name = str(value.get("name") or "")
        if self._tree is not None and not from_tree:
            try:
                self._tree.selection_set(str(index))
                self._tree.see(str(index))
            except tk.TclError:
                pass
        self._update_tile_styles()
        self._update_selection_status()

    def _update_tile_styles(self) -> None:
        for data in self._tiles.values():
            index = data.get("index")
            item = (
                self.items[index]
                if isinstance(index, int) and 0 <= index < len(self.items)
                else None
            )
            selected = bool(
                item
                and self.selected_name
                and str(item.get("name") or "").casefold()
                == self.selected_name.casefold()
            )
            incompatible = bool(
                item
                and compatibility(self.profile_key, str(item.get("arch") or ""))
                == "incompatible"
            )
            data["frame"].config(
                highlightbackground=(
                    ACCENT if selected else YELLOW if incompatible else BORDER
                )
            )

    def _update_selection_status(self) -> None:
        item = self._item_by_name(self.selected_name)
        if not item:
            self.status.config(text=tr("Sélectionne un LoRA."), fg=MUTED)
            self.use_btn.config(state="disabled")
            return
        parts = [str(item.get("label") or "?")]
        folder = str(item.get("folder") or "")
        if folder:
            parts.append(folder)
        family = str(item.get("arch") or "")
        if family:
            parts.append(family_label(family))
        state = compatibility(self.profile_key, family)
        if state == "incompatible":
            parts.append(tr("incompatible"))
        if item.get("has_text_encoder"):
            parts.append(tr("text encoder ignoré"))
        if str(item.get("name") or "").replace("\\", "/").casefold() in self.used:
            parts.append(tr("déjà utilisé"))
        self.status.config(text=" · ".join(parts), fg=MUTED)
        used = str(item.get("name") or "").replace("\\", "/").casefold() in self.used
        self.use_btn.config(state="disabled" if used else "normal")

    def _update_footer(self) -> None:
        if self._page_loading:
            self.status.config(text=tr("Chargement…"), fg=MUTED)
        elif not self.items:
            self.status.config(text=tr("Aucun LoRA trouvé."), fg=MUTED)
        else:
            self.status.config(
                text=tr(
                    "Page {page}/{pages} · {total} LoRA",
                    page=self.page,
                    pages=max(1, self.total_pages),
                    total=self.total or len(self.items),
                ),
                fg=MUTED,
            )
        if self.page < self.total_pages:
            self.more_btn.pack(side="left")
            self.more_btn.config(state="disabled" if self._page_loading else "normal")
        else:
            self.more_btn.pack_forget()
        if not self.selected_name:
            self.use_btn.config(state="disabled")

    # ------------------------------------------------------------------
    # Thumbnails
    # ------------------------------------------------------------------

    def _thumb_source(self, item: dict[str, Any]) -> dict[str, str]:
        preview_url = str(item.get("preview_url") or "").strip()
        if preview_url:
            if preview_url.startswith(("http://", "https://")):
                url = preview_url
            elif preview_url.startswith("/"):
                url = self.api.endpoint + preview_url
            else:
                url = self.api.endpoint + "/" + preview_url
            # The LoRA Manager can point at remote CivitAI previews. Do not
            # download those from a metered connection; only the configured
            # ComfyUI host is allowed.
            endpoint_host = urlparse(self.api.endpoint).netloc
            preview_host = urlparse(url).netloc
            if preview_host and endpoint_host and preview_host != endpoint_host:
                return {}
            return {"url": url}
        preview_file = str(item.get("preview_file") or "").strip()
        if preview_file:
            return {"file": preview_file}
        return {}

    def _start_thumbnails(self, items: list[dict[str, Any]] | None = None) -> None:
        if self._thumbs_running or self._closed:
            return
        jobs: list[dict[str, str]] = []
        for index, item in enumerate(self.items):
            key = preview_cache_key(item)
            if not key:
                continue
            self._thumb_keys[key] = str(index)
            path = preview_cache_path(key)
            if path.exists():
                self._load_thumb(key, str(path))
                continue
            if key in self._pending_thumbs:
                continue
            source = self._thumb_source(item)
            if not source:
                continue
            jobs.append({"key": key, **source})
            self._pending_thumbs.add(key)
        if not jobs:
            return
        python, error = self.app._comfy_python() if self.app is not None else (None, "app")
        if error or not python:
            self.status.config(
                text=tr("Miniatures indisponibles : {error}", error=error or "Python"),
                fg=YELLOW,
            )
            for job in jobs:
                self._pending_thumbs.discard(job["key"])
            return
        helper = Path(__file__).resolve().parent / "lora_previews.py"
        if not helper.exists():
            self.status.config(
                text=tr("Miniatures indisponibles : {error}", error=str(helper)),
                fg=YELLOW,
            )
            for job in jobs:
                self._pending_thumbs.discard(job["key"])
            return
        self._thumbs_running = True
        self._thumb_total = len(jobs)
        self._thumb_done = 0
        self._update_thumb_status()

        def work() -> None:
            jobs_path = PREVIEW_CACHE_DIR / f"jobs_{os.getpid()}_{time.time_ns()}.json"
            proc: subprocess.Popen[str] | None = None
            try:
                PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                jobs_path.write_text(
                    json.dumps(jobs, ensure_ascii=False), encoding="utf-8"
                )
                proc = subprocess.Popen(
                    [
                        python,
                        str(helper),
                        "--jobs",
                        str(jobs_path),
                        "--cache-dir",
                        str(PREVIEW_CACHE_DIR),
                        "--size",
                        "160",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                self._thumb_proc = proc
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = str(payload.get("key") or "")
                    if not key:
                        continue
                    if payload.get("ok"):
                        self._queue.put(
                            ("thumb", key, True, str(preview_cache_path(key)))
                        )
                    else:
                        self._queue.put(
                            ("thumb", key, False, str(payload.get("error") or "?"))
                        )
                proc.wait()
                if proc.returncode not in (0, None):
                    self._queue.put(
                        ("thumb_error", f"lora_previews.py exit {proc.returncode}")
                    )
                else:
                    self._queue.put(("thumbs_done",))
            except Exception as exc:  # noqa: BLE001
                self._queue.put(("thumb_error", str(exc)))
            finally:
                try:
                    jobs_path.unlink()
                except OSError:
                    pass
                if proc is not None and proc.poll() is None:
                    try:
                        proc.terminate()
                    except OSError:
                        pass

        threading.Thread(target=work, daemon=True).start()

    def _handle_thumb(self, key: str, ok: bool, value: str) -> None:
        self._pending_thumbs.discard(key)
        self._thumb_done += 1
        if ok:
            self._load_thumb(key, value)
        self._update_thumb_status()

    def _load_thumb(self, key: str, path: str) -> None:
        if key in self._thumb_images:
            image = self._thumb_images[key]
        else:
            try:
                image = tk.PhotoImage(file=path)
            except Exception:  # noqa: BLE001
                return
            self._thumb_images[key] = image
        tile_key = self._thumb_keys.get(key, "")
        tile = self._tiles.get(tile_key)
        if tile is None:
            return
        label: tk.Label = tile["image"]
        label.config(image=image, text="", width=0, height=0)

    def _update_thumb_status(self) -> None:
        if not self._thumbs_running:
            return
        self.status.config(
            text=tr(
                "Chargement des miniatures… {done}/{total}",
                done=self._thumb_done,
                total=self._thumb_total,
            ),
            fg=MUTED,
        )

    # ------------------------------------------------------------------
    # Selection / close
    # ------------------------------------------------------------------

    def _use_selected(self) -> None:
        item = self._item_by_name(self.selected_name)
        if not item:
            messagebox.showinfo(tr("LoRA"), tr("Sélectionne un LoRA."), parent=self)
            return
        if str(item.get("name") or "").replace("\\", "/").casefold() in self.used:
            messagebox.showinfo(
                tr("LoRA"), tr("Ce LoRA est déjà dans la liste."), parent=self
            )
            return
        self.result = copy.deepcopy(item)
        self._close()

    def _cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._thumb_proc is not None and self._thumb_proc.poll() is None:
            try:
                self._thumb_proc.terminate()
            except OSError:
                pass
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
