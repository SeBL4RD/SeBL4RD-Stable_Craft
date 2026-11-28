"""On-demand installer for the optional ComfyUI caption engines.

Nothing here runs from the main installer.  The caption manager calls these
functions only after the user explicitly asks to install a node, its vision
backend, or a model.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import urllib.request
from pathlib import Path
from typing import Any, Callable

from caption_engines import (
    CaptionEngine,
    CaptionModelFile,
    comfy_models_dir,
    engine_installed,
    llama_cpp_wheel,
    model_url,
)
from models_tools import (
    CACHE_DIR,
    DownloadToken,
    comfyui_root,
    download_file,
    endpoint_port,
    install_custom_node,
    start_comfyui,
    stop_comfyui,
    wait_for_comfyui,
    wait_port,
)
from platform_support import comfyui_app_dir, comfyui_manageable, comfyui_python

StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]

_VISION_CACHE: dict[str, bool] = {}


def _python(cfg: dict[str, Any]) -> Path:
    section = cfg.get("comfyui", {})
    python = comfyui_python(
        comfyui_root(cfg), str(section.get("python", "") or "")
    )
    if python is None:
        raise RuntimeError("Python de ComfyUI introuvable.")
    return python


def _node_dir(engine: CaptionEngine, cfg: dict[str, Any]) -> Path | None:
    if not engine.node_folder:
        return None
    app_dir = comfyui_app_dir(comfyui_root(cfg))
    if app_dir is None:
        return None
    return app_dir / "custom_nodes" / engine.node_folder


def _endpoint(cfg: dict[str, Any]) -> str:
    return str(cfg.get("comfyui", {}).get("endpoint", "") or "").rstrip("/")


def node_installed(engine: CaptionEngine, cfg: dict[str, Any]) -> bool:
    if engine.family == "florence":
        return True
    path = _node_dir(engine, cfg)
    return path is not None and path.exists()


def node_loaded(engine: CaptionEngine, cfg: dict[str, Any]) -> bool:
    if engine.family == "florence":
        return True
    endpoint = _endpoint(cfg)
    if not endpoint:
        return False
    try:
        with urllib.request.urlopen(
            f"{endpoint}/object_info/{engine.node_class}", timeout=5
        ) as response:
            data = json.load(response)
        return engine.node_class in data
    except Exception:  # noqa: BLE001
        return False


def vision_ok(cfg: dict[str, Any], *, refresh: bool = False) -> bool:
    python = _python(cfg)
    key = str(python)
    if not refresh and key in _VISION_CACHE:
        return _VISION_CACHE[key]
    code = (
        "from llama_cpp.llama_chat_format import "
        "Qwen3VLChatHandler, Llava15ChatHandler; print('VISION_OK')"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            timeout=40,
        )
        ok = result.returncode == 0 and "VISION_OK" in result.stdout
    except Exception:  # noqa: BLE001
        ok = False
    _VISION_CACHE[key] = ok
    return ok


def clear_vision_cache() -> None:
    _VISION_CACHE.clear()


def engine_status(engine: CaptionEngine, cfg: dict[str, Any]) -> dict[str, Any]:
    if engine.family == "florence":
        return {
            "ready": True,
            "node": True,
            "loaded": True,
            "vision": True,
            "models": True,
            "missing": [],
        }
    node = node_installed(engine, cfg)
    loaded = node_loaded(engine, cfg) if node else False
    vision = vision_ok(cfg)
    models = engine_installed(engine, cfg)
    missing: list[str] = []
    if not node:
        missing.append("node")
    elif not loaded:
        missing.append("restart")
    if not vision:
        missing.append("vision")
    if not models:
        missing.append("models")
    return {
        "ready": node and loaded and vision and models,
        "node": node,
        "loaded": loaded,
        "vision": vision,
        "models": models,
        "missing": missing,
    }


def _merge_json(path: Path, section: str, entries: dict[str, Any]) -> None:
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
    bucket = payload.get(section)
    if not isinstance(bucket, dict):
        bucket = {}
    bucket.update(entries)
    payload[section] = bucket
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def ensure_catalog(engine: CaptionEngine, cfg: dict[str, Any]) -> None:
    node_dir = _node_dir(engine, cfg)
    if node_dir is None:
        return
    catalog = node_dir / "custom_models.json"
    if engine.family == "qwen_vl":
        model_dir = Path(engine.model_dir)
        entry = {
            "author": model_dir.parent.name or "stablecraft",
            "repo_name": model_dir.name,
            "repo_id": engine.model_files[0].repo if engine.model_files else "",
            "model_files": [item.filename for item in engine.model_files],
            "defaults": {"context_length": 8192},
        }
        if engine.mmproj is not None:
            entry["mmproj_file"] = engine.mmproj.filename
        _merge_json(catalog, "gguf_models", {engine.catalog_name: entry})
    elif engine.family == "joycaption":
        item = engine.model_files[0] if engine.model_files else None
        if item is None:
            return
        entry = {
            "name": f"{item.repo}/{item.filename}",
            "description": f"{engine.download_size_gb:.1f} GB - StableCraft",
        }
        _merge_json(catalog, "gguf_models", {engine.catalog_name: entry})


def _file_items(engine: CaptionEngine) -> list[CaptionModelFile]:
    items = list(engine.model_files)
    if engine.mmproj is not None:
        items.append(engine.mmproj)
    return items


def download_engine_models(
    engine: CaptionEngine,
    cfg: dict[str, Any],
    progress: ProgressCallback | None = None,
    cancel: DownloadToken | threading.Event | None = None,
) -> None:
    base = comfy_models_dir(cfg) / engine.model_dir
    base.mkdir(parents=True, exist_ok=True)
    items = _file_items(engine)
    total = sum(item.size for item in items)
    done_base = 0
    for item in items:
        target = base / item.filename
        if target.exists() and target.stat().st_size == item.size:
            done_base += item.size
            if progress is not None:
                progress(done_base, total)
            continue

        def per_file(
            done: int,
            _total: int,
            *,
            base_done: int = done_base,
            item_size: int = item.size,
        ) -> None:
            if progress is not None:
                progress(base_done + min(done, item_size), total)

        download_file(
            model_url(item),
            target,
            expected_sha256=item.sha256 or None,
            progress=per_file,
            cancel=cancel,
        )
        done_base += item.size
        if progress is not None:
            progress(done_base, total)


def restart_comfyui(
    cfg: dict[str, Any],
    status: StatusCallback | None = None,
) -> None:
    if not comfyui_manageable(cfg):
        raise RuntimeError(
            "ComfyUI est géré en externe. Redémarre-le depuis son lanceur."
        )
    if status is not None:
        status("Arrêt de ComfyUI…")
    stop_comfyui(cfg)
    if status is not None:
        status("Redémarrage de ComfyUI…")
    start_comfyui(cfg)
    if not wait_for_comfyui(cfg, 240):
        raise RuntimeError("ComfyUI n'a pas redémarré dans les 4 minutes.")


def install_vision(
    cfg: dict[str, Any],
    progress: ProgressCallback | None = None,
    cancel: DownloadToken | threading.Event | None = None,
    status: StatusCallback | None = None,
) -> bool:
    """Install the JamePeng vision wheel if needed. Returns True if installed."""
    if vision_ok(cfg):
        return False
    python = _python(cfg)
    try:
        version_text = subprocess.check_output(
            [
                str(python),
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
            ],
            text=True,
        ).strip()
        major, minor = (int(part) for part in version_text.split(".", 1))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Version de Python ComfyUI illisible : {exc}") from exc
    if not (
        os.name == "nt"
        and platform.machine().lower() in {"amd64", "x86_64"}
        and llama_cpp_wheel((major, minor)) is not None
    ):
        raise RuntimeError(
            "Le wheel vision automatique est prévu pour Windows x64 avec "
            f"Python 3.10–3.14 (ComfyUI utilise Python {major}.{minor}). "
            "Suis le guide du node pour ta plateforme : "
            "https://github.com/1038lab/ComfyUI-QwenVL/blob/main/docs/"
            "LLAMA_CPP_PYTHON_VISION_INSTALL.md"
        )
    wheel_url, wheel_sha, wheel_size = llama_cpp_wheel((major, minor))  # type: ignore[misc]
    wheel_name = wheel_url.rsplit("/", 1)[-1].replace("%2B", "+")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    wheel = CACHE_DIR / wheel_name
    if not (wheel.exists() and wheel.stat().st_size == wheel_size):
        if status is not None:
            status(f"Téléchargement du backend vision ({wheel_size / 1e6:.0f} Mo)…")
        download_file(
            wheel_url,
            wheel,
            expected_sha256=wheel_sha,
            progress=progress,
            cancel=cancel,
        )
    stopped = False
    try:
        if comfyui_manageable(cfg):
            if status is not None:
                status("Arrêt de ComfyUI pour installer le backend vision…")
            stop_comfyui(cfg)
            stopped = True
        elif wait_port("127.0.0.1", endpoint_port(cfg), 0.5):
            raise RuntimeError(
                "ComfyUI tourne mais StableCraft ne le gère pas "
                "([comfyui] manage = false). Arrête-le depuis son lanceur, "
                "puis relance l'installation du backend vision."
            )
        if status is not None:
            status("Installation du backend vision…")
        # llama-cpp-python needs diskcache, which the embedded Python may not
        # have.  Install it separately so we can keep --no-deps and avoid
        # upgrading numpy/Pillow behind ComfyUI's back.
        subprocess.run(
            [str(python), "-m", "pip", "install", "diskcache"],
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--force-reinstall",
                "--no-deps",
                str(wheel),
            ],
            capture_output=True,
            text=True,
        )
        # The node requirements can pull numpy 2.5, which breaks numba/was-ns.
        # Pin it back while ComfyUI is stopped.
        subprocess.run(
            [str(python), "-m", "pip", "install", "numpy<2.3"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            raise RuntimeError(
                "Installation du backend vision impossible : "
                + (detail[-1] if detail else str(result.returncode))
            )
        clear_vision_cache()
        if not vision_ok(cfg, refresh=True):
            raise RuntimeError(
                "Le wheel installé ne contient pas les handlers vision. "
                "Consulte le guide d'installation du node."
            )
        return True
    finally:
        if stopped:
            if status is not None:
                status("Redémarrage de ComfyUI…")
            try:
                start_comfyui(cfg)
                wait_for_comfyui(cfg, 240)
            except Exception:  # noqa: BLE001
                pass


def install_engine(
    engine: CaptionEngine,
    cfg: dict[str, Any],
    progress: ProgressCallback | None = None,
    cancel: DownloadToken | threading.Event | None = None,
    status: StatusCallback | None = None,
) -> str:
    if engine.family == "florence":
        return "Florence-2 est déjà fourni par comfyui-florence2."

    def note(message: str) -> None:
        if status is not None:
            status(message)

    note(f"Installation du node {engine.node_folder}…")
    install_custom_node(
        cfg,
        engine.node_folder,
        progress=progress,
        cancel=cancel,
    )
    note("Configuration du catalogue de modèles…")
    ensure_catalog(engine, cfg)
    note(f"Téléchargement du modèle ({engine.download_size_gb:.1f} Go)…")
    download_engine_models(engine, cfg, progress=progress, cancel=cancel)

    install_vision(cfg, progress=progress, cancel=cancel, status=status)
    if node_loaded(engine, cfg):
        return "Moteur installé et prêt."
    if comfyui_manageable(cfg):
        restart_comfyui(cfg, status=status)
        if node_loaded(engine, cfg):
            return "Moteur installé et prêt."
        raise RuntimeError(
            f"{engine.node_class} n'est pas chargé après le redémarrage. "
            "Vérifie le journal ComfyUI."
        )
    note("Node et modèle installés. Redémarre ComfyUI pour le charger.")
    return "Installation terminée. Redémarre ComfyUI."
