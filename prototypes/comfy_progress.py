"""Minimal ComfyUI websocket progress client (stdlib only).

ComfyUI reports sampler progress over ``/ws``.  This module keeps a small
websocket implementation so the bridge does not need a new dependency, and
turns the node events into a single, weighted progress value for the UI.

The messages used here are:

* ``execution_start``, ``execution_cached``, ``executing``, ``executed``
* ``progress_state`` (recent ComfyUI) and ``progress`` (older versions)
* ``execution_success``, ``execution_error``, ``execution_interrupted``

Only the sampler exposes fine-grained progress.  Text encoders and the VAE are
short nodes, so their share of the bar advances when the node finishes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import threading
import time
import urllib.parse
from typing import Any, Callable

# Stage order and weights.  Weights are renormalised over the stages that
# actually exist in the workflow, so a profile without a separate text node
# still reaches 100%.
STAGE_ORDER = ("Chargement", "Text Encoder", "Sampler", "VAE Decode")
STAGE_WEIGHTS = {
    "Chargement": 0.05,
    "Text Encoder": 0.10,
    "Sampler": 0.80,
    "VAE Decode": 0.05,
}

TEXT_ENCODER_TYPES = (
    "CLIPTextEncode",
    "TextEncode",
    "GroundedEncode",
    "T5TextEncode",
)


def stage_for_class(class_type: str) -> str:
    """Map a ComfyUI class_type to one of the four visible stages."""
    name = str(class_type or "")
    if "KSampler" in name or "SamplerCustom" in name or name.endswith("Sampler"):
        return "Sampler"
    if "VAEDecode" in name:
        return "VAE Decode"
    if any(token in name for token in TEXT_ENCODER_TYPES):
        return "Text Encoder"
    if "PreviewImage" in name or "SaveImage" in name:
        # Draw the preview under the VAE stage rather than adding a useless
        # 100% stage after decoding.
        return "VAE Decode"
    return "Chargement"


class ProgressTracker:
    """Track one ComfyUI prompt and emit weighted progress dictionaries."""

    def __init__(
        self,
        workflow: dict[str, Any],
        prompt_id: str,
        emit: Callable[[dict[str, Any]], None],
        *,
        scope: str = "generate",
        index: int = 0,
        count: int = 1,
    ) -> None:
        self.workflow = workflow or {}
        self.prompt_id = str(prompt_id or "")
        self.emit = emit
        self.scope = scope
        self.index = max(0, int(index))
        self.count = max(1, int(count))
        self.states: dict[str, str] = {}
        self.values: dict[str, tuple[float, float]] = {}
        self.node_stage: dict[str, str] = {}
        self.stages: dict[str, list[str]] = {}
        self.current_node: str | None = None
        self.current_stage = "Chargement"
        self.last_fraction = 0.0
        self.last_sent: tuple[str, int, bool] | None = None
        self.finished = False

        for node_id, node in self.workflow.items():
            if not isinstance(node, dict):
                continue
            stage = stage_for_class(str(node.get("class_type", "")))
            self.node_stage[str(node_id)] = stage
            self.states[str(node_id)] = "pending"
            self.values[str(node_id)] = (0.0, 1.0)
            self.stages.setdefault(stage, []).append(str(node_id))

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle(self, message: dict[str, Any]) -> None:
        kind = str(message.get("type") or "")
        data = message.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        if kind not in {"status", "feature_flags"}:
            prompt_id = data.get("prompt_id")
            if prompt_id is not None and str(prompt_id) != self.prompt_id:
                return

        if kind == "execution_start":
            self._reset()
        elif kind == "execution_cached":
            for node in data.get("nodes") or []:
                self._mark_finished(str(node))
            self._emit()
        elif kind == "executing":
            node = data.get("node")
            if node is None:
                # ComfyUI sends a final executing(null) after the last node.
                self._finish_all()
            else:
                node = str(node)
                if self.current_node and self.current_node != node:
                    self._mark_finished(self.current_node)
                self.current_node = node
                self.current_stage = self.node_stage.get(node, "Chargement")
                if self.states.get(node) != "finished":
                    self.states[node] = "running"
                self._emit()
        elif kind == "progress_state":
            nodes = data.get("nodes") or {}
            if isinstance(nodes, dict):
                for node_id, state in nodes.items():
                    if not isinstance(state, dict):
                        continue
                    node_id = str(node_id)
                    status = str(state.get("state") or "pending")
                    self.states[node_id] = status
                    try:
                        value = float(state.get("value", 0.0))
                        maximum = float(state.get("max", 1.0))
                    except (TypeError, ValueError):
                        value, maximum = 0.0, 1.0
                    self.values[node_id] = (value, max(1.0, maximum))
                    if status == "running":
                        self.current_node = node_id
                        self.current_stage = self.node_stage.get(node_id, self.current_stage)
            self._emit()
        elif kind == "progress":
            node = str(data.get("node") or self.current_node or "")
            if node:
                self.current_node = node
                self.current_stage = self.node_stage.get(node, self.current_stage)
                if self.states.get(node) != "finished":
                    self.states[node] = "running"
                try:
                    value = float(data.get("value", 0.0))
                    maximum = float(data.get("max", 1.0))
                except (TypeError, ValueError):
                    value, maximum = 0.0, 1.0
                self.values[node] = (value, max(1.0, maximum))
            self._emit()
        elif kind == "executed":
            self._mark_finished(str(data.get("node") or ""))
            self._emit()
        elif kind == "execution_success":
            self._finish_all()
        elif kind == "execution_error":
            if self.current_node:
                self.states[self.current_node] = "error"
            self._emit()
        elif kind == "execution_interrupted":
            if self.current_node:
                self.states[self.current_node] = "error"
            self._emit()

    def _reset(self) -> None:
        for node_id in self.states:
            self.states[node_id] = "pending"
            self.values[node_id] = (0.0, 1.0)
        self.current_node = None
        self.current_stage = "Chargement"
        self.last_fraction = 0.0
        self.last_sent = None
        self.finished = False
        self._emit()

    def _mark_finished(self, node_id: str) -> None:
        if not node_id or node_id not in self.states:
            return
        self.states[node_id] = "finished"
        maximum = self.values.get(node_id, (0.0, 1.0))[1]
        self.values[node_id] = (maximum, maximum)

    def _finish_all(self) -> None:
        for node_id in self.states:
            self._mark_finished(node_id)
        self.finished = True
        self.last_fraction = 1.0
        self._emit(force=True)

    # ------------------------------------------------------------------
    # Computation / output
    # ------------------------------------------------------------------

    def _fraction_for_stage(self, stage: str) -> float:
        nodes = self.stages.get(stage) or []
        if not nodes:
            return 0.0
        done = 0.0
        for node_id in nodes:
            state = self.states.get(node_id, "pending")
            if state in {"finished", "error"}:
                done += 1.0
            elif state == "running":
                value, maximum = self.values.get(node_id, (0.0, 1.0))
                done += max(0.0, min(1.0, value / maximum if maximum else 0.0))
        return max(0.0, min(1.0, done / len(nodes)))

    def _image_fraction(self) -> float:
        weights = {
            stage: STAGE_WEIGHTS.get(stage, 0.05)
            for stage in self.stages
            if self.stages[stage]
        }
        total = sum(weights.values())
        if total <= 0:
            return 0.0
        fraction = sum(
            weights[stage] * self._fraction_for_stage(stage) for stage in weights
        ) / total
        # Keep the bar monotonic while nodes finish out of order.
        self.last_fraction = max(self.last_fraction, max(0.0, min(1.0, fraction)))
        return self.last_fraction

    def _emit(self, force: bool = False) -> None:
        if self.finished:
            fraction = 1.0
        else:
            fraction = self._image_fraction()
        percent = int(round(100.0 * (self.index + fraction) / self.count))
        stage = self.current_stage or "Chargement"
        percent = max(0, min(100, percent))
        token = (stage, percent, self.finished)
        if not force and token == self.last_sent:
            return
        self.last_sent = token
        self.emit(
            {
                "scope": self.scope,
                "index": self.index + 1,
                "count": self.count,
                "stage": stage,
                "percent": percent,
                "stage_percent": int(round(fraction * 100.0)),
                "finished": self.finished,
            }
        )


class MiniWebSocket:
    """Small RFC 6455 client used for ComfyUI's progress stream."""

    _GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(
        self,
        endpoint: str,
        client_id: str,
        on_message: Callable[[dict[str, Any]], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.endpoint = str(endpoint).rstrip("/")
        self.client_id = str(client_id)
        self.on_message = on_message
        self.on_error = on_error
        self.sock: socket.socket | ssl.SSLSocket | None = None
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.connected = False

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="comfy-progress", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        sock = self.sock
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        thread = self.thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.endpoint)
            secure = parsed.scheme in {"https", "wss"}
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or (443 if secure else 80)
            path = (parsed.path or "").rstrip("/") + "/ws"
            query = urllib.parse.urlencode({"clientId": self.client_id})
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            host_header = host if port in (80, 443) else f"{host}:{port}"

            raw = socket.create_connection((host, port), timeout=5.0)
            if secure:
                context = ssl.create_default_context()
                raw = context.wrap_socket(raw, server_hostname=host)
            raw.settimeout(5.0)
            self.sock = raw
            request = (
                f"GET {path}?{query} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "\r\n"
            )
            raw.sendall(request.encode("ascii"))
            response = b""
            while b"\r\n\r\n" not in response:
                chunk = raw.recv(4096)
                if not chunk:
                    raise ConnectionError("websocket closed during handshake")
                response += chunk
                if len(response) > 65536:
                    raise ConnectionError("websocket handshake too large")
            header = response.split(b"\r\n\r\n", 1)[0].decode("latin-1", "replace")
            if " 101 " not in header.split("\r\n", 1)[0]:
                raise ConnectionError(f"websocket upgrade refused: {header.splitlines()[0]}")
            expected = base64.b64encode(
                hashlib.sha1((key + self._GUID).encode("ascii")).digest()
            ).decode("ascii")
            if f"sec-websocket-accept: {expected}".lower() not in header.lower():
                raise ConnectionError("websocket accept key mismatch")

            self.connected = True
            self._loop()
        except Exception as exc:  # noqa: BLE001 - progress must never kill generation
            if not self.stop_event.is_set() and self.on_error is not None:
                self.on_error(str(exc))
        finally:
            self.connected = False
            sock = self.sock
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

    def _loop(self) -> None:
        frag_opcode: int | None = None
        frag_payload = bytearray()
        while not self.stop_event.is_set():
            sock = self.sock
            if sock is None:
                return
            try:
                first = self._recv_exact(2)
                b0, b1 = first[0], first[1]
                fin = bool(b0 & 0x80)
                opcode = b0 & 0x0F
                masked = bool(b1 & 0x80)
                length = b1 & 0x7F
                if length == 126:
                    length = struct.unpack("!H", self._recv_exact(2))[0]
                elif length == 127:
                    length = struct.unpack("!Q", self._recv_exact(8))[0]
                if length > 32 * 1024 * 1024:
                    raise ConnectionError("websocket frame too large")
                mask = self._recv_exact(4) if masked else b""
                payload = self._recv_exact(length) if length else b""
                if masked and mask:
                    payload = bytes(
                        byte ^ mask[index % 4] for index, byte in enumerate(payload)
                    )

                if opcode == 0x8:  # close
                    return
                if opcode == 0x9:  # ping
                    self._send_frame(0xA, payload)
                    continue
                if opcode == 0xA:  # pong
                    continue
                if opcode == 0x2:  # binary (latent previews) - ignore
                    continue

                if opcode == 0x0:
                    if frag_opcode is None:
                        continue
                    frag_payload.extend(payload)
                    if fin:
                        self._dispatch(frag_opcode, bytes(frag_payload))
                        frag_opcode = None
                        frag_payload.clear()
                elif opcode == 0x1:
                    if fin:
                        self._dispatch(opcode, payload)
                    else:
                        frag_opcode = opcode
                        frag_payload = bytearray(payload)
            except socket.timeout:
                continue
            except OSError:
                return

    def _dispatch(self, opcode: int, payload: bytes) -> None:
        if opcode != 0x1:
            return
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(message, dict):
            try:
                self.on_message(message)
            except Exception:  # noqa: BLE001 - never break the reader
                pass

    def _recv_exact(self, count: int) -> bytes:
        sock = self.sock
        if sock is None:
            raise ConnectionError("websocket closed")
        data = bytearray()
        while len(data) < count:
            chunk = sock.recv(count - len(data))
            if not chunk:
                raise ConnectionError("websocket closed")
            data.extend(chunk)
        return bytes(data)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        sock = self.sock
        if sock is None:
            return
        length = len(payload)
        header = bytearray([0x80 | opcode])
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        try:
            sock.sendall(bytes(header) + masked)
        except OSError:
            pass


class ComfyProgress:
    """Own the websocket and route messages to the current prompt tracker."""

    def __init__(
        self,
        endpoint: str,
        client_id: str,
        emit: Callable[[dict[str, Any]], None],
    ) -> None:
        self.endpoint = endpoint
        self.client_id = client_id
        self.emit = emit
        self.tracker: ProgressTracker | None = None
        self._lock = threading.Lock()
        self.available = True
        self.ws = MiniWebSocket(endpoint, client_id, self._message, self._error)
        self.ws.start()

    def track(
        self,
        workflow: dict[str, Any],
        prompt_id: str,
        *,
        scope: str = "generate",
        index: int = 0,
        count: int = 1,
    ) -> None:
        tracker = ProgressTracker(
            workflow,
            prompt_id,
            self.emit,
            scope=scope,
            index=index,
            count=count,
        )
        with self._lock:
            self.tracker = tracker
        if not self.available:
            self.emit(
                {
                    "scope": tracker.scope,
                    "index": tracker.index + 1,
                    "count": tracker.count,
                    "stage": "Génération",
                    "percent": int(round(100.0 * tracker.index / tracker.count)),
                    "stage_percent": 0,
                    "unavailable": True,
                }
            )
            return
        tracker._emit(force=True)

    def stop(self) -> None:
        self.ws.stop()

    def _error(self, message: str) -> None:
        self.available = False
        # Tell the UI that the bar cannot be driven by ComfyUI.  The bridge
        # keeps polling /history and the generation continues normally.
        with self._lock:
            tracker = self.tracker
        if tracker is not None:
            self.emit(
                {
                    "scope": tracker.scope,
                    "index": tracker.index + 1,
                    "count": tracker.count,
                    "stage": "Génération",
                    "percent": int(round(100.0 * tracker.index / tracker.count)),
                    "stage_percent": 0,
                    "unavailable": True,
                }
            )

    def _message(self, message: dict[str, Any]) -> None:
        with self._lock:
            tracker = self.tracker
        if tracker is not None:
            tracker.handle(message)
