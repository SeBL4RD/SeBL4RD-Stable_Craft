"""Normalize a StableCraft reference image with Pillow.

Called by the Tkinter UI through ComfyUI's embedded Python, and imported by
the bridge to keep reference files consistent. The UI has no Pillow dependency.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageOps

MAX_SIDE = 2048
THUMB_SIDE = 256


def normalize_reference(source: Path, image_path: Path, thumb_path: Path) -> dict[str, object]:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        has_alpha = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        if has_alpha:
            rgba = image.convert("RGBA")
            rgb = Image.new("RGB", rgba.size, (255, 255, 255))
            rgb.paste(rgba, mask=rgba.getchannel("A"))
            image = rgb
        else:
            image = image.convert("RGB")
        if max(image.size) > MAX_SIDE:
            image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        image.load()

        image_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(image_path, "PNG")
        thumb = image.copy()
        thumb.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.LANCZOS)
        thumb.save(thumb_path, "PNG")
        return {
            "source": str(source),
            "width": image.width,
            "height": image.height,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize a StableCraft reference image")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--thumb", type=Path, required=True)
    args = parser.parse_args()
    try:
        info = normalize_reference(args.source, args.image, args.thumb)
    except Exception as exc:  # noqa: BLE001
        parser.exit(1, f"Impossible de préparer l'image de référence : {exc}\n")
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
