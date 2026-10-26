"""E2E StableCraft on Linux: open an image in PhotoCraft, select a rect, run the bridge, count layers.
Run from the StableCraft folder with ComfyUI's Python:
  e2e.py IMAGE PROFILE PROMPT [--dry-run]"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prototypes"))
os.chdir(Path(__file__).resolve().parents[1])
from control_client import ControlClient, read_token  # noqa: E402

image, profile, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
dry = "--dry-run" in sys.argv
user = Path("user").resolve()
src = user / "e2e" / f"e2e-{profile}.png"
src.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(image, src)

c = ControlClient("127.0.0.1", 7990, read_token(user / "control.token"))
opened = c.request("app.open", {"path": str(src)})
time.sleep(1.5)
doc = c.inspect()
w, h = int(doc["width"]), int(doc["height"])
x, y, sw, sh = w // 3, h // 3, w // 3, h // 3
c.execute("select.rect", {"x": x, "y": y, "width": sw, "height": sh})
before = c.inspect()
layers_before = [l.get("name") for l in before.get("layers", [])]
print(json.dumps({"doc": doc.get("name"), "size": [w, h], "rect": [x, y, sw, sh],
                  "selection": before.get("selectionBounds"), "layers_before": layers_before}))
c.close_socket()

env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
cmd = [sys.executable, "prototypes/bridge_cli.py", "--config", "config.toml", "--profile", profile,
       "--mode", "edit", "--prompt", prompt, "--seed", "424242", "--save-preview"]
if dry:
    cmd.append("--dry-run")
t0 = time.time()
r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=900)
print(f"--- bridge rc={r.returncode} en {time.time() - t0:.1f} s")
print(r.stdout[-2500:])
if r.returncode:
    print("STDERR:", r.stderr[-2500:])

c = ControlClient("127.0.0.1", 7990, read_token(user / "control.token"))
after = c.inspect()
layers_after = [(l.get("name"), bool(l.get("mask") or l.get("hasMask") or l.get("layerMask"))) for l in after.get("layers", [])]
print(json.dumps({"layers_after": layers_after, "n_before": len(layers_before), "n_after": len(layers_after)}))
print("layer keys:", sorted(after.get("layers", [{}])[-1].keys()) if after.get("layers") else None)
c.close_socket()
sys.exit(r.returncode)
