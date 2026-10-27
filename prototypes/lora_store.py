"""LoRA data layer for StableCraft.

This module is Tk-free: it reads the ComfyUI LoRA Manager API, inspects
safetensors headers and stores the per-profile LoRA selection in
``user/lora_settings.json``. The UI lives in ``lora_manager.py``.
"""

from __future__ import annotations

import hashlib
import json
import struct
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "user" / "lora_settings.json"
PREVIEW_CACHE_DIR = ROOT / "user" / "cache" / "lora_previews"

MAX_LORAS = 10
PREVIEW_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif")

# Families accepted by each profile. The strings are matched against the
# normalized safetensors metadata (modelspec.architecture / ss_base_model_version).
PROFILE_FAMILIES: dict[str, set[str]] = {
    "flux3_klein": {"flux3"},
    "flux2_klein_9b": {"flux2_klein", "flux2"},
    "krea2_general_edit": {"krea2"},
    "krea2_edit": {"krea2"},
    "qwen_image_21": {"qwen_image"},
}

KNOWN_FAMILIES = {
    "flux3",
    "flux2_klein",
    "flux2",
    "flux1",
    "krea2",
    "qwen_image",
    "zimage",
    "sdxl",
    "sd15",
}

FAMILY_LABELS = {
    "flux3": "FLUX.3",
    "flux2_klein": "FLUX.2 Klein",
    "flux2": "FLUX.2",
    "flux1": "FLUX.1",
    "krea2": "Krea 2",
    "qwen_image": "Qwen Image",
    "zimage": "Z-Image",
    "sdxl": "SDXL",
    "sd15": "SD 1.5",
}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def _empty_settings() -> dict[str, Any]:
    return {"version": 1, "enabled": True, "profiles": {}}


def load_settings(path: Path | None = None) -> dict[str, Any]:
    target = path or SETTINGS_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/damaged state is not fatal
        return _empty_settings()
    if not isinstance(data, dict):
        return _empty_settings()
    data.setdefault("version", 1)
    data["enabled"] = bool(data.get("enabled", True))
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        data["profiles"] = {}
    return data


def save_settings(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or SETTINGS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(target)


def clamp_strength(value: object) -> float:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, number))


def normalize_item(item: object) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    label = str(item.get("label") or Path(name).name or name).strip() or name
    folder = str(item.get("folder") or "").strip()
    arch = str(item.get("arch") or "").strip()
    result: dict[str, Any] = {
        "name": name,
        "label": label,
        "folder": folder,
        "arch": arch,
        "strength": clamp_strength(item.get("strength", 1.0)),
        "enabled": bool(item.get("enabled", True)),
    }
    if item.get("has_text_encoder"):
        result["has_text_encoder"] = True
    return result


def profile_items(settings: dict[str, Any], profile: str) -> list[dict[str, Any]]:
    raw = settings.get("profiles", {}).get(profile, [])
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in raw[:MAX_LORAS]:
        normalized = normalize_item(entry)
        if normalized is not None:
            items.append(normalized)
    return items


def set_profile_items(
    settings: dict[str, Any], profile: str, items: list[dict[str, Any]]
) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for entry in items[:MAX_LORAS]:
        value = normalize_item(entry)
        if value is not None:
            normalized.append(value)
    profiles = settings.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
        settings["profiles"] = profiles
    profiles[profile] = normalized
    return settings


def active_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if bool(item.get("enabled", True)) and clamp_strength(item.get("strength", 0.0)) > 0:
            values.append(item)
    return values


def signature(items: list[dict[str, Any]]) -> str:
    parts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").casefold()
        strength = clamp_strength(item.get("strength", 1.0))
        parts.append(f"{name}@{strength:.2f}")
    return "|".join(parts)


# ---------------------------------------------------------------------------
# LoRA Manager API
# ---------------------------------------------------------------------------


class LoraApiError(RuntimeError):
    pass


