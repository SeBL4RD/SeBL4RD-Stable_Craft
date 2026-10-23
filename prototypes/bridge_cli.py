"""StableCraft bridge CLI (proof of concept).

Runs the full loop against a live PhotoCraft and ComfyUI:

    selection in PhotoCraft
      -> save composite
      -> crop with context
      -> FLUX.3 Klein edit in ComfyUI
      -> insert result as a new layer at the crop offset
      -> layer mask from the selection, feathered
      -> restore the selection

PhotoCraft must be running with the control channel. ComfyUI must be running with
the FLUX.3 models. See config.example.toml.

Usage:
    python prototypes/bridge_cli.py --prompt "Change the dress to royal blue"

    # geometry only, no ComfyUI call
    python prototypes/bridge_cli.py --prompt "..." --dry-run

    # generate, do not insert into PhotoCraft
    python prototypes/bridge_cli.py --prompt "..." --no-apply
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from control_client import ControlClient, ControlError, read_token  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def manifest_profile(profile: str) -> dict[str, Any]:
    manifest = json.loads((ROOT / "models.json").read_text(encoding="utf-8"))
    try:
        return manifest["profiles"][profile]
    except KeyError as exc:
        raise SystemExit(f"unknown profile {profile!r}") from exc


def file_name(path: str | None, fallback: str) -> str:
    return Path(path).name if path else fallback


# ---------------------------------------------------------------------------
# ComfyUI
# ---------------------------------------------------------------------------


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, endpoint: str, timeout: float = 600.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, **kwargs: Any) -> requests.Response:
        response = requests.get(self.endpoint + path, timeout=30, **kwargs)
        response.raise_for_status()
        return response

    def _post(self, path: str, **kwargs: Any) -> requests.Response:
        response = requests.post(self.endpoint + path, timeout=60, **kwargs)
        response.raise_for_status()
        return response

    def status(self) -> dict[str, Any]:
        return self._get("/system_stats").json()

    def options(self, node: str, key: str) -> list[str]:
        info = self._get(f"/object_info/{node}").json()
        spec = info[node]["input"]["required"][key]
        if isinstance(spec, list) and spec and isinstance(spec[0], list):
            return list(spec[0])
        return []

    def require(self, node: str, key: str, value: str) -> None:
        options = self.options(node, key)
        if value not in options:
            raise ComfyError(
                f"{value!r} is not visible to ComfyUI ({node}.{key}).\n"
                f"Available: {', '.join(options[:20]) or '(none)'}\n"
                "Add the file to ComfyUI's model folders or configure extra_model_paths.yaml."
            )

    def upload(self, path: Path, name: str) -> str:
        with path.open("rb") as f:
            response = self._post(
                "/upload/image",
                files={"image": (name, f, "image/png")},
                data={"type": "input", "overwrite": "true"},
            )
        return response.json()["name"]

    def queue(self, workflow: dict[str, Any]) -> str:
        response = self._post(
            "/prompt",
            json={"prompt": workflow, "client_id": f"stablecraft-{random.randrange(1 << 30)}"},
        )
        body = response.json()
        if "prompt_id" not in body:
            raise ComfyError(f"ComfyUI rejected the workflow: {json.dumps(body)[:2000]}")
        return body["prompt_id"]

    def wait(self, prompt_id: str) -> dict[str, Any]:
        deadline = time.time() + self.timeout
        last_note = 0.0
        while time.time() < deadline:
            history = self._get(f"/history/{prompt_id}").json()
            entry = history.get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise ComfyError(comfy_error_message(status))
                if status.get("completed"):
                    return entry
            now = time.time()
            if now - last_note > 5:
                print(f"  ... sampling ({int(now - (deadline - self.timeout))}s)")
                last_note = now
            time.sleep(1.0)
        raise ComfyError(f"ComfyUI timed out after {self.timeout:.0f}s")

    def download(self, image: dict[str, Any]) -> Image.Image:
        response = self._get(
            "/view",
            params={
                "filename": image["filename"],
                "subfolder": image.get("subfolder", ""),
                "type": image.get("type", "output"),
            },
        )
        return Image.open(io.BytesIO(response.content)).convert("RGB")

    def interrupt(self) -> None:
        try:
            self._post("/interrupt")
        except Exception:
            pass


def comfy_error_message(status: dict[str, Any]) -> str:
    for message in status.get("messages", []):
        if isinstance(message, list) and len(message) == 2 and message[0] == "execution_error":
            data = message[1]
            node = data.get("node_type", "?")
            text = data.get("exception_message", "unknown error").splitlines()[0]
            return f"ComfyUI error in {node}: {text}"
    return "ComfyUI reported an error"


def flux3_workflow(
    *,
    image_name: str,
    prompt: str,
    negative: str,
    unet: str,
    text_encoder: str,
    vae: str,
    steps: int,
    cfg: float,
    seed: int,
    prefix: str,
) -> dict[str, Any]:
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": unet}},
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": text_encoder, "type": "flux3"},
        },
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative}},
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
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["7", 0],
                "negative": ["7", 1],
                "latent_image": ["7", 2],
                "denoise": 1.0,
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {
            "class_type": "SaveImage",
            "inputs": {"images": ["9", 0], "filename_prefix": prefix},
        },
    }


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def align16(value: int) -> int:
    return max(16, int(round(value / 16.0)) * 16)


def compute_crop(
    bounds: list[int], doc_w: int, doc_h: int, padding: int
) -> tuple[int, int, int, int]:
    x, y, w, h = (int(v) for v in bounds)
    x0 = max(0, x - padding)
    y0 = max(0, y - padding)
    x1 = min(doc_w, x + w + padding)
    y1 = min(doc_h, y + h + padding)
    cw = min(doc_w, align16(x1 - x0))
    ch = min(doc_h, align16(y1 - y0))
    x0 = min(max(0, x0), doc_w - cw)
    y0 = min(max(0, y0), doc_h - ch)
    return x0, y0, cw, ch


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="StableCraft bridge proof of concept")
    ap.add_argument("--config", type=Path, default=ROOT / "config.toml")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", default="")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--padding", type=int, default=None)
    ap.add_argument("--feather", type=int, default=None)
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--cfg", type=float, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="only save the composite and crop")
    ap.add_argument("--no-apply", action="store_true", help="generate but do not insert into PhotoCraft")
    ap.add_argument("--save-preview", action="store_true", help="also save a flattened after.png")
    ap.add_argument("--timeout", type=float, default=600.0)
    args = ap.parse_args()

    cfg = load_config(args.config)
    profile_name = args.profile or cfg.get("app", {}).get("default_profile", "flux3_klein")
    pcfg = cfg.get("profiles", {}).get(profile_name, {})
    manifest = manifest_profile(profile_name)
    if profile_name != "flux3_klein":
        raise SystemExit(
            "This proof-of-concept CLI supports only 'flux3_klein'. "
            "FLUX.2 and Krea 2 are validated workflows but not wired into the bridge yet."
        )

    comfy_endpoint = cfg.get("comfyui", {}).get("endpoint", "http://127.0.0.1:12452")
    host = cfg.get("photocraft", {}).get("control_host", "127.0.0.1")
    port = int(cfg.get("photocraft", {}).get("control_port", 7878))
    token_path = Path(
        cfg.get("photocraft", {}).get("control_token_file")
        or (ROOT / ".runtime" / "control.token")
    )
    automation_root = Path(
        cfg.get("photocraft", {}).get("automation_root")
        or (ROOT / ".runtime" / "automation")
    )

    padding = args.padding if args.padding is not None else int(pcfg.get("context_padding", 96))
    feather = args.feather if args.feather is not None else int(pcfg.get("feather", 10))
    steps = args.steps if args.steps is not None else int(pcfg.get("steps", manifest["settings"]["steps"]))
    cfg_scale = args.cfg if args.cfg is not None else float(pcfg.get("cfg", manifest["settings"]["cfg"]))

    unet = file_name(pcfg.get("unet"), manifest["files"]["unet"]["filename"])
    text_encoder = file_name(pcfg.get("text_encoder"), manifest["files"]["text_encoder"]["filename"])
    vae = file_name(pcfg.get("vae"), manifest["files"]["vae"]["filename"])

    run_rel = f"stablecraft/{time.strftime('%Y%m%d-%H%M%S')}"
    run_abs = automation_root / run_rel
    run_abs.mkdir(parents=True, exist_ok=True)

    print("PhotoCraft:", f"{host}:{port}")
    print("ComfyUI:   ", comfy_endpoint)
    print("Profile:   ", profile_name, f"({unet}, {text_encoder}, {vae})")

    control = ControlClient(host, port, read_token(token_path))
    comfy = ComfyClient(comfy_endpoint, timeout=args.timeout)
    result_doc_index: int | None = None

    try:
        session = control.session()
        orig_index = int(session["active"])
        orig_doc = next(d for d in session["documents"] if d["index"] == orig_index)
        inspect = control.inspect()

        if not inspect.get("hasSelection"):
            raise SystemExit(
                "Aucune sélection active dans PhotoCraft.\n"
                "Fais un lasso (ou une sélection) autour de la zone à modifier, puis relance."
            )

        x0, y0, cw, ch = compute_crop(
            inspect["selectionBounds"], int(orig_doc["width"]), int(orig_doc["height"]), padding
        )
        print(f"Document:  {orig_doc['name']} {orig_doc['width']}x{orig_doc['height']}")
        print(f"Selection: {inspect['selectionBounds']}")
        print(f"Crop:      ({x0},{y0}) {cw}x{ch}, padding={padding}")

        # Save a channel so we can restore the selection after applying the mask.
        alpha_names = [c["name"] for c in inspect["channels"]["alpha"]]
        if "StableCraft Mask" in alpha_names:
            control.execute(
                "select.saveSelection",
                {"name": "StableCraft Mask", "channel": "StableCraft Mask", "operation": "replace"},
            )
        else:
            control.execute(
                "select.saveSelection",
                {"name": "StableCraft Mask", "channel": "new", "operation": "new"},
            )

        # Composite, then crop with context.
        control.save(f"{run_rel}/composite.png")
        composite_path = run_abs / "composite.png"
        if not composite_path.exists():
            raise SystemExit(f"PhotoCraft did not write {composite_path}")
        composite = Image.open(composite_path).convert("RGB")
        crop = composite.crop((x0, y0, x0 + cw, y0 + ch))
        crop_path = run_abs / "crop.png"
        crop.save(crop_path)
        print("Crop saved:", crop_path)

        if args.dry_run:
            print("Dry run: stopping before ComfyUI.")
            return

        comfy.require("UnetLoaderGGUF", "unet_name", unet)
        comfy.require("CLIPLoader", "clip_name", text_encoder)
        comfy.require("VAELoader", "vae_name", vae)

        upload_name = f"stablecraft_{int(time.time())}.png"
        uploaded = comfy.upload(crop_path, upload_name)
        seed = args.seed if args.seed is not None and args.seed >= 0 else random.randrange(0, 2**63 - 1)
        workflow = flux3_workflow(
            image_name=uploaded,
            prompt=args.prompt,
            negative=args.negative,
            unet=unet,
            text_encoder=text_encoder,
            vae=vae,
            steps=steps,
            cfg=cfg_scale,
            seed=seed,
            prefix="StableCraft",
        )
        started = time.time()
        prompt_id = comfy.queue(workflow)
        print(f"ComfyUI:   queued {prompt_id} (seed {seed}, {steps} steps, cfg {cfg_scale})")
        entry = comfy.wait(prompt_id)
        outputs = entry.get("outputs", {})
        images = []
        for node in outputs.values():
            images.extend(node.get("images", []))
        if not images:
            raise ComfyError("ComfyUI returned no image")
        result = comfy.download(images[0])
        if result.size != (cw, ch):
            result = result.resize((cw, ch), Image.LANCZOS)
        result_path = run_abs / "result.png"
        result.save(result_path)
        print(f"Result:    {result_path} ({time.time() - started:.1f}s)")

        if args.no_apply:
            print("No-apply: result generated but not inserted.")
            return

        # PhotoCraft may close an idle control connection while ComfyUI samples.
        # Reconnect before the apply phase, then find the original document again.
        control.close_socket()
        control = ControlClient(host, port, read_token(token_path))
        ui = control.request("ui.inspect")
        docs = ui["session"]["documents"]
        candidates = [
            d for d in docs
            if d["name"] == orig_doc["name"] and d.get("path") == orig_doc.get("path")
        ]
        if not candidates:
            raise ControlError("the original document is no longer open")
        original = next((d for d in candidates if d["index"] == orig_index), candidates[0])
        orig_index = int(original["index"])
        control.activate(orig_index)

        # Open the result as a temporary document, then copy its layer into the original.
        control.open(f"{run_rel}/result.png")
        ui = control.request("ui.inspect")
        docs = ui["session"]["documents"]
        result_docs = [d for d in docs if d["name"] == "result.png"]
        if not result_docs:
            raise ControlError("the result document is not open")
        result_doc = result_docs[-1]
        result_doc_index = int(result_doc["index"])

        control.activate(result_doc_index)
        result_inspect = control.inspect()
        result_layer = result_inspect["activeLayer"]

        control.activate(orig_index)
        if not control.inspect().get("hasSelection"):
            control.execute("select.loadSelection", {"channel": "StableCraft Mask"})

        layer_name = "StableCraft — " + args.prompt.strip().replace("\n", " ")[:48]
        copied = control.execute(
            "layer.copyToDocument",
            {
                "document": orig_index,
                "source": result_doc_index,
                "layers": [result_layer],
                "offset": [x0, y0],
                "name": layer_name,
            },
        )
        new_layer = int(copied["layers"][0])
        print("Layer:     ", new_layer, layer_name)

        control.execute("layer.layerMask.revealSelection", {"layer": new_layer})
        control.execute("layer.layerMask.edit", {"layer": new_layer, "feather": feather})
        # Put the selection back so the user can iterate or refine.
        try:
            control.execute("select.loadSelection", {"channel": "StableCraft Mask"})
        except ControlError:
            pass

        final = control.inspect()
        layer = next((l for l in final["layers"] if l["id"] == new_layer), None)
        print("Applied:   ", json.dumps(layer, indent=2) if layer else "(layer not found)")
        print("Mask:      ", "yes" if layer and layer.get("hasMask") else "no")

        if args.save_preview:
            control.save(f"{run_rel}/after.png")
            print("Preview:   ", run_abs / "after.png")

        print("Done.")
    except (ControlError, ComfyError, requests.RequestException) as exc:
        print("ERROR:", exc, file=sys.stderr)
        comfy.interrupt()
        raise SystemExit(1)
    finally:
        if result_doc_index is not None:
            control.close_quietly(result_doc_index)
        control.close_socket()


if __name__ == "__main__":
    main()
