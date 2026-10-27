"""Convert LoRA preview images to small PNG thumbnails.

Runs with ComfyUI's embedded Python (which already has Pillow). The StableCraft
UI only reads the generated PNGs with Tkinter; it never loads WebP directly.

Job file format (JSON list):
    [{"key": "abc123", "url": "http://127.0.0.1:8188/api/lm/previews?..."}]
    [{"key": "abc123", "file": "F:/.../preview.webp"}]

One JSON line is printed per job so the UI can update the grid progressively.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image


def _load_source(job: dict[str, str]) -> Image.Image:
    local = str(job.get("file") or "")
    if local:
        return Image.open(local)
    url = str(job.get("url") or "")
    if not url:
        raise ValueError("no preview source")
    with urllib.request.urlopen(url, timeout=20) as response:
        return Image.open(io.BytesIO(response.read()))


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA preview thumbnailer")
    parser.add_argument("--jobs", required=True, help="JSON file describing the jobs")
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--size", type=int, default=160)
    args = parser.parse_args()

    jobs_path = Path(args.jobs)
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    size = max(32, min(512, int(args.size)))

    try:
        jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"jobs: {exc}"}), flush=True)
        return 1
    if not isinstance(jobs, list):
        print(json.dumps({"ok": False, "error": "jobs must be a list"}), flush=True)
        return 1

    for job in jobs:
        if not isinstance(job, dict):
            continue
        key = str(job.get("key") or "").strip()
        if not key:
            continue
        output = cache_dir / f"{key}.png"
        if output.exists():
            print(json.dumps({"key": key, "ok": True, "cached": True}), flush=True)
            continue
        try:
            image = _load_source(job)
            if getattr(image, "is_animated", False):
                image.seek(0)
            image = image.convert("RGB")
            image.thumbnail((size, size), Image.LANCZOS)
            image.save(output, "PNG")
            print(
                json.dumps(
                    {
                        "key": key,
                        "ok": True,
                        "width": image.width,
                        "height": image.height,
                    }
                ),
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                json.dumps({"key": key, "ok": False, "error": str(exc)}),
                flush=True,
            )

    try:
        jobs_path.unlink()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