class LoraApi:
    """Minimal client for the ComfyUI LoRA Manager custom node."""

    def __init__(self, endpoint: str, timeout: float = 10.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def _get_json(self, path: str, timeout: float | None = None) -> Any:
        url = self.endpoint + path
        try:
            with urllib.request.urlopen(url, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise LoraApiError(str(exc)) from exc

    def list_loras(
        self, page: int = 1, page_size: int = 40, search: str = ""
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "page": max(1, int(page)),
            "page_size": max(1, min(100, int(page_size))),
            "sort_by": "name",
        }
        term = search.strip()
        if term:
            query["search"] = term
        data = self._get_json("/api/lm/loras/list?" + urllib.parse.urlencode(query))
        if not isinstance(data, dict) or "items" not in data:
            raise LoraApiError("Réponse LoRA Manager invalide")
        return data

    def relative_paths(self, search: str, limit: int = 100) -> list[str]:
        query = urllib.parse.urlencode(
            {"search": search, "limit": max(1, min(100, int(limit)))}
        )
        data = self._get_json("/api/lm/loras/relative-paths?" + query)
        values = data.get("relative_paths", []) if isinstance(data, dict) else []
        return [str(value) for value in values]

    def comfy_names(self) -> list[str]:
        data = self._get_json("/object_info/LoraLoaderModelOnly", timeout=15.0)
        try:
            options = data["LoraLoaderModelOnly"]["input"]["required"]["lora_name"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise LoraApiError("Nœud LoraLoaderModelOnly introuvable") from exc
        if not isinstance(options, list):
            return []
        return [str(value) for value in options]

    def page_url(self) -> str:
        return self.endpoint + "/loras"


# ---------------------------------------------------------------------------
# Safetensors / GGUF metadata
# ---------------------------------------------------------------------------


_ARCH_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}


def normalize_family(value: str) -> str:
    raw = str(value or "").lower()
    normalized = raw.replace("-", "_").replace(" ", "_").replace(".", "_")
    if "flux3" in normalized or "flux_3" in normalized:
        return "flux3"
    if "flux2_klein" in normalized or "flux_klein_9b" in normalized:
        return "flux2_klein"
    if "flux2" in normalized:
        return "flux2"
    if "krea2" in normalized or "krea_2" in normalized:
        return "krea2"
    if "qwen_image" in normalized or "qwenimage" in normalized:
        return "qwen_image"
    if "flux1" in normalized or "flux_1" in normalized:
        return "flux1"
    if "zimage" in normalized or "z_image" in normalized:
        return "zimage"
    if "sdxl" in normalized or "stable_diffusion_xl" in normalized:
        return "sdxl"
    if "sd15" in normalized or "sd_1_5" in normalized or "stable_diffusion_v1" in normalized:
        return "sd15"
    return normalized


def family_label(family: str) -> str:
    value = str(family or "")
    return FAMILY_LABELS.get(value, value or "?")


def compatibility(profile: str, family: str) -> str:
    value = str(family or "")
    if not value:
        return "unknown"
    accepted = PROFILE_FAMILIES.get(profile, set())
    if value in accepted:
        return "compatible"
    for candidate in accepted:
        if candidate in value or value in candidate:
            return "compatible"
    if value in KNOWN_FAMILIES:
        return "incompatible"
    return "unknown"


def _read_safetensors_header(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        head = handle.read(8)
        if len(head) != 8:
            return {}
        size = struct.unpack("<Q", head)[0]
        if size <= 0 or size > 5_000_000:
            return {}
        raw = handle.read(size)
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def read_lora_arch(path: str | Path) -> dict[str, Any]:
    """Return ``{architecture, family, has_text_encoder}`` for a LoRA file.

    Only the header is read; no tensor is loaded. Results are cached by
    (path, mtime, size).
    """
    file_path = Path(path)
    try:
        stat = file_path.stat()
    except OSError:
        return {}
    key = (str(file_path), int(stat.st_mtime_ns), int(stat.st_size))
    cached = _ARCH_CACHE.get(key)
    if cached is not None:
        return cached

    architecture = ""
    has_text_encoder = False
    suffix = file_path.suffix.lower()

    if suffix in {".safetensors", ".sft"}:
        try:
            header = _read_safetensors_header(file_path)
        except OSError:
            header = {}
        metadata = header.get("__metadata__", {})
        if isinstance(metadata, dict):
            architecture = str(
                metadata.get("modelspec.architecture")
                or metadata.get("ss_base_model_version")
                or ""
            ).strip()
        has_text_encoder = any(
            str(name).startswith(("lora_te", "text_encoder", "lora_te1", "lora_te2"))
            for name in header
            if name != "__metadata__"
        )
    elif suffix == ".gguf":
        try:
            from models_tools import gguf_architecture  # noqa: PLC0415

            architecture = str(gguf_architecture(file_path) or "").strip()
        except Exception:  # noqa: BLE001
            architecture = ""

    result = {
        "architecture": architecture,
        "family": normalize_family(architecture),
        "has_text_encoder": has_text_encoder,
    }
    _ARCH_CACHE[key] = result
    return result


def find_preview_file(path: str | Path) -> str:
    file_path = Path(path)
    for suffix in PREVIEW_SUFFIXES:
        candidate = file_path.with_suffix(suffix)
        if candidate.is_file():
            return str(candidate)
    for suffix in PREVIEW_SUFFIXES:
        candidate = file_path.with_name(file_path.stem + ".preview" + suffix)
        if candidate.is_file():
            return str(candidate)
    return ""


def preview_cache_key(item: dict[str, Any]) -> str:
    source = str(
        item.get("preview_url")
        or item.get("preview_file")
        or ""
    )
    if not source:
        return ""
    seed = "|".join(
        [
            str(item.get("file_path") or item.get("name") or ""),
            str(item.get("modified") or ""),
            source,
        ]
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def preview_cache_path(key: str) -> Path:
    return PREVIEW_CACHE_DIR / f"{key}.png"


def _match_comfy_name(
    candidate: str, basename: str, comfy_names: list[str]
) -> str:
    if not comfy_names:
        return candidate
    lookup = {str(name).casefold(): str(name) for name in comfy_names}
    for value in (
        candidate,
        candidate.replace("/", "\\"),
        candidate.replace("\\", "/"),
        basename,
    ):
        found = lookup.get(value.casefold())
        if found:
            return found
    matches = [
        str(name)
        for name in comfy_names
        if Path(str(name).replace("\\", "/")).name.casefold() == basename.casefold()
    ]
    if len(matches) == 1:
        return matches[0]
    return candidate


def normalize_api_item(
    item: dict[str, Any], comfy_names: list[str] | None = None
) -> dict[str, Any] | None:
    """Convert one /api/lm/loras/list item into StableCraft's shape."""
    if not isinstance(item, dict):
        return None
    file_path = str(item.get("file_path") or "").strip()
    raw_name = str(item.get("file_name") or "").strip()
    if not file_path and not raw_name:
        return None
    basename = Path(file_path).name if file_path else raw_name
    folder = str(item.get("folder") or "").strip().replace("\\", "/")
    candidate_folder = folder.replace("/", "\\")
    candidate = f"{candidate_folder}\\{basename}" if candidate_folder else basename
    comfy_name = _match_comfy_name(candidate, basename, list(comfy_names or []))

    arch_info = read_lora_arch(file_path) if file_path else {}
    preview_url = str(item.get("preview_url") or "").strip()
    preview_file = find_preview_file(file_path) if file_path else ""

    result: dict[str, Any] = {
        "name": comfy_name,
        "label": basename,
        "folder": folder,
        "arch": str(arch_info.get("family") or ""),
        "architecture": str(arch_info.get("architecture") or ""),
        "has_text_encoder": bool(arch_info.get("has_text_encoder")),
        "strength": 1.0,
        "enabled": True,
        "file_path": file_path,
        "preview_url": preview_url,
        "preview_file": preview_file,
        "modified": item.get("modified") or 0,
    }
    return result
