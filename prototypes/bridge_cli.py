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
import os
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
from models_tools import resolve_filename  # noqa: E402
from reference_image import normalize_reference  # noqa: E402
from session_store import SessionStore, session_layer_name  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

KREA_PROFILES = {"krea2_edit", "krea2_general_edit"}
QWEN_PROFILE = "qwen_image_21"
REFERENCE_PROFILES = {"krea2_edit", "krea2_general_edit", "flux3_klein", QWEN_PROFILE}
T2I_REFERENCE_PROFILES = {"flux3_klein", QWEN_PROFILE}
REFERENCE_INSTRUCTION = (
    "Image 1 is the scene to edit. Image 2 is the reference image. "
    "Use image 2 only for the requested detail, and keep image 1's scene, "
    "pose, lighting and identity unchanged.\n\n"
)
T2I_REFERENCE_INSTRUCTION = (
    "Image 1 is a reference image. Use its subject, style and details only where "
    "the prompt asks, and generate a new image for the requested scene.\n\n"
)
QWEN_REFERENCE_INSTRUCTION = (
    "Image 1 is the scene to edit. Image 2 is the reference image. "
    "Use <image2> only for the requested detail, and keep <image1>'s scene, "
    "pose, lighting and identity unchanged.\n\n"
)
QWEN_T2I_REFERENCE_INSTRUCTION = (
    "Image 1 is a reference image. Use <image1> for the subject, style and details "
    "requested in the prompt, and generate a new image for the requested scene.\n\n"
)
REFERENCE_SYSTEM_PROMPT = (
    "Image 1 is the scene to edit. Image 2 is the reference image. "
    "Describe both images by detailing the color, shape, size, texture, "
    "quantity, text and spatial relationships of the objects and background. "
    "Use image 2 only for the requested detail, and keep image 1's scene, "
    "pose, lighting and identity unchanged."
)


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


def as_path(value: str | Path, base: Path = ROOT) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path)


def default_user_dir() -> Path:
    return ROOT / "user"


def comfy_temp_dir(cfg: dict[str, Any]) -> Path | None:
    section = cfg.get("comfyui", {})
    configured = str(section.get("temp_dir", "") or "")
    if configured:
        return as_path(configured)
    root = str(section.get("root", "") or os.environ.get("STABLECRAFT_COMFY_ROOT", "") or "")
    if not root:
        return None
    return as_path(root) / "ComfyUI" / "temp"


