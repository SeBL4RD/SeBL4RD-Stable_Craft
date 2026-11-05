"""Grab an image from the system clipboard.

Run with ComfyUI's Python (Pillow is available there); the Tkinter UI itself
has no Pillow dependency.  On Windows/macOS Pillow's ImageGrab handles the
clipboard.  On Linux we use wl-paste (Wayland) or xclip (X11), including
copied files and image MIME types.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageGrab

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
MIME_PRIORITY = ("image/png", "image/jpeg", "image/webp", "image/bmp")


def _existing_image(path: str | Path) -> Path | None:
    candidate = Path(str(path)).expanduser()
    if candidate.exists() and candidate.suffix.lower() in IMAGE_SUFFIXES:
        return candidate
    return None


def _from_file_list(items: list[Any]) -> Path | None:
    for item in items:
        if isinstance(item, (str, os.PathLike)):
            found = _existing_image(str(item))
            if found is not None:
                return found
    return None


def _grab_windows_macos() -> tuple[Image.Image | None, Path | None]:
    data = ImageGrab.grabclipboard()
    if isinstance(data, Image.Image):
        return data, None
    if isinstance(data, list):
        return None, _from_file_list(data)
    return None, None


def _run(command: list[str], *, text: bool = False) -> bytes | str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=10,
            text=text,
        )
    except Exception:  # noqa: BLE001
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _linux_clipboard_image() -> tuple[Image.Image | None, Path | None]:
    # Wayland first when available.
    if shutil.which("wl-paste"):
        types_raw = _run(["wl-paste", "--list-types"], text=True)
        types = str(types_raw or "").splitlines()
        for mime in MIME_PRIORITY:
            if mime in types:
                payload = _run(["wl-paste", "--no-newline", "--type", mime])
                if isinstance(payload, bytes) and payload:
                    try:
                        import io

                        return Image.open(io.BytesIO(payload)).copy(), None
                    except Exception:  # noqa: BLE001
                        pass
        for mime in ("text/uri-list", "text/plain"):
            if mime in types:
                raw = _run(["wl-paste", "--no-newline", "--type", mime], text=True)
                found = _path_from_text(str(raw or ""))
                if found is not None:
                    return None, found

    if shutil.which("xclip"):
        targets_raw = _run(
            ["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"], text=True
        )
        targets = str(targets_raw or "").splitlines()
        for mime in MIME_PRIORITY:
            if mime in targets:
                payload = _run(
                    ["xclip", "-selection", "clipboard", "-t", mime, "-o"]
                )
                if isinstance(payload, bytes) and payload:
                    try:
                        import io

                        return Image.open(io.BytesIO(payload)).copy(), None
                    except Exception:  # noqa: BLE001
                        pass
        for mime in ("text/uri-list", "text/plain"):
            if mime in targets:
                raw = _run(
                    ["xclip", "-selection", "clipboard", "-t", mime, "-o"],
                    text=True,
                )
                found = _path_from_text(str(raw or ""))
                if found is not None:
                    return None, found

    # X11 fallback without xclip: Pillow's ImageGrab may still work on some
    # builds, and xsel can expose text paths.
    try:
        data = ImageGrab.grabclipboard()
        if isinstance(data, Image.Image):
            return data, None
        if isinstance(data, list):
            found = _from_file_list(data)
            if found is not None:
                return None, found
    except Exception:  # noqa: BLE001
        pass

    if shutil.which("xsel"):
        raw = _run(["xsel", "--clipboard", "--output"], text=True)
        found = _path_from_text(str(raw or ""))
        if found is not None:
            return None, found
    return None, None


def _path_from_text(text: str) -> Path | None:
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("file://"):
            from urllib.parse import unquote, urlparse

            parsed = urlparse(line)
            found = _existing_image(unquote(parsed.path))
            if found is not None:
                return found
        # Some file managers put a plain path on the clipboard.
        found = _existing_image(line.strip('"').strip("'"))
        if found is not None:
            return found
    return None


def grab(destination: Path) -> dict[str, Any]:
    if os.name == "nt" or sys.platform == "darwin":
        image, source = _grab_windows_macos()
    else:
        image, source = _linux_clipboard_image()

    if source is not None:
        with Image.open(source) as opened:
            width, height = opened.size
        return {"path": str(source), "source": "file", "width": width, "height": height}

    if image is None:
        raise RuntimeError(
            "Le presse-papiers ne contient pas d'image. "
            "Copie une image, ou choisis un fichier."
        )

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    image.save(destination, "PNG")
    return {
        "path": str(destination),
        "source": "clipboard",
        "width": image.width,
        "height": image.height,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Grab an image from the clipboard")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        info = grab(args.output)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
