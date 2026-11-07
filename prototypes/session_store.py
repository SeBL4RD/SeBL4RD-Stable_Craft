"""Persistent StableCraft sessions (one per generated layer).

A session keeps the original base composite, the selection mask, and every
generation. The session id is embedded in the layer name:

    StableCraft [ab12cd34] — prompt…

so clicking an old layer can find its gallery again, even after a restart.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

SESSION_RE = re.compile(r"StableCraft \[([0-9a-f]{8})\]")


def parse_session_id(layer_name: str) -> str | None:
    match = SESSION_RE.search(layer_name or "")
    return match.group(1) if match else None


def session_layer_name(session_id: str, prompt: str) -> str:
    text = " ".join((prompt or "").split())
    if len(text) > 48:
        text = text[:47].rstrip() + "…"
    return f"StableCraft [{session_id}] — {text}" if text else f"StableCraft [{session_id}]"


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def new_id(self) -> str:
        return uuid.uuid4().hex[:8]

    def directory(self, session_id: str) -> Path:
        return self.root / session_id

    def session_path(self, session_id: str) -> Path:
        return self.directory(session_id) / "session.json"

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        data.setdefault("schema", 1)
        data.setdefault("generations", [])
        data.setdefault("current", -1)
        self.save(data)
        return data

    def load(self, session_id: str) -> dict[str, Any]:
        path = self.session_path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"session {session_id!r} introuvable : {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("generations", [])
        data.setdefault("current", -1)
        return data

    def save(self, data: dict[str, Any]) -> None:
        path = self.session_path(str(data["id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    def clone_directory(self, source_id: str, destination_id: str) -> Path:
        """Copy a whole session (metadata, base/mask and generations)."""
        source = self.directory(source_id)
        destination = self.directory(destination_id)
        if not source.exists():
            raise FileNotFoundError(f"session {source_id!r} introuvable : {source}")
        if destination.exists():
            raise FileExistsError(f"session {destination_id!r} existe déjà")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        return destination

    def generation_dir(self, data: dict[str, Any], index: int) -> Path:
        return self.directory(str(data["id"])) / "generations" / str(index)

    def add_generation(self, data: dict[str, Any], generation: dict[str, Any]) -> int:
        index = len(data["generations"])
        generation["index"] = index
        generation.setdefault("created", time.strftime("%Y-%m-%dT%H:%M:%S"))
        data["generations"].append(generation)
        data["current"] = index
        self.save(data)
        return index

    def delete_generation(self, data: dict[str, Any], index: int) -> None:
        """Remove one generation and renumber the following folders."""
        generations = data.get("generations", [])
        if not 0 <= index < len(generations):
            raise IndexError(f"génération {index} hors limites")
        session_dir = self.directory(str(data["id"]))
        generations_dir = session_dir / "generations"
        shutil.rmtree(generations_dir / str(index), ignore_errors=True)
        generations.pop(index)
        for new_index in range(index, len(generations)):
            old_index = new_index + 1
            old_folder = generations_dir / str(old_index)
            new_folder = generations_dir / str(new_index)
            if old_folder.exists():
                if new_folder.exists():
                    shutil.rmtree(new_folder, ignore_errors=True)
                old_folder.rename(new_folder)
            generation = generations[new_index]
            generation["index"] = new_index
            old_prefix = f"generations/{old_index}/"
            for key in ("result", "thumb"):
                value = str(generation.get(key) or "").replace("\\", "/")
                if value.startswith(old_prefix):
                    generation[key] = (
                        f"generations/{new_index}/" + value[len(old_prefix) :]
                    )
        current = int(data.get("current", -1))
        if current == index:
            current = min(index, len(generations) - 1)
        elif current > index:
            current -= 1
        data["current"] = current
        self.save(data)

    def base_path(self, data: dict[str, Any]) -> Path:
        return self.directory(str(data["id"])) / data.get("base", "base.png")

    def mask_path(self, data: dict[str, Any]) -> Path:
        return self.directory(str(data["id"])) / data.get("mask", "mask.png")