# ---------------------------------------------------------------------------
# ComfyUI
# ---------------------------------------------------------------------------


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, endpoint: str, timeout: float = 600.0, temp_dir: Path | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.temp_dir = Path(temp_dir) if temp_dir else None

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

    def require_node(self, node: str) -> None:
        try:
            info = self._get(f"/object_info/{node}").json()
        except requests.RequestException as exc:
            raise ComfyError(
                f"ComfyUI node {node} is missing. Install the custom node required by this profile."
            ) from exc
        if node not in info:
            raise ComfyError(
                f"ComfyUI node {node} is missing. Install the custom node required by this profile."
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

    def cleanup(self, image: dict[str, Any]) -> None:
        if image.get("type") != "temp" or self.temp_dir is None:
            return
        path = self.temp_dir / image.get("subfolder", "") / image["filename"]
        try:
            path.unlink()
        except OSError:
            pass

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


def clip_loader_for(text_encoder: str) -> str:
    return "CLIPLoaderGGUF" if text_encoder.lower().endswith(".gguf") else "CLIPLoader"


def unet_loader_for(unet: str) -> str:
    return "UnetLoaderGGUF" if unet.lower().endswith(".gguf") else "UNETLoader"


def build_workflow(
    profile: str,
    *,
    image_name: str | None,
    prompt: str,
    negative: str,
    unet: str,
    text_encoder: str,
    vae: str,
    steps: int,
    cfg: float,
    seed: int,
    width: int,
    height: int,
    prefix: str,
    ref_boost: float = 4.0,
    grounding_px: int = 768,
    reference_image: str | None = None,
    mode: str = "edit",
    lora: str | None = None,
    lora_strength: float = 1.0,
    loras: list[tuple[str, float]] | None = None,
) -> dict[str, Any]:
    if mode not in {"edit", "t2i"}:
        raise ComfyError(f"unknown generation mode {mode!r}")
    if mode == "edit" and not image_name:
        raise ComfyError("le mode EDIT nécessite une image source")

    def start(apply_lora: bool = False) -> tuple[dict[str, Any], list[Any]]:
        unet_inputs: dict[str, Any] = {"unet_name": unet}
        if not unet.lower().endswith(".gguf"):
            # ComfyUI's UNETLoader requires weight_dtype; GGUF has its own loader.
            unet_inputs["weight_dtype"] = "default"
        workflow: dict[str, Any] = {
            "1": {
                "class_type": unet_loader_for(unet),
                "inputs": unet_inputs,
            }
        }
        model: list[Any] = ["1", 0]
        next_id = 900
        if apply_lora and lora:
            workflow[str(next_id)] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": model,
                    "lora_name": lora,
                    "strength_model": lora_strength,
                },
            }
            model = [str(next_id), 0]
            next_id += 1
        for name, strength in loras or []:
            workflow[str(next_id)] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": model,
                    "lora_name": name,
                    "strength_model": max(0.0, min(1.0, float(strength))),
                },
            }
            model = [str(next_id), 0]
            next_id += 1
        return workflow, model

    # ------------------------------------------------------------------
    # Text-to-image: no scene image, but the same crop-sized canvas. The
    # result is still masked by PhotoCraft, so a rectangular selection is
    # the natural way to use this mode.
    # ------------------------------------------------------------------
    if mode == "t2i":
        if profile == "flux3_klein" and reference_image:
            text = f"{T2I_REFERENCE_INSTRUCTION}{prompt}"
            workflow, model = start()
            workflow.update(
                {
                    "2": {
                        "class_type": "CLIPLoader",
                        "inputs": {"clip_name": text_encoder, "type": "flux3"},
                    },
                    "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
                    "4": {
                        "class_type": "CLIPTextEncode",
                        "inputs": {"clip": ["2", 0], "text": text},
                    },
                    "5": {
                        "class_type": "CLIPTextEncode",
                        "inputs": {"clip": ["2", 0], "text": negative},
                    },
                    "6": {
                        "class_type": "LoadImage",
                        "inputs": {"image": reference_image},
                    },
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
                            "model": model,
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
                    "9": {
                        "class_type": "VAEDecode",
                        "inputs": {"samples": ["8", 0], "vae": ["3", 0]},
                    },
                    "10": {
                        "class_type": "PreviewImage",
                        "inputs": {"images": ["9", 0]},
                    },
                }
            )
            return workflow

        if profile == "flux2_klein_9b" and reference_image:
            raise ComfyError(
                "FLUX.2 Klein 9B does not support a reference image, including T2I."
            )

        if profile in {"flux3_klein", "flux2_klein_9b"}:
            workflow, model = start()
            clip_type = "flux3" if profile == "flux3_klein" else "flux2"
            workflow.update(
                {
                    "2": {
                        "class_type": clip_loader_for(text_encoder),
                        "inputs": {"clip_name": text_encoder, "type": clip_type},
                    },
                    "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
                    "4": {
                        "class_type": "CLIPTextEncode",
                        "inputs": {"clip": ["2", 0], "text": prompt},
                    },
                    "5": {
                        "class_type": "CLIPTextEncode",
                        "inputs": {"clip": ["2", 0], "text": negative},
                    },
                    "6": {
                        "class_type": "EmptyFlux2LatentImage",
                        "inputs": {"width": width, "height": height, "batch_size": 1},
                    },
                    "7": {
                        "class_type": "KSampler",
                        "inputs": {
                            "model": model,
                            "seed": seed,
                            "steps": steps,
                            "cfg": cfg,
                            "sampler_name": "euler",
                            "scheduler": "simple",
                            "positive": ["4", 0],
                            "negative": ["5", 0],
                            "latent_image": ["6", 0],
                            "denoise": 1.0,
                        },
                    },
                    "8": {
                        "class_type": "VAEDecode",
                        "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
                    },
                    "9": {
                        "class_type": "PreviewImage",
                        "inputs": {"images": ["8", 0]},
                    },
                }
            )
            return workflow

        if profile in KREA_PROFILES:
            if reference_image:
                raise ComfyError(
                    "Krea 2 T2I does not take a reference image; use EDIT instead."
                )
            workflow, model = start()
            # The identity profile is a qwen_image-architecture merge and uses
            # the 16-channel SD3 latent. The official Krea 2 base follows the
            # ComfyUI template and uses the generic empty latent.
            empty_latent = (
                "EmptySD3LatentImage"
                if profile == "krea2_edit"
                else "EmptyLatentImage"
            )
            workflow.update(
                {
                    "2": {
                        "class_type": "CLIPLoader",
                        "inputs": {"clip_name": text_encoder, "type": "krea2"},
                    },
                    "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
                    "4": {
                        "class_type": "CLIPTextEncode",
                        "inputs": {"clip": ["2", 0], "text": prompt},
                    },
                    "5": {
                        "class_type": "CLIPTextEncode",
                        "inputs": {"clip": ["2", 0], "text": negative},
                    },
                    "6": {
                        "class_type": empty_latent,
                        "inputs": {"width": width, "height": height, "batch_size": 1},
                    },
                    "7": {
                        "class_type": "KSampler",
                        "inputs": {
                            "model": model,
                            "seed": seed,
                            "steps": steps,
                            "cfg": cfg,
                            "sampler_name": "euler",
                            "scheduler": "simple",
                            "positive": ["4", 0],
                            "negative": ["5", 0],
                            "latent_image": ["6", 0],
                            "denoise": 1.0,
                        },
                    },
                    "8": {
                        "class_type": "VAEDecode",
                        "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
                    },
                    "9": {
                        "class_type": "PreviewImage",
                        "inputs": {"images": ["8", 0]},
                    },
                }
            )
            return workflow

        if profile == QWEN_PROFILE:
            qwen_prompt = (
                f"{QWEN_T2I_REFERENCE_INSTRUCTION}{prompt}"
                if reference_image
                else prompt
            )
            workflow, model = start()
            workflow.update(
                {
                    "2": {
                        "class_type": clip_loader_for(text_encoder),
                        "inputs": {"clip_name": text_encoder, "type": "qwen_image"},
                    },
                    "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
                    "4": {
                        "class_type": "TextEncodeQwenImage21",
                        "inputs": {
                            "clip": ["2", 0],
                            "prompt": qwen_prompt,
                            "negative_prompt": negative,
                            "resolution": 1024,
                        },
                    },
                    "6": {
                        "class_type": "QwenImage21Cache",
                        "inputs": {"model": model, "device": "auto", "dtype": "default"},
                    },
                    "7": {
                        "class_type": "KSampler",
                        "inputs": {
                            "model": ["6", 0],
                            "seed": seed,
                            "steps": steps,
                            "cfg": cfg,
                            "sampler_name": "euler",
                            "scheduler": "simple",
                            "positive": ["4", 0],
                            "negative": ["4", 1],
                            # Qwen Image 2.1 uses a 64-channel latent; the text
                            # encoder returns the matching empty latent on output 2.
                            "latent_image": ["4", 2],
                            "denoise": 1.0,
                        },
                    },
                    "8": {
                        "class_type": "VAEDecode",
                        "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
                    },
                    "9": {
                        "class_type": "PreviewImage",
                        "inputs": {"images": ["8", 0]},
                    },
                }
            )
            if reference_image:
                workflow["10"] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": reference_image},
                }
                workflow["4"]["inputs"].update(
                    {
                        "vae": ["3", 0],
                        "images.image_1": ["10", 0],
                    }
                )
            return workflow

        raise ComfyError(f"unknown profile {profile!r}")

    # ------------------------------------------------------------------
    # Instruction editing: the scene crop is the source image.
    # ------------------------------------------------------------------
    if profile == "flux3_klein":
        text = f"{REFERENCE_INSTRUCTION}{prompt}" if reference_image else prompt
        workflow, model = start()
        workflow.update(
            {
                "2": {
                    "class_type": "CLIPLoader",
                    "inputs": {"clip_name": text_encoder, "type": "flux3"},
                },
                "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
                "4": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["2", 0], "text": text},
                },
                "5": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["2", 0], "text": negative},
                },
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
                        "model": model,
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
                "9": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["8", 0], "vae": ["3", 0]},
                },
                "10": {
                    "class_type": "PreviewImage",
                    "inputs": {"images": ["9", 0]},
                },
            }
        )
        if reference_image:
            workflow["11"] = {
                "class_type": "LoadImage",
                "inputs": {"image": reference_image},
            }
            workflow["7"]["inputs"]["images.image1"] = ["11", 0]
        return workflow

    if profile == "flux2_klein_9b":
        if reference_image:
            raise ComfyError(
                "L'image de référence est disponible pour Krea 2, FLUX.3 Klein "
                "et Qwen Image 2.1, pas pour FLUX.2 Klein 9B."
            )
        workflow, model = start()
        workflow.update(
            {
                "2": {
                    "class_type": clip_loader_for(text_encoder),
                    "inputs": {"clip_name": text_encoder, "type": "flux2"},
                },
                "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
                "4": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["2", 0], "text": prompt},
                },
                "5": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["2", 0], "text": negative},
                },
                "6": {"class_type": "LoadImage", "inputs": {"image": image_name}},
                "7": {
                    "class_type": "ImageScaleToTotalPixels",
                    "inputs": {
                        "image": ["6", 0],
                        "upscale_method": "lanczos",
                        "megapixels": 1.0,
                        "resolution_steps": 1,
                    },
                },
                "8": {
                    "class_type": "VAEEncode",
                    "inputs": {"pixels": ["7", 0], "vae": ["3", 0]},
                },
                "9": {
                    "class_type": "ReferenceLatent",
                    "inputs": {"conditioning": ["4", 0], "latent": ["8", 0]},
                },
                "10": {
                    "class_type": "ConditioningZeroOut",
                    "inputs": {"conditioning": ["4", 0]},
                },
                "11": {
                    "class_type": "ReferenceLatent",
                    "inputs": {"conditioning": ["10", 0], "latent": ["8", 0]},
                },
                "12": {
                    "class_type": "KSampler",
                    "inputs": {
                        "model": model,
                        "seed": seed,
                        "steps": steps,
                        "cfg": cfg,
                        "sampler_name": "euler",
                        "scheduler": "simple",
                        "positive": ["9", 0],
                        "negative": ["11", 0],
                        "latent_image": ["8", 0],
                        "denoise": 1.0,
                    },
                },
                "13": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["12", 0], "vae": ["3", 0]},
                },
                "14": {
                    "class_type": "PreviewImage",
                    "inputs": {"images": ["13", 0]},
                },
            }
        )
        return workflow

    if profile in KREA_PROFILES:
        workflow, model = start(apply_lora=profile == "krea2_general_edit")
        workflow.update(
            {
                "2": {
                    "class_type": "CLIPLoader",
                    "inputs": {"clip_name": text_encoder, "type": "krea2"},
                },
                "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
                "4": {"class_type": "LoadImage", "inputs": {"image": image_name}},
                "5": {
                    "class_type": "VAEEncode",
                    "inputs": {"pixels": ["4", 0], "vae": ["3", 0]},
                },
                "6": {
                    "class_type": "EmptySD3LatentImage",
                    "inputs": {"width": width, "height": height, "batch_size": 1},
                },
                "7": {
                    "class_type": "Krea2EditModelPatch",
                    "inputs": {
                        "model": model,
                        "source_latent": ["5", 0],
                        "vae": ["3", 0],
                        "source_image": ["4", 0],
                        "ref_boost": ref_boost,
                        "fit_mode": "fit",
                        "target_latent": ["6", 0],
                    },
                },
                "8": {
                    "class_type": "Krea2EditGroundedEncode",
                    "inputs": {
                        "clip": ["2", 0],
                        "prompt": prompt,
                        "image": ["4", 0],
                        "grounding_px": grounding_px,
                    },
                },
                "9": {
                    "class_type": "Krea2EditGroundedEncode",
                    "inputs": {
                        "clip": ["2", 0],
                        "prompt": "",
                        "image": ["4", 0],
                        "grounding_px": grounding_px,
                    },
                },
                "10": {
                    "class_type": "KSampler",
                    "inputs": {
                        "model": ["7", 0],
                        "seed": seed,
                        "steps": steps,
                        "cfg": cfg,
                        "sampler_name": "euler",
                        "scheduler": "simple",
                        "positive": ["8", 0],
                        "negative": ["9", 0],
                        "latent_image": ["6", 0],
                        "denoise": 1.0,
                    },
                },
                "11": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["10", 0], "vae": ["3", 0]},
                },
                "12": {
                    "class_type": "PreviewImage",
                    "inputs": {"images": ["11", 0]},
                },
            }
        )
        if reference_image:
            workflow["13"] = {
                "class_type": "LoadImage",
                "inputs": {"image": reference_image},
            }
            workflow["7"]["inputs"].update(
                {
                    "source_image_b": ["13", 0],
                    "ref_position": "beside (right of target)",
                    "ref_position_a": "aligned (trained)",
                    "ref_boost_a": 1.0,
                }
            )
            for node in ("8", "9"):
                workflow[node]["inputs"].update(
                    {
                        "image_b": ["13", 0],
                        "system_prompt": REFERENCE_SYSTEM_PROMPT,
                    }
                )
        return workflow

    if profile == QWEN_PROFILE:
        qwen_prompt = f"{QWEN_REFERENCE_INSTRUCTION}{prompt}" if reference_image else prompt
        workflow, model = start()
        workflow.update(
            {
                "2": {
                    "class_type": clip_loader_for(text_encoder),
                    "inputs": {"clip_name": text_encoder, "type": "qwen_image"},
                },
                "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
                "4": {"class_type": "LoadImage", "inputs": {"image": image_name}},
                "5": {
                    "class_type": "TextEncodeQwenImage21",
                    "inputs": {
                        "clip": ["2", 0],
                        "prompt": qwen_prompt,
                        "negative_prompt": negative,
                        "vae": ["3", 0],
                        "resolution": 1024,
                        "images.image_1": ["4", 0],
                    },
                },
                "6": {
                    "class_type": "QwenImage21Cache",
                    "inputs": {"model": model, "device": "auto", "dtype": "default"},
                },
                "7": {
                    "class_type": "KSampler",
                    "inputs": {
                        "model": ["6", 0],
                        "seed": seed,
                        "steps": steps,
                        "cfg": cfg,
                        "sampler_name": "euler",
                        "scheduler": "simple",
                        "positive": ["5", 0],
                        "negative": ["5", 1],
                        "latent_image": ["5", 2],
                        "denoise": 1.0,
                    },
                },
                "8": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
                },
                "9": {
                    "class_type": "PreviewImage",
                    "inputs": {"images": ["8", 0]},
                },
            }
        )
        if reference_image:
            workflow["10"] = {
                "class_type": "LoadImage",
                "inputs": {"image": reference_image},
            }
            workflow["5"]["inputs"]["images.image_2"] = ["10", 0]
        return workflow

    raise ComfyError(f"unknown profile {profile!r}")


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


