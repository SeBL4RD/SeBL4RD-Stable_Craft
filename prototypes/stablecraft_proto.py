"""StableCraft proof of concept.

Simulates a lasso selection, crops with context, runs FLUX.3 Klein in ComfyUI,
then composites the result back through a feathered mask.

Run with ComfyUI's embedded Python (it already has Pillow and requests):

    F:\\ComfyUI_windows_portable\\python_embeded\\python.exe prototypes\\stablecraft_proto.py

Environment:
    COMFYUI_URL      default http://127.0.0.1:8188
    COMFYUI_UNET     default flux-3-image-klein-Q8_0.gguf
    COMFYUI_CLIP     default Qwen-3-VL-4B-Scaled-FP8-v2.safetensors
    COMFYUI_VAE      default flux2_vae.safetensors
"""

from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "demo" / "lasso-before.png"
OUT = ROOT / "prototypes" / "out"

BASE = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
UNET = os.environ.get("COMFYUI_UNET", "flux-3-image-klein-Q8_0.gguf")
CLIP = os.environ.get("COMFYUI_CLIP", "Qwen-3-VL-4B-Scaled-FP8-v2.safetensors")
VAE = os.environ.get("COMFYUI_VAE", "flux2_vae.safetensors")

PROMPT = (
    "Change the dress to a deep emerald green with subtle fabric folds. "
    "Keep the character, face, hair, pose, arms, legs and background unchanged."
)


def post_json(path: str, payload: dict) -> dict:
    r = requests.post(BASE + path, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def upload_image(path: Path, name: str) -> str:
    with path.open("rb") as f:
        r = requests.post(
            BASE + "/upload/image",
            files={"image": (name, f, "image/png")},
            data={"type": "input", "overwrite": "true"},
            timeout=60,
        )
    r.raise_for_status()
    return r.json()["name"]


def build_workflow(image_name: str, prompt: str, seed: int) -> dict:
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNET}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "flux3"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
        "6": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "7": {
            "class_type": "ReferenceMultiLatent",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["5", 0],
                "vae": ["3", 0],
                "images.image0": ["6", 0],
                "resolution": "resize",
                "resolution.megapixels": 1.0,
            },
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "seed": seed,
                "steps": 16,
                "cfg": 1,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["7", 0],
                "negative": ["7", 1],
                "latent_image": ["7", 2],
                "denoise": 1,
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {
            "class_type": "PreviewImage",
            "inputs": {"images": ["9", 0]},
        },
    }


def wait_for(prompt_id: str, timeout: float = 300.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        h = requests.get(BASE + f"/history/{prompt_id}", timeout=10).json()
        entry = h.get(prompt_id)
        if entry and entry.get("status", {}).get("completed"):
            return entry
        if entry and entry.get("status", {}).get("status_str") == "error":
            raise RuntimeError(json.dumps(entry.get("status", {}), indent=2)[:4000])
        time.sleep(1.0)
    raise TimeoutError(prompt_id)


def download_image(image: dict) -> Image.Image:
    r = requests.get(
        BASE + "/view",
        params={
            "filename": image["filename"],
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        },
        timeout=60,
    )
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def align16(n: int) -> int:
    return max(16, int(round(n / 16.0)) * 16)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    src = Image.open(SOURCE).convert("RGB")
    w, h = src.size

    # A hand-drawn lasso around the dress, in normalized coordinates.
    polygon_norm = [
        (0.40, 0.39),
        (0.57, 0.39),
        (0.63, 0.47),
        (0.64, 0.82),
        (0.54, 0.87),
        (0.43, 0.87),
        (0.36, 0.82),
        (0.36, 0.48),
    ]
    polygon = [(int(x * w), int(y * h)) for x, y in polygon_norm]

    selection = Image.new("L", (w, h), 0)
    ImageDraw.Draw(selection).polygon(polygon, fill=255)
    selection = selection.filter(ImageFilter.GaussianBlur(2.0))

    bbox = selection.getbbox()
    if bbox is None:
        raise RuntimeError("empty selection")

    # Crop with context, aligned to the 16 px grid used by FLUX.
    pad = 96
    x0 = max(0, bbox[0] - pad)
    y0 = max(0, bbox[1] - pad)
    x1 = min(w, bbox[2] + pad)
    y1 = min(h, bbox[3] + pad)
    cw, ch = align16(x1 - x0), align16(y1 - y0)
    x1, y1 = min(w, x0 + cw), min(h, y0 + ch)
    x0, y0 = max(0, x1 - cw), max(0, y1 - ch)
    cw, ch = x1 - x0, y1 - y0

    crop = src.crop((x0, y0, x1, y1))
    crop_path = OUT / "crop.png"
    crop.save(crop_path)

    name = upload_image(crop_path, "stablecraft_crop.png")
    seed = 424242
    queued = post_json(
        "/prompt",
        {"prompt": build_workflow(name, PROMPT, seed), "client_id": "stablecraft-proto"},
    )
    prompt_id = queued["prompt_id"]
    print("queued", prompt_id)

    entry = wait_for(prompt_id)
    result = download_image(entry["outputs"]["10"]["images"][0])
    print("result", result.size)

    result = result.resize((cw, ch), Image.LANCZOS)
    result.save(OUT / "result_raw.png")

    mask_crop = selection.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(10.0))
    mask_crop.save(OUT / "mask.png")

    after = src.copy()
    after.paste(result, (x0, y0), mask_crop)

    src.save(OUT / "before.png")
    after.save(OUT / "after.png")

    side = Image.new("RGB", (w * 2 + 12, h), "white")
    side.paste(src, (0, 0))
    side.paste(after, (w + 12, 0))
    side.save(OUT / "side_by_side.png")

    print("crop", (x0, y0, x1, y1), "selection", bbox)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
