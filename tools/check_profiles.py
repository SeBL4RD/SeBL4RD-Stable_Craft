"""Check that every enabled StableCraft profile resolves to files and nodes ComfyUI can see.
Run from the StableCraft folder with ComfyUI's Python: check_profiles.py [config.toml]"""
import json
import sys
import tomllib
from pathlib import Path

import os
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prototypes"))
os.chdir(Path(__file__).resolve().parents[1])
from bridge_cli import ComfyClient, ComfyError, clip_loader_for, unet_loader_for  # noqa: E402
from models_tools import resolve_filename  # noqa: E402

cfg = tomllib.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "config.toml").read_text(encoding="utf-8"))
profiles = json.loads(Path("models.json").read_text(encoding="utf-8"))["profiles"]
comfy = ComfyClient(cfg["comfyui"]["endpoint"])
bad = 0
for name, manifest in profiles.items():
    pcfg = cfg.get("profiles", {}).get(name, {})
    if not pcfg.get("enabled", True):
        print(f"{name:20} desactive")
        continue
    files = {k: resolve_filename(name, k, pcfg, manifest) for k in ("unet", "text_encoder", "vae")}
    checks = [
        (unet_loader_for(files["unet"]), "unet_name", files["unet"]),
        (clip_loader_for(files["text_encoder"]), "clip_name", files["text_encoder"]),
        ("VAELoader", "vae_name", files["vae"]),
    ]
    if (manifest.get("files") or {}).get("lora"):
        files["lora"] = resolve_filename(name, "lora", pcfg, manifest)
        checks.append(("LoraLoaderModelOnly", "lora_name", files["lora"]))
    nodes = []
    if name.startswith("krea2"):
        nodes += ["Krea2EditModelPatch", "Krea2EditGroundedEncode"]
    if name == "qwen_image_21":
        nodes += ["TextEncodeQwenImage21", "QwenImage21Cache"]
    errors = []
    for node, key, value in checks:
        try:
            comfy.require(node, key, value)
        except (ComfyError, Exception) as exc:  # noqa: BLE001
            errors.append(f"{node}.{key}={value}: {str(exc).splitlines()[0]}")
    for node in nodes:
        try:
            comfy.require_node(node)
        except (ComfyError, Exception) as exc:  # noqa: BLE001
            errors.append(f"node {node}: {str(exc).splitlines()[0]}")
    bad += bool(errors)
    print(f"{name:20} {'OK' if not errors else 'KO'}  " + ", ".join(f"{k}={v}" for k, v in files.items()))
    for err in errors:
        print("    ->", err)
sel = Path("user/model_selection.json")
print("model_selection.json:", "PRESENT (prioritaire sur config)" if sel.exists() else "absent")
sys.exit(1 if bad else 0)