# ---------------------------------------------------------------------------
# Persistent sessions (gallery per layer)
# ---------------------------------------------------------------------------


def sessions_root(ctx: dict[str, Any]) -> Path:
    configured = ctx["cfg"].get("app", {}).get("sessions_dir")
    if configured:
        return as_path(str(configured))
    return default_user_dir() / "sessions"


def store_reference(
    store: SessionStore,
    sdata: dict[str, Any],
    source: Path,
    display_name: str | None = None,
) -> Path:
    source = as_path(str(source))
    if not source.exists():
        raise ControlError(f"image de référence introuvable : {source}")
    directory = store.directory(str(sdata["id"]))
    image_path = directory / "reference.png"
    thumb_path = directory / "reference_thumb.png"
    info = normalize_reference(source, image_path, thumb_path)
    sdata["reference"] = {
        "image": "reference.png",
        "thumb": "reference_thumb.png",
        "name": display_name or source.name,
        "enabled": True,
        "width": info.get("width"),
        "height": info.get("height"),
    }
    store.save(sdata)
    return image_path


def session_reference_path(
    store: SessionStore, sdata: dict[str, Any]
) -> Path | None:
    reference = sdata.get("reference")
    if not isinstance(reference, dict) or not reference.get("enabled", True):
        return None
    relative = reference.get("image") or "reference.png"
    path = store.directory(str(sdata["id"])) / str(relative)
    return path if path.exists() else None


