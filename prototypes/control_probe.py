"""Probe PhotoCraft's control channel.

Usage:
    python prototypes/control_probe.py [--port 7878] [--token PATH]

Requires PhotoCraft to be running with:
    --control 7878 --control-token-file <token>
    --automation-read-root <dir> --automation-write-root <dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from control_client import ControlClient, read_token  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOKEN = ROOT / ".runtime" / "control.token"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7878)
    ap.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    ap.add_argument("--open", dest="open_path", default=None)
    args = ap.parse_args()

    c = ControlClient(args.host, args.port, read_token(args.token))
    print("connected")

    commands = c.request("engine.commands")
    ids = {cmd["id"] for cmd in commands}
    print(f"commands: {len(commands)}")
    required = [
        "document.inspect",
        "document.activate",
        "channel.duplicate",
        "file.close",
        "layer.copyToDocument",
        "layer.layerMask.revealSelection",
        "layer.layerMask.edit",
        "layer.select",
        "select.saveSelection",
        "select.loadSelection",
        "edit.undo",
    ]
    for rid in required:
        print(f"  {rid:42} {'OK' if rid in ids else 'MISSING'}")

    ui = c.request("ui.inspect")
    print("ui keys:", sorted(ui.keys())[:30])
    print("ui.document:", json.dumps(ui.get("document"), indent=2)[:1500] if ui.get("document") else None)

    if args.open_path:
        opened = c.request("app.open", {"path": args.open_path})
        print("opened:", opened)
        print("inspect:", json.dumps(c.execute("document.inspect"), indent=2)[:3000])

    c.close_socket()


if __name__ == "__main__":
    main()
