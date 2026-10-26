"""Sonde bornée du canal de contrôle PhotoCraft. Lancer depuis ~/src/StableCraft.
Usage: diag_canal.py [methode ...]  (défaut : engine.commands ui.inspect)"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path("prototypes").resolve()))
from control_client import ControlClient, read_token  # noqa: E402

for method in sys.argv[1:] or ["engine.commands", "ui.inspect"]:
    t = time.time()
    try:
        c = ControlClient("127.0.0.1", 7990, read_token(Path("user/control.token")), timeout=6)
        r = c.request(method)
        if isinstance(r, dict) and "session" in r:
            info = f"docs={[d.get('name') for d in r['session'].get('documents', [])]} dialogs={r.get('dialogs')}"
        elif isinstance(r, (list, dict)):
            info = f"{type(r).__name__} len={len(r)}"
        else:
            info = str(r)[:120]
        print(f"{method}: OK {time.time() - t:.2f}s {info}")
        c.close_socket()
    except Exception as exc:  # noqa: BLE001
        print(f"{method}: KO {time.time() - t:.2f}s {type(exc).__name__}: {str(exc)[:150]}")
