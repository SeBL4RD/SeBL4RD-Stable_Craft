"""Model locations, downloads, node installation and ComfyUI restarts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from app_meta import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
USER_DIR = ROOT / "user"
CACHE_DIR = USER_DIR / "cache"
SELECTION_PATH = USER_DIR / "model_selection.json"

KREA_NODE_REPO = "lbouaraba/comfyui-krea2edit"
KREA_NODE_DIR = "comfyui-krea2edit"
KREA_NODE_API = f"https://api.github.com/repos/{KREA_NODE_REPO}/releases/latest"

FOLDER_FOR_KIND = {
    "unet": "unet",
    "lora": "loras",
    "text_encoder": "text_encoders",
    "vae": "vae",
}

KIND_LABELS = {
    "unet": "UNet",
    "lora": "LoRA",
    "text_encoder": "Text encoder",
    "vae": "VAE",
    "node": "Custom node",
}

_QUANT_SUFFIX = re.compile(
    r"(?i)(?:[-_.](?:q\d+[a-z0-9]*(?:[_-][a-z0-9]+)*|bf16|fp16|fp32|"
    r"f16|f32|fp8(?:[_-][a-z0-9]+)*|w4a8|w8a8|int8|int4))$"
)


def model_family_key(value: object) -> str:
    """Strip a quantization suffix so Q4/Q8 variants share one family."""
    stem = Path(str(value or "").replace("\\", "/")).stem
    while True:
        stripped = _QUANT_SUFFIX.sub("", stem)
        if stripped == stem:
            break
        stem = stripped
    return stem.casefold()


def quantization_label(value: object) -> str:
    stem = Path(str(value or "").replace("\\", "/")).stem
    match = _QUANT_SUFFIX.search(stem)
    return match.group(0).lstrip("-_. ") if match else ""


def same_model_file(left: object, right: object) -> bool:
    return (
        Path(str(left or "").replace("\\", "/")).name.casefold()
        == Path(str(right or "").replace("\\", "/")).name.casefold()
    )


def human_size(size: int | None) -> str:
    if not size:
        return "?"
    from i18n import current_language  # noqa: PLC0415

    units = (
        ("o", "Ko", "Mo", "Go", "To")
        if current_language() == "fr"
        else ("B", "KB", "MB", "GB", "TB")
    )
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == units[0] else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} {units[-1]}"


# ---------------------------------------------------------------------------
# Selection persisted outside config.toml
# ---------------------------------------------------------------------------


def _read_selection() -> dict[str, Any]:
    try:
        data = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing or damaged state is not fatal
        return {"version": 1, "profiles": {}}
    if not isinstance(data, dict):
        return {"version": 1, "profiles": {}}
    data.setdefault("version", 1)
    data.setdefault("profiles", {})
    return data


def selected_file(profile: str, kind: str) -> str | None:
    data = _read_selection()
    value = data.get("profiles", {}).get(profile, {}).get(kind)
    return str(value) if value else None


def set_selected_file(profile: str, kind: str, filename: str | None) -> None:
    data = _read_selection()
    profiles = data.setdefault("profiles", {})
    entry = profiles.setdefault(profile, {})
    if filename:
        entry[kind] = filename
    else:
        entry.pop(kind, None)
    SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SELECTION_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def resolve_filename(
    profile: str,
    kind: str,
    pcfg: dict[str, Any],
    profile_manifest: dict[str, Any],
) -> str:
    spec = (profile_manifest.get("files") or {}).get(kind, {})
    configured = pcfg.get(kind)
    fallback = Path(str(configured)).name if configured else str(spec.get("filename", ""))
    return selected_file(profile, kind) or fallback


def download_options(
    profile: str, kind: str, profile_manifest: dict[str, Any], current: str
) -> list[dict[str, Any]]:
    spec = (profile_manifest.get("files") or {}).get(kind, {})
    quantizations = spec.get("quantizations")
    if not quantizations and kind == "unet":
        quantizations = profile_manifest.get("quantizations")
    if quantizations:
        options = [dict(item) for item in quantizations]
    elif spec.get("download_url"):
        options = [dict(spec)]
    else:
        options = []

    for item in options:
        item.setdefault("label", str(item.get("filename", "?")))
        item["is_current"] = str(item.get("filename")) == current
    options.sort(key=lambda item: (not item["is_current"], item["label"]))
    return options


# ---------------------------------------------------------------------------
# Files and downloads
# ---------------------------------------------------------------------------


_GGUF_SCALARS = {
    0: "<B",
    1: "<b",
    2: "<H",
    3: "<h",
    4: "<I",
    5: "<i",
    6: "<f",
    7: "<B",
    10: "<Q",
    11: "<q",
    12: "<d",
}


def _gguf_read_string(handle: Any) -> str:
    length = struct.unpack("<Q", handle.read(8))[0]
    if length > 4_000_000:
        raise ValueError("GGUF string metadata is unreasonably large")
    return handle.read(length).decode("utf-8", errors="replace")


def _gguf_skip_value(handle: Any, value_type: int) -> str | None:
    if value_type == 8:
        return _gguf_read_string(handle)
    if value_type == 9:
        element_type = struct.unpack("<I", handle.read(4))[0]
        count = struct.unpack("<Q", handle.read(8))[0]
        for _ in range(count):
            _gguf_skip_value(handle, element_type)
        return None
    fmt = _GGUF_SCALARS.get(value_type)
    if fmt is None:
        raise ValueError(f"unknown GGUF value type {value_type}")
    handle.read(struct.calcsize(fmt))
    return None


def gguf_architecture(path: Path) -> str | None:
    """Read general.architecture from a GGUF header without loading weights.

    Returns None when the file is not a readable GGUF or when the metadata is
    missing (notably some Unsloth Qwen Image conversions).
    """
    try:
        with path.open("rb") as handle:
            if handle.read(4) != b"GGUF":
                return None
            version = struct.unpack("<I", handle.read(4))[0]
            if version < 1:
                return None
            handle.read(8)  # tensor count
            kv_count = struct.unpack("<Q", handle.read(8))[0]
            for _ in range(min(kv_count, 4096)):
                key = _gguf_read_string(handle)
                value_type = struct.unpack("<I", handle.read(4))[0]
                value = _gguf_skip_value(handle, value_type)
                if key == "general.architecture":
                    return value
    except (OSError, struct.error, ValueError, UnicodeDecodeError):
        return None
    return None


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    url: str,
    destination: Path,
    *,
    expected_sha256: str | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        url, headers={"User-Agent": f"StableCraft/{APP_VERSION} model manager"}
    )
    digest = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, part.open("wb") as f:
            total = int(response.headers.get("Content-Length", "0") or 0)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
        actual = digest.hexdigest()
        if expected_sha256 and actual.lower() != expected_sha256.lower():
            raise ValueError(
                f"SHA256 incorrect pour {destination.name}\n"
                f"attendu : {expected_sha256}\nobtenu  : {actual}"
            )
        part.replace(destination)
        return destination
    except Exception:
        try:
            part.unlink()
        except OSError:
            pass
        raise


def copy_file(
    source: Path,
    destination: Path,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = source.stat().st_size
    done = 0
    part = destination.with_suffix(destination.suffix + ".part")
    try:
        with source.open("rb") as src, part.open("wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
        part.replace(destination)
        return destination
    except Exception:
        try:
            part.unlink()
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# ComfyUI paths and restart
# ---------------------------------------------------------------------------


_AUTO_COMFY_ROOT: Path | None = None
_AUTO_COMFY_ROOT_DONE = False


def comfyui_root(cfg: dict[str, Any]) -> Path | None:
    global _AUTO_COMFY_ROOT, _AUTO_COMFY_ROOT_DONE

    section = cfg.get("comfyui", {})
    value = str(section.get("root", "") or "")
    if value:
        root = Path(value)
        return root if root.exists() else None

    # Allow a manual config that only sets the embedded Python or the launcher.
    python_value = str(section.get("python", "") or "")
    if python_value:
        python_path = Path(python_value)
        if (
            python_path.exists()
            and python_path.parent.name.lower() == "python_embeded"
        ):
            root = python_path.parent.parent
            if root.exists():
                return root
    start_value = str(section.get("start_command", "") or "")
    if start_value:
        start = Path(start_value)
        if start.exists():
            root = start.parent
            if root.exists():
                return root

    # Last resort: reuse the launcher's auto-detection when config.toml leaves
    # the ComfyUI paths empty. Cache it: the UI and model manager call this often.
    if _AUTO_COMFY_ROOT_DONE:
        return _AUTO_COMFY_ROOT
    _AUTO_COMFY_ROOT_DONE = True
    try:
        from launcher import find_comfyui  # noqa: PLC0415

        _start, _python, root, error = find_comfyui(cfg)
        _AUTO_COMFY_ROOT = root if error is None else None
    except Exception:  # noqa: BLE001
        _AUTO_COMFY_ROOT = None
    return _AUTO_COMFY_ROOT


def extra_model_paths_path(cfg: dict[str, Any]) -> Path | None:
    root = comfyui_root(cfg)
    if root is None:
        return None
    return root / "ComfyUI" / "extra_model_paths.yaml"


def ensure_store_dirs(cfg: dict[str, Any]) -> Path:
    value = str(cfg.get("models", {}).get("store_dir", "") or "")
    store = Path(value) if value else ROOT / "models"
    if not store.is_absolute():
        store = ROOT / store
    for folder in ("unet", "text_encoders", "vae", "loras"):
        (store / folder).mkdir(parents=True, exist_ok=True)
    return store


def ensure_extra_model_paths(cfg: dict[str, Any]) -> tuple[bool, str | None]:
    path = extra_model_paths_path(cfg)
    if path is None:
        return False, "Dossier ComfyUI introuvable."
    store = ensure_store_dirs(cfg)

    try:
        existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    except OSError as exc:
        return False, str(exc)
    if re.search(r"(?m)^stablecraft\s*:", existing):
        return False, None

    base = store.resolve().as_posix()
    section = (
        "\n# StableCraft — managed by the model manager\n"
        "stablecraft:\n"
        f'    base_path: "{base}"\n'
        "    unet: unet\n"
        "    diffusion_models: unet\n"
        "    text_encoders: text_encoders\n"
        "    clip: text_encoders\n"
        "    vae: vae\n"
        "    loras: loras\n"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(section)
    except OSError as exc:
        return False, str(exc)
    return True, None


def endpoint_port(cfg: dict[str, Any]) -> int:
    endpoint = str(cfg.get("comfyui", {}).get("endpoint", "http://127.0.0.1:8188"))
    parsed = urllib.parse.urlparse(endpoint)
    return parsed.port or 8188


def stop_comfyui(cfg: dict[str, Any]) -> None:
    port = endpoint_port(cfg)
    command = (
        "$p = Get-NetTCPConnection -LocalPort "
        f"{port} -State Listen -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty OwningProcess -Unique; "
        "if ($p) { $p | ForEach-Object { Stop-Process -Id $_ -Force } }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
    )


def start_comfyui(cfg: dict[str, Any]) -> subprocess.Popen[Any]:
    section = cfg.get("comfyui", {})
    root = comfyui_root(cfg)
    if root is None:
        raise RuntimeError("Dossier ComfyUI introuvable.")
    start_value = str(section.get("start_command", "") or "")
    command = Path(start_value) if start_value else root / "run_nvidia_gpu.bat"
    if not command.exists():
        raise RuntimeError(f"Lanceur ComfyUI introuvable : {command}")

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from launcher import comfyui_launch_command  # noqa: PLC0415

        launch = comfyui_launch_command(command, cfg)
    except Exception:  # noqa: BLE001
        launch = command
    return subprocess.Popen(
        ["cmd", "/c", str(launch)],
        cwd=str(command.parent),
        creationflags=0x00000010 if os.name == "nt" else 0,
    )


def wait_for_comfyui(cfg: dict[str, Any], timeout: float = 240.0) -> bool:
    endpoint = str(cfg.get("comfyui", {}).get("endpoint", "http://127.0.0.1:8188")).rstrip("/")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            request = urllib.request.Request(
                endpoint + "/system_stats", headers={"User-Agent": "StableCraft"}
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                if response.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0)
    return False


# ---------------------------------------------------------------------------
# Krea 2 custom node
# ---------------------------------------------------------------------------


def krea_node_path(cfg: dict[str, Any]) -> Path | None:
    root = comfyui_root(cfg)
    if root is None:
        return None
    return root / "ComfyUI" / "custom_nodes" / KREA_NODE_DIR


def _read_node_version(path: Path) -> str | None:
    pyproject = path / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
        return str(data.get("project", {}).get("version", "") or "") or None
    except Exception:  # noqa: BLE001
        init = path / "__init__.py"
        try:
            text = init.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)', text)
        return match.group(1) if match else None


def version_tuple(value: str | None) -> tuple[int, ...]:
    parts: list[int] = []
    for part in str(value or "").lstrip("v").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts)


def latest_krea_release() -> dict[str, Any] | None:
    request = urllib.request.Request(
        KREA_NODE_API, headers={"User-Agent": f"StableCraft/{APP_VERSION} node installer"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except Exception:  # noqa: BLE001
        data = {}
    tag = str(data.get("tag_name", "") or "")
    if tag:
        version = tag.lstrip("v")
        return {
            "tag": tag,
            "version": version,
            "zip_url": f"https://github.com/{KREA_NODE_REPO}/archive/refs/tags/{tag}.zip",
            "notes": str(data.get("body", "") or ""),
            "html_url": str(data.get("html_url", "") or ""),
        }

    # GitHub API unavailable (offline/rate limit): fall back to the main branch.
    raw = (
        f"https://raw.githubusercontent.com/{KREA_NODE_REPO}/main/pyproject.toml"
    )
    try:
        request = urllib.request.Request(
            raw, headers={"User-Agent": f"StableCraft/{APP_VERSION} node installer"}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            text = response.read().decode("utf-8", errors="replace")
        match = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)', text)
        version = match.group(1) if match else "main"
    except Exception:  # noqa: BLE001
        return None
    return {
        "tag": "main",
        "version": version,
        "zip_url": f"https://github.com/{KREA_NODE_REPO}/archive/refs/heads/main.zip",
        "notes": "",
        "html_url": f"https://github.com/{KREA_NODE_REPO}",
    }


def krea_node_status(cfg: dict[str, Any], latest: dict[str, Any] | None = None) -> dict[str, Any]:
    path = krea_node_path(cfg)
    installed = _read_node_version(path) if path and path.exists() else None
    if latest is None:
        latest = latest_krea_release()
    latest_version = str(latest.get("version", "")) if latest else ""
    needs_install = installed is None
    needs_update = bool(
        installed
        and latest_version
        and version_tuple(latest_version) > version_tuple(installed)
    )
    return {
        "path": path,
        "installed": installed,
        "latest": latest_version,
        "tag": str(latest.get("tag", "")) if latest else "",
        "zip_url": str(latest.get("zip_url", "")) if latest else "",
        "needs_install": needs_install,
        "needs_update": needs_update,
        "ok": not (needs_install or needs_update),
    }


def install_krea_node(
    cfg: dict[str, Any],
    latest: dict[str, Any],
    progress: Callable[[int, int], None] | None = None,
) -> str:
    destination = krea_node_path(cfg)
    if destination is None:
        raise RuntimeError("Dossier custom_nodes introuvable.")
    zip_url = str(latest.get("zip_url", "") or "")
    if not zip_url:
        raise RuntimeError("Archive du nœud Krea 2 introuvable.")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive = CACHE_DIR / f"krea2edit-{latest.get('tag', 'latest')}.zip"
    download_file(zip_url, archive, progress=progress)

    temp_dir = Path(tempfile.mkdtemp(prefix="stablecraft-node-", dir=str(CACHE_DIR)))
    try:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(temp_dir)
        candidates = [p for p in temp_dir.iterdir() if p.is_dir()]
        root = candidates[0] if candidates else None
        if root is None or not (root / "pyproject.toml").exists():
            raise RuntimeError("L'archive du nœud Krea 2 est invalide.")

        backup: Path | None = None
        if destination.exists():
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            backup = CACHE_DIR / (
                f"{destination.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
            )
            shutil.move(str(destination), str(backup))
        try:
            shutil.copytree(root, destination)
        except Exception:
            if destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            if backup is not None and backup.exists():
                shutil.move(str(backup), str(destination))
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
        return _read_node_version(destination) or str(latest.get("version", "?"))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        try:
            archive.unlink()
        except OSError:
            pass


def wait_port(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
