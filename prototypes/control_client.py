"""Minimal client for PhotoCraft's local control channel.

The protocol is one JSON object per line over TCP. The first request must be
`auth` with the 256-bit token from PhotoCraft's token file.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any


class ControlError(RuntimeError):
    """An error returned by PhotoCraft."""


class ControlClient:
    def __init__(self, host: str, port: int, token: str, timeout: float = 300.0) -> None:
        self.sock = socket.create_connection((host, port), timeout=15)
        self.sock.settimeout(timeout)
        self.file = self.sock.makefile("rwb")
        self.next_id = 0
        self.request("auth", {"token": token})

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.next_id += 1
        message: dict[str, Any] = {"id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.file.write((json.dumps(message) + "\n").encode("utf-8"))
        self.file.flush()
        line = self.file.readline()
        if not line:
            raise ControlError("PhotoCraft closed the control connection")
        reply = json.loads(line)
        if not reply.get("ok"):
            raise ControlError(f"{method}: {reply.get('error')}")
        return reply.get("result")

    def execute(self, command: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("engine.execute", {"command": command, "params": params or {}})

    # Convenience wrappers -------------------------------------------------

    def session(self) -> dict[str, Any]:
        return self.request("ui.inspect")["session"]

    def active_index(self) -> int:
        return int(self.session()["active"])

    def documents(self) -> list[dict[str, Any]]:
        return list(self.session()["documents"])

    def find_document(self, name: str) -> dict[str, Any] | None:
        for doc in self.documents():
            if doc.get("name") == name:
                return doc
        return None

    def inspect(self) -> dict[str, Any]:
        return self.execute("document.inspect")

    def save(self, path: str) -> dict[str, Any]:
        return self.request("app.save", {"path": path})

    def open(self, path: str) -> dict[str, Any]:
        return self.request("app.open", {"path": path})

    def close(self, index: int) -> None:
        self.execute("file.close", {"document": index})

    def close_quietly(self, index: int) -> None:
        try:
            self.close(index)
        except ControlError:
            pass

    def activate(self, index: int) -> None:
        self.execute("document.activate", {"document": index})

    def close_socket(self) -> None:
        try:
            self.file.close()
        finally:
            self.sock.close()

    def __enter__(self) -> "ControlClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close_socket()


def read_token(path: Path) -> str:
    token = path.read_text(encoding="utf-8").strip()
    if len(token) != 64:
        raise ControlError(f"{path} does not contain a 64-character token")
    return token
