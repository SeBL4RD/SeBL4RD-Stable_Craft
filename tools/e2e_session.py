"""E2E StableCraft on Linux, session path (what the UI runs).
Run from the StableCraft folder with ComfyUI's Python:
  e2e_session.py IMAGE PROFILE PROMPT X Y W H"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prototypes"))
os.chdir(Path(__file__).resolve().parents[1])
from control_client import ControlClient, read_token  # noqa: E402

image, profile, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
x, y, sw, sh = (int(v) for v in sys.argv[4:8])
user = Path("user").resolve()
src = user / "e2e" / f"session-{profile}.png"
src.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(image, src)

c = ControlClient("127.0.0.1", 7990, read_token(user / "control.token"))
for i in reversed(range(len(c.documents()))):
    c.close_quietly(i)
c.request("app.open", {"path": str(src)})
time.sleep(1.5)
c.execute("select.rect", {"x": x, "y": y, "width": sw, "height": sh})
before = c.inspect()
print(json.dumps({"doc": before.get("name"), "selection": before.get("selectionBounds"),
                  "layers_before": [l.get("name") for l in before.get("layers", [])]}))
c.close_socket()

env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
cmd = [sys.executable, "prototypes/bridge_cli.py", "--config", "config.toml", "--profile", profile,
       "--mode", "edit", "--prompt", prompt, "--seed", "424242", "--save-preview", "--session-mode"]
t0 = time.time()
r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=900)
out = "\n".join(l for l in r.stdout.splitlines() if "sampling (" not in l)
print(f"--- bridge rc={r.returncode} en {time.time() - t0:.1f} s")
print(out[-1800:])
if r.returncode:
    print("STDERR:", r.stderr[-1800:])

m = re.search(r"queued ([0-9a-f-]{36})", r.stdout)
if m:
    with urllib.request.urlopen(f"http://127.0.0.1:8188/history/{m.group(1)}", timeout=10) as resp:
        hist = json.load(resp)
    graph = list(hist.values())[0]["prompt"][2]
    print("noeuds ComfyUI:", sorted({v["class_type"] for v in graph.values()}))
    for v in graph.values():
        if v["class_type"] == "LoraLoaderModelOnly":
            print("lora:", v["inputs"].get("lora_name"), v["inputs"].get("strength_model"))

c = ControlClient("127.0.0.1", 7990, read_token(user / "control.token"))
after = c.inspect()
print(json.dumps({"layers_after": [(l.get("name"), l.get("hasMask")) for l in after.get("layers", [])]}))
c.close_socket()
sys.exit(r.returncode)