def rel_to_root(ctx: dict[str, Any], path: Path) -> str:
    try:
        return path.resolve().relative_to(ctx["automation_root"].resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(
            f"{path} n'est pas dans le dossier d'automation de PhotoCraft ({ctx['automation_root']})."
        ) from exc


def connect_control(ctx: dict[str, Any]) -> ControlClient:
    return ControlClient(ctx["host"], ctx["port"], read_token(ctx["token_path"]))


def is_stablecraft_recent(path: object) -> bool:
    normalized = str(path).replace("\\", "/")
    if normalized.startswith("sessions/"):
        return (
            "/generations/" in normalized
            or normalized.endswith(("/mask.png", "/base.png", "/after.png"))
        )
    return "/sessions/" in normalized and "/generations/" in normalized


def clean_recent_files(control: ControlClient) -> None:
    """Drop StableCraft temp documents from PhotoCraft's recent-files list.

    `app.open` is how the bridge brings `result.png` and `mask.png` into
    PhotoCraft, and PhotoCraft records every open in File > Open Recent. Those
    entries are implementation details, not documents the user wants there.
    """
    try:
        recent = control.execute("prefs.get", {"path": "fileHandling.recentFiles"})
        if not isinstance(recent, list):
            return
        kept = [entry for entry in recent if not is_stablecraft_recent(entry)]
        if len(kept) != len(recent):
            control.execute(
                "prefs.set",
                {"path": "fileHandling.recentFiles", "value": kept},
            )
    except ControlError:
        # Older PhotoCraft builds may not expose the preference through
        # automation; the gallery keeps working without this cleanup.
        pass


def save_composite(
    control: ControlClient,
    automation_root: Path,
    path: Path,
    orig_index: int,
) -> None:
    """Save the flattened composite without PhotoCraft's flatten notice.

    Saving a multi-layer document as PNG makes PhotoCraft post a warning notice
    ("layers flattened"), which appears in the lower-right corner. Duplicating
    the document merged produces a single-layer document, so the same PNG save
    has no warning. The temporary document is closed immediately.
    """
    duplicate = control.execute(
        "image.duplicate",
        {
            "name": f"StableCraft Composite {time.time_ns()}",
            "mergedOnly": True,
        },
    )
    duplicate_index = int(duplicate["document"])
    try:
        try:
            relative = path.resolve().relative_to(automation_root.resolve()).as_posix()
        except ValueError as exc:
            raise ControlError(
                f"{path} n'est pas dans le dossier d'automation de PhotoCraft ({automation_root})."
            ) from exc
        control.save(relative)
    finally:
        control.close_quietly(duplicate_index)
        control.activate(orig_index)


def current_document(control: ControlClient, sdata: dict[str, Any] | None = None) -> dict[str, Any]:
    ui = control.request("ui.inspect")
    docs = ui["session"]["documents"]
    if not docs:
        raise ControlError("aucun document ouvert dans PhotoCraft")
    active = int(ui["session"]["active"])
    if sdata is not None:
        name = sdata["document"]["name"]
        path = sdata["document"].get("path")
        matches = [
            d for d in docs
            if d["name"] == name and (path is None or d.get("path") == path)
        ]
        if not matches:
            # The file may have been moved since the session was created. If its
            # name is unique among the open documents, keep the session usable.
            by_name = [d for d in docs if d["name"] == name]
            if len(by_name) == 1:
                matches = by_name
        if not matches:
            raise ControlError(f"le document de la session ({name}) n'est pas ouvert")
        doc = next((d for d in matches if d["index"] == active), matches[0])
    else:
        doc = next(d for d in docs if d["index"] == active)
    control.activate(int(doc["index"]))
    return doc


def find_session_layer(control: ControlClient, session_id: str) -> dict[str, Any] | None:
    prefix = f"StableCraft [{session_id}]"

    def walk(layers: list[dict[str, Any]]) -> dict[str, Any] | None:
        for layer in layers:
            if str(layer.get("name", "")).startswith(prefix):
                return layer
            found = walk(layer.get("children", []))
            if found:
                return found
        return None

    return walk(control.inspect().get("layers", []))


def load_mask_selection(
    control: ControlClient,
    ctx: dict[str, Any],
    store: SessionStore,
    sdata: dict[str, Any],
    orig_index: int,
) -> bool:
    channel = sdata.get("mask_channel")
    if channel:
        try:
            control.execute("select.loadSelection", {"channel": channel})
            return True
        except ControlError:
            pass

    mask_path = store.mask_path(sdata)
    if not mask_path.exists():
        return False
    mask_rel = rel_to_root(ctx, mask_path)
    control.open(mask_rel)
    ui = control.request("ui.inspect")
    mask_docs = [d for d in ui["session"]["documents"] if d["name"] == mask_path.name]
    if not mask_docs:
        return False
    mask_doc = int(mask_docs[-1]["index"])
    control.activate(orig_index)
    control.execute("select.loadSelection", {"channel": "composite", "document": mask_doc})
    control.close_quietly(mask_doc)
    control.activate(orig_index)
    return True


def apply_session_result(
    control: ControlClient,
    ctx: dict[str, Any],
    store: SessionStore,
    sdata: dict[str, Any],
    result_path: Path,
    crop: list[int],
    feather: int,
    orig_index: int,
    restore_selection: bool,
) -> int:
    if not result_path.exists():
        raise ControlError(f"résultat introuvable : {result_path}")
    if not load_mask_selection(control, ctx, store, sdata, orig_index):
        raise ControlError("impossible de recharger le masque de la session")

    result_rel = rel_to_root(ctx, result_path)
    control.open(result_rel)
    ui = control.request("ui.inspect")
    result_docs = [d for d in ui["session"]["documents"] if d["name"] == result_path.name]
    if not result_docs:
        raise ControlError("le document de résultat n'est pas ouvert")
    result_doc = int(result_docs[-1]["index"])
    control.activate(result_doc)
    result_layer = control.inspect()["activeLayer"]

    control.activate(orig_index)
    target = find_session_layer(control, str(sdata["id"]))
    temporary_layer: int | None = None
    if target:
        control.execute("layer.select", {"layer": target["id"]})
    elif control.inspect().get("activeLayer") is None:
        # `layer.copyToDocument` needs an active destination layer. Some PSDs
        # open with no layer selected, so create one and remove it afterwards.
        created = control.execute(
            "layer.new.layer", {"name": "StableCraft (temporaire)"}
        )
        temporary_layer = int(created["layer"])

    x0, y0, _cw, _ch = crop
    try:
        copied = control.execute(
            "layer.copyToDocument",
            {
                "document": orig_index,
                "source": result_doc,
                "layers": [result_layer],
                "offset": [x0, y0],
                "name": sdata["layer_name"],
            },
        )
    except ControlError:
        if temporary_layer is not None:
            control.execute("layer.delete", {"layer": temporary_layer})
        raise
    new_layer = int(copied["layers"][0])
    if temporary_layer is not None:
        control.execute("layer.delete", {"layer": temporary_layer})
    if target:
        control.execute("layer.delete", {"layer": target["id"]})
    if not control.inspect().get("hasSelection"):
        if not load_mask_selection(control, ctx, store, sdata, orig_index):
            raise ControlError("impossible de recharger le masque avant d'appliquer le calque")
    control.execute("layer.layerMask.revealSelection", {"layer": new_layer})
    control.execute("layer.layerMask.edit", {"layer": new_layer, "feather": feather})
    if restore_selection:
        try:
            load_mask_selection(control, ctx, store, sdata, orig_index)
        except ControlError:
            pass

    control.close_quietly(result_doc)
    control.activate(orig_index)
    return new_layer


def save_session_snapshot(
    control: ControlClient,
    ctx: dict[str, Any],
    store: SessionStore,
    sdata: dict[str, Any],
    orig_doc: dict[str, Any],
) -> None:
    base = store.base_path(sdata)
    base.parent.mkdir(parents=True, exist_ok=True)
    save_composite(control, ctx["automation_root"], base, int(orig_doc["index"]))
    if not base.exists():
        raise ControlError(f"PhotoCraft n'a pas écrit {base}")

    sid = str(sdata["id"])
    channel = f"StableCraft Mask {sid}"
    sdata["mask_channel"] = channel
    control.execute("select.saveSelection", {"name": channel, "channel": "new"})
    duplicate = control.execute(
        "channel.duplicate",
        {"channel": channel, "document": "new", "name": f"StableCraft Mask {sid}"},
    )
    mask_doc = int(duplicate["document"])
    mask = store.mask_path(sdata)
    control.save(rel_to_root(ctx, mask))
    control.close(mask_doc)
    control.activate(int(orig_doc["index"]))
    if not control.inspect().get("hasSelection"):
        control.execute("select.loadSelection", {"channel": channel})


def create_session(
    ctx: dict[str, Any],
    control: ControlClient,
    store: SessionStore,
    orig_doc: dict[str, Any],
    inspect: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    sid = store.new_id()
    sdata = {
        "id": sid,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "document": {
            "name": orig_doc["name"],
            "path": orig_doc.get("path"),
            "width": int(orig_doc["width"]),
            "height": int(orig_doc["height"]),
        },
        "selection": [int(v) for v in inspect["selectionBounds"]],
        "layer_name": session_layer_name(sid, prompt),
        "base": "base.png",
        "mask": "mask.png",
        "mask_channel": f"StableCraft Mask {sid}",
        "profile": ctx["profile_name"],
        "mode": ctx["mode"],
        "settings": {
            "padding": ctx["padding"],
            "feather": ctx["feather"],
            "steps": ctx["steps"],
            "cfg": ctx["cfg_scale"],
        },
        "generations": [],
        "current": -1,
    }
    store.create(sdata)
    save_session_snapshot(control, ctx, store, sdata, orig_doc)
    store.save(sdata)
    return sdata


def parse_lora_args(values: list[str] | None) -> list[tuple[str, float]]:
    """Parse repeated ``--lora NAME=STRENGTH`` arguments."""
    loras: list[tuple[str, float]] = []
    seen: set[str] = set()
    for raw in values or []:
        text = str(raw).strip()
        if not text:
            continue
        name = text
        strength = 1.0
        head, separator, tail = text.rpartition("=")
        if separator and head.strip():
            try:
                strength = float(tail.replace(",", "."))
                name = head.strip()
            except ValueError:
                name = text
        name = name.strip()
        if not name:
            continue
        if strength <= 0:
            continue
        key = name.replace("\\", "/").casefold()
        if key in seen:
            raise SystemExit(f"LoRA en double : {name}")
        seen.add(key)
        loras.append((name, max(0.0, min(1.0, strength))))
    if len(loras) > 10:
        raise SystemExit("Maximum 10 LoRA par génération.")
    return loras


def validate_loras(
    comfy: ComfyClient, loras: list[tuple[str, float]] | None
) -> list[tuple[str, float]]:
    """Resolve names against ComfyUI's lora list and clamp strengths."""
    values = list(loras or [])
    if not values:
        return []
    options = comfy.options("LoraLoaderModelOnly", "lora_name")
    lookup = {
        str(option).replace("\\", "/").casefold(): str(option) for option in options
    }
    normalized: list[tuple[str, float]] = []
    missing: list[str] = []
    for name, strength in values[:10]:
        actual = lookup.get(str(name).replace("\\", "/").casefold())
        if actual is None:
            missing.append(str(name))
        else:
            normalized.append((actual, max(0.0, min(1.0, float(strength)))))
    if missing:
        raise ComfyError(
            "LoRA introuvable(s) dans ComfyUI : "
            + ", ".join(missing)
            + "\nOuvre la page LoRA Manager et vérifie que le fichier est visible."
        )
    if len(values) > 10:
        raise ComfyError("Maximum 10 LoRA par génération.")
    return normalized


def comfy_generate(
    ctx: dict[str, Any],
    comfy: ComfyClient,
    image_path: Path,
    width: int,
    height: int,
    prompt: str,
    negative: str,
    seed: int,
    reference_path: Path | None = None,
) -> Image.Image:
    mode = ctx["mode"]
    profile = ctx["profile_name"]
    ctx["loras"] = validate_loras(comfy, list(ctx.get("loras") or []))
    comfy.require(unet_loader_for(ctx["unet"]), "unet_name", ctx["unet"])
    comfy.require(clip_loader_for(ctx["text_encoder"]), "clip_name", ctx["text_encoder"])
    comfy.require("VAELoader", "vae_name", ctx["vae"])
    if mode == "edit" and profile in KREA_PROFILES:
        comfy.require_node("Krea2EditModelPatch")
        comfy.require_node("Krea2EditGroundedEncode")
    if profile == "krea2_edit":
        comfy.require_node("EmptySD3LatentImage")
    if profile == QWEN_PROFILE:
        comfy.require_node("TextEncodeQwenImage21")
        comfy.require_node("QwenImage21Cache")
    if mode == "edit" and ctx.get("lora"):
        comfy.require("LoraLoaderModelOnly", "lora_name", ctx["lora"])
    if reference_path is not None and profile not in REFERENCE_PROFILES:
        raise ComfyError(
            f"L'image de référence n'est pas disponible pour le profil {profile}."
        )

    uploaded = None
    if mode == "edit":
        uploaded = comfy.upload(image_path, f"stablecraft_{time.time_ns()}.png")
    reference_name = None
    if reference_path is not None:
        reference_name = comfy.upload(
            reference_path, f"stablecraft_ref_{time.time_ns()}.png"
        )
    workflow = build_workflow(
        profile,
        image_name=uploaded,
        prompt=prompt,
        negative=negative,
        unet=ctx["unet"],
        text_encoder=ctx["text_encoder"],
        vae=ctx["vae"],
        steps=ctx["steps"],
        cfg=ctx["cfg_scale"],
        seed=seed,
        width=width,
        height=height,
        prefix="StableCraft",
        ref_boost=ctx["ref_boost"],
        grounding_px=ctx["grounding_px"],
        reference_image=reference_name,
        mode=mode,
        lora=ctx.get("lora"),
        lora_strength=float(ctx.get("lora_strength", 1.0)),
        loras=ctx.get("loras"),
    )
    prompt_id = comfy.queue(workflow)
    print(
        f"ComfyUI:   queued {prompt_id} (mode {mode.upper()}, seed {seed}, "
        f"{ctx['steps']} steps, cfg {ctx['cfg_scale']})"
    )
    entry = comfy.wait(prompt_id)
    images: list[dict[str, Any]] = []
    for node in entry.get("outputs", {}).values():
        images.extend(node.get("images", []))
    if not images:
        raise ComfyError("ComfyUI returned no image")
    image = images[0]
    try:
        result = comfy.download(image)
    finally:
        comfy.cleanup(image)
    if result.size != (width, height):
        result = result.resize((width, height), Image.LANCZOS)
    return result


def run_session_generate(ctx: dict[str, Any]) -> None:
    args = ctx["args"]
    store = SessionStore(sessions_root(ctx))
    control = connect_control(ctx)
    clean_recent_files(control)
    comfy = ComfyClient(
        ctx["comfy_endpoint"], timeout=args.timeout, temp_dir=comfy_temp_dir(ctx["cfg"])
    )
    try:
        if args.session:
            sdata = store.load(args.session)
            if args.mode is None:
                generations = sdata.get("generations", [])
                current = int(sdata.get("current", -1))
                if 0 <= current < len(generations):
                    ctx["mode"] = str(generations[current].get("mode", "edit"))
                else:
                    ctx["mode"] = str(sdata.get("mode", "edit"))
            orig_doc = current_document(control, sdata)
            base_abs = store.base_path(sdata)
            if not base_abs.exists():
                raise ControlError(f"base de session introuvable : {base_abs}")
            selection = [int(v) for v in sdata["selection"]]
            print(f"Session:   {sdata['id']} ({len(sdata['generations'])} génération(s))")
        else:
            orig_doc = current_document(control)
            inspect = control.inspect()
            if not inspect.get("hasSelection"):
                raise SystemExit(
                    "Aucune sélection active dans PhotoCraft.\n"
                    "Fais un lasso autour de la zone à modifier."
                )
            selection = [int(v) for v in inspect["selectionBounds"]]
            sdata = create_session(ctx, control, store, orig_doc, inspect, args.prompt)
            base_abs = store.base_path(sdata)
            print(f"Session:   {sdata['id']} (nouvelle)")

        prompt = (args.prompt or "").strip()
        if not prompt:
            raise SystemExit("--prompt est requis pour une génération")

        reference_path: Path | None = None
        if args.reference:
            if ctx["profile_name"] not in REFERENCE_PROFILES:
                raise SystemExit(
                    "L'image de référence est disponible pour Krea 2, FLUX.3 Klein "
                    "et Qwen Image 2.1, pas pour ce profil."
                )
            if (
                ctx["mode"] == "t2i"
                and ctx["profile_name"] not in T2I_REFERENCE_PROFILES
            ):
                raise SystemExit(
                    "Ce profil n'utilise pas la référence en T2I ; passe en mode EDIT."
                )
            reference_path = store_reference(
                store,
                sdata,
                as_path(args.reference),
                display_name=args.reference_name,
            )
            print(f"Reference: {reference_path}")
        elif (
            ctx["profile_name"] in REFERENCE_PROFILES
            and (
                ctx["mode"] == "edit"
                or ctx["profile_name"] in T2I_REFERENCE_PROFILES
            )
        ):
            reference_path = session_reference_path(store, sdata)
            if reference_path is not None:
                print(f"Reference: {reference_path}")

        orig_index = int(orig_doc["index"])
        base = Image.open(base_abs).convert("RGB")
        x0, y0, cw, ch = compute_crop(selection, base.width, base.height, ctx["padding"])
        crop_image = base.crop((x0, y0, x0 + cw, y0 + ch))
        sid = str(sdata["id"])
        sdir = store.directory(sid)
        crop_path = sdir / "crop_last.png"
        crop_image.save(crop_path)
        print(f"Crop:      ({x0},{y0}) {cw}x{ch}, padding={ctx['padding']}")

        if args.dry_run:
            print("Dry run: session créée, arrêt avant ComfyUI.")
            print(f"SESSION: {sid}")
            return

        seed = args.seed if args.seed is not None and args.seed >= 0 else random.randrange(0, 2**63 - 1)
        started = time.time()
        result = comfy_generate(
            ctx,
            comfy,
            crop_path,
            cw,
            ch,
            prompt,
            args.negative,
            seed,
            reference_path=reference_path,
        )
        elapsed = time.time() - started

        index = len(sdata["generations"])
        gdir = store.generation_dir(sdata, index)
        gdir.mkdir(parents=True, exist_ok=True)
        result_path = gdir / "result.png"
        result.save(result_path)
        crop_image.save(gdir / "crop.png")
        thumb = result.copy()
        thumb.thumbnail((128, 128), Image.LANCZOS)
        thumb.save(gdir / "thumb.png")
        sdata["layer_name"] = session_layer_name(sid, prompt)
        sdata["profile"] = ctx["profile_name"]
        sdata["mode"] = ctx["mode"]
        sdata["settings"] = {
            "padding": ctx["padding"],
            "feather": ctx["feather"],
            "steps": ctx["steps"],
            "cfg": ctx["cfg_scale"],
        }
        generation = {
            "prompt": prompt,
            "negative": args.negative,
            "seed": seed,
            "steps": ctx["steps"],
            "cfg": ctx["cfg_scale"],
            "profile": ctx["profile_name"],
            "mode": ctx["mode"],
            "feather": ctx["feather"],
            "padding": ctx["padding"],
            "loras": [
                {"name": name, "strength": strength}
                for name, strength in (ctx.get("loras") or [])
            ],
            "crop": [x0, y0, cw, ch],
            "crop_offset": [x0, y0],
            "crop_size": [cw, ch],
            "result": f"generations/{index}/result.png",
            "thumb": f"generations/{index}/thumb.png",
            "reference": (
                sdata.get("reference", {}).get("name") if reference_path else None
            ),
            "elapsed": round(elapsed, 1),
        }
        store.add_generation(sdata, generation)
        store.save(sdata)
        print(f"Result:    {result_path} ({elapsed:.1f}s)")
        print(f"SESSION: {sid}")
        print(f"GENERATION: {index}")

        if args.no_apply:
            print("No-apply: génération enregistrée, calque non modifié.")
            return

        # Reconnect: PhotoCraft may close an idle control connection during sampling.
        control.close_socket()
        control = connect_control(ctx)
        orig_doc = current_document(control, sdata)
        orig_index = int(orig_doc["index"])
        new_layer = apply_session_result(
            control, ctx, store, sdata, result_path, [x0, y0, cw, ch],
            ctx["feather"], orig_index, restore_selection=True,
        )
        sdata["layer_name"] = session_layer_name(sid, prompt)
        sdata["current"] = index
        store.save(sdata)
        print(f"Layer:     {new_layer} {sdata['layer_name']}")

        if args.save_preview:
            preview = sdir / "after.png"
            save_composite(control, ctx["automation_root"], preview, orig_index)
            print(f"Preview:   {preview}")

        print("Done.")
    except (ControlError, ComfyError, requests.RequestException) as exc:
        print("ERROR:", exc, file=sys.stderr)
        comfy.interrupt()
        raise SystemExit(1)
    finally:
        clean_recent_files(control)
        control.close_socket()


def run_session_apply(ctx: dict[str, Any]) -> None:
    args = ctx["args"]
    store = SessionStore(sessions_root(ctx))
    sdata = store.load(args.apply)
    generations = sdata.get("generations", [])
    if not generations:
        raise SystemExit(f"la session {args.apply} n'a aucune génération")
    index = args.generation if args.generation is not None else int(sdata.get("current", -1))
    if index < 0:
        index = len(generations) - 1
    if index >= len(generations):
        raise SystemExit(f"génération {index} hors limites (0..{len(generations) - 1})")
    generation = generations[index]
    result_path = store.directory(str(sdata["id"])) / generation["result"]
    if not result_path.exists():
        raise SystemExit(f"résultat introuvable : {result_path}")
    crop = [int(v) for v in generation.get("crop", [0, 0, 0, 0])]
    if crop[2] <= 0 or crop[3] <= 0:
        base = Image.open(store.base_path(sdata))
        crop = list(compute_crop(sdata["selection"], base.width, base.height, int(sdata["settings"].get("padding", 96))))
    feather = int(generation.get("feather", sdata["settings"].get("feather", 10)))
    sdata["layer_name"] = session_layer_name(str(sdata["id"]), generation.get("prompt", ""))

    control = connect_control(ctx)
    clean_recent_files(control)
    try:
        orig_doc = current_document(control, sdata)
        orig_index = int(orig_doc["index"])
        new_layer = apply_session_result(
            control, ctx, store, sdata, result_path, crop, feather,
            orig_index, restore_selection=False,
        )
        sdata["current"] = index
        sdata["mode"] = str(generation.get("mode", "edit"))
        store.save(sdata)
        print(f"SESSION: {sdata['id']}")
        print(f"GENERATION: {index}")
        print(f"Layer:     {new_layer} {sdata['layer_name']}")
        if args.save_preview:
            preview = store.directory(str(sdata["id"])) / "after.png"
            save_composite(control, ctx["automation_root"], preview, orig_index)
            print(f"Preview:   {preview}")
        print("Done.")
    finally:
        clean_recent_files(control)
        control.close_socket()


def run_session_mode(ctx: dict[str, Any]) -> None:
    if ctx["args"].apply:
        run_session_apply(ctx)
    else:
        run_session_generate(ctx)


def main() -> None:
    ap = argparse.ArgumentParser(description="StableCraft bridge")
    ap.add_argument("--config", type=Path, default=ROOT / "config.toml")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--negative", default="")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--mode", choices=("edit", "t2i"), default=None)
    ap.add_argument("--padding", type=int, default=None)
    ap.add_argument("--feather", type=int, default=None)
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--cfg", type=float, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="only save the composite and crop")
    ap.add_argument("--no-apply", action="store_true", help="generate but do not insert into PhotoCraft")
    ap.add_argument("--save-preview", action="store_true", help="also save a flattened after.png")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--session-mode", action="store_true", help="create a persistent session for this selection")
    ap.add_argument("--session", default=None, help="regenerate an existing session id")
    ap.add_argument("--apply", default=None, help="apply an existing generation of a session id")
    ap.add_argument("--generation", type=int, default=None, help="generation index for --apply")
    ap.add_argument("--sessions-dir", type=Path, default=None, help="override the sessions root")
    ap.add_argument(
        "--reference",
        type=Path,
        default=None,
        help="reference image for the current session (Krea 2, FLUX.3 and Qwen 2.1)",
    )
    ap.add_argument(
        "--reference-name",
        default=None,
        help="original filename to record with --reference",
    )
    ap.add_argument(
        "--lora",
        action="append",
        default=[],
        metavar="NAME=STRENGTH",
        help="user LoRA to apply (repeatable, max 10, strength 0..1)",
    )
    args = ap.parse_args()
    loras = parse_lora_args(args.lora)

    cfg = load_config(args.config)
    profile_name = args.profile or cfg.get("app", {}).get("default_profile", "flux3_klein")
    pcfg = cfg.get("profiles", {}).get(profile_name, {})
    manifest = manifest_profile(profile_name)

    comfy_endpoint = cfg.get("comfyui", {}).get("endpoint", "http://127.0.0.1:8188")
    host = cfg.get("photocraft", {}).get("control_host", "127.0.0.1")
    port = int(cfg.get("photocraft", {}).get("control_port", 7990))
    token_path = as_path(
        str(
            cfg.get("photocraft", {}).get("control_token_file")
            or (default_user_dir() / "control.token")
        )
    )
    automation_root = as_path(
        str(cfg.get("photocraft", {}).get("automation_root") or default_user_dir())
    )

    padding = args.padding if args.padding is not None else int(pcfg.get("context_padding", 96))
    feather = args.feather if args.feather is not None else int(pcfg.get("feather", 10))
    steps = args.steps if args.steps is not None else int(pcfg.get("steps", manifest["settings"]["steps"]))
    cfg_scale = args.cfg if args.cfg is not None else float(pcfg.get("cfg", manifest["settings"]["cfg"]))
    ref_boost = float(pcfg.get("ref_boost", manifest.get("settings", {}).get("ref_boost", 4.0)))
    grounding_px = int(pcfg.get("grounding_px", manifest.get("settings", {}).get("grounding_px", 768)))

    unet = resolve_filename(profile_name, "unet", pcfg, manifest)
    text_encoder = resolve_filename(profile_name, "text_encoder", pcfg, manifest)
    vae = resolve_filename(profile_name, "vae", pcfg, manifest)
    lora_file = manifest["files"].get("lora")
    lora = (
        resolve_filename(profile_name, "lora", pcfg, manifest) if lora_file else None
    )
    lora_strength = float(
        pcfg.get(
            "lora_strength",
            manifest.get("settings", {}).get("lora_strength", 1.0),
        )
    )
    mode = args.mode or "edit"

    if args.reference and not (args.session_mode or args.session):
        raise SystemExit(
            "--reference nécessite --session-mode (nouvelle session) ou --session <id>."
        )
    if args.reference and mode == "t2i" and profile_name not in T2I_REFERENCE_PROFILES:
        raise SystemExit(
            "Ce profil n'utilise pas la référence en T2I ; passe en mode EDIT."
        )

    if args.session_mode or args.session or args.apply:
        ctx = {
            "args": args,
            "cfg": cfg,
            "profile_name": profile_name,
            "mode": mode,
            "pcfg": pcfg,
            "manifest": manifest,
            "comfy_endpoint": comfy_endpoint,
            "host": host,
            "port": port,
            "token_path": token_path,
            "automation_root": automation_root,
            "padding": padding,
            "feather": feather,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "ref_boost": ref_boost,
            "grounding_px": grounding_px,
            "unet": unet,
            "text_encoder": text_encoder,
            "vae": vae,
            "lora": lora,
            "lora_strength": lora_strength,
            "loras": loras,
        }
        if args.sessions_dir:
            cfg.setdefault("app", {})["sessions_dir"] = str(args.sessions_dir)
        run_session_mode(ctx)
        return

    if not args.prompt.strip():
        raise SystemExit("--prompt est requis")

    run_rel = f"stablecraft/{time.strftime('%Y%m%d-%H%M%S')}"
    run_abs = automation_root / run_rel
    run_abs.mkdir(parents=True, exist_ok=True)

    print("PhotoCraft:", f"{host}:{port}")
    print("ComfyUI:   ", comfy_endpoint)
    print("Profile:   ", profile_name, f"({unet}, {text_encoder}, {vae})")

    control = ControlClient(host, port, read_token(token_path))
    clean_recent_files(control)
    comfy = ComfyClient(
        comfy_endpoint, timeout=args.timeout, temp_dir=comfy_temp_dir(cfg)
    )
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
        save_composite(
            control, automation_root, run_abs / "composite.png", orig_index
        )
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
        comfy.require(clip_loader_for(text_encoder), "clip_name", text_encoder)
        comfy.require("VAELoader", "vae_name", vae)
        loras = validate_loras(comfy, loras)
        if profile_name == "krea2_edit":
            comfy.require_node("Krea2EditModelPatch")
            comfy.require_node("Krea2EditGroundedEncode")
            comfy.require_node("EmptySD3LatentImage")

        upload_name = f"stablecraft_{int(time.time())}.png"
        uploaded = comfy.upload(crop_path, upload_name)
        seed = args.seed if args.seed is not None and args.seed >= 0 else random.randrange(0, 2**63 - 1)
        workflow = build_workflow(
            profile_name,
            image_name=uploaded,
            prompt=args.prompt,
            negative=args.negative,
            unet=unet,
            text_encoder=text_encoder,
            vae=vae,
            steps=steps,
            cfg=cfg_scale,
            seed=seed,
            width=cw,
            height=ch,
            prefix="StableCraft",
            ref_boost=ref_boost,
            grounding_px=grounding_px,
            loras=loras,
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
        image = images[0]
        try:
            result = comfy.download(image)
        finally:
            comfy.cleanup(image)
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
        clean_recent_files(control)
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
            save_composite(
                control, automation_root, run_abs / "after.png", orig_index
            )
            print("Preview:   ", run_abs / "after.png")

        print("Done.")
    except (ControlError, ComfyError, requests.RequestException) as exc:
        print("ERROR:", exc, file=sys.stderr)
        comfy.interrupt()
        raise SystemExit(1)
    finally:
        if result_doc_index is not None:
            control.close_quietly(result_doc_index)
        clean_recent_files(control)
        control.close_socket()


if __name__ == "__main__":
    main()
