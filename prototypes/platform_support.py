"""Small cross-platform helpers for launching and locating ComfyUI.

Windows keeps its existing batch/PowerShell behaviour.  These helpers cover the
POSIX side (Linux) without importing anything outside the standard library,
except psutil which is only needed to stop a process on Linux.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any

IS_WINDOWS = os.name == "nt"


def comfyui_manageable(cfg: dict[str, Any]) -> bool:
    """When false, ComfyUI is managed by Desktop/another service."""
    return bool(cfg.get("comfyui", {}).get("manage", True))


def comfyui_app_dir(root: Path | None) -> Path | None:
    """Return the folder that contains ComfyUI/main.py.

    Windows portable roots contain a ``ComfyUI`` subfolder.  Linux git/manual
    installs usually point directly at the clone.
    """
    if root is None:
        return None
    nested = root / "ComfyUI"
    if (nested / "main.py").exists():
        return nested
    if (root / "main.py").exists():
        return root
    return nested if nested.is_dir() else root


def comfyui_python(root: Path | None, configured: str = "") -> Path | None:
    value = str(configured or "").strip()
    if value:
        path = Path(value)
        if path.exists():
            return path
        return None
    if root is None:
        return None
    candidates = (
        root / "python_embeded" / "python.exe",
        root / "python_embeded" / "bin" / "python",
        root / "standalone-env" / "bin" / "python",
        root / "ComfyUI" / "standalone-env" / "bin" / "python",
        root / "ComfyUI" / ".venv" / "bin" / "python",
        root / ".venv" / "bin" / "python",
        root / "ComfyUI" / "venv" / "bin" / "python",
        root / "venv" / "bin" / "python",
        root / "ComfyUI" / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def comfyui_main(root: Path | None) -> Path | None:
    app_dir = comfyui_app_dir(root)
    if app_dir is None:
        return None
    main = app_dir / "main.py"
    return main if main.exists() else None


def comfyui_start_argv(
    cfg: dict[str, Any],
    python: Path | None,
    root: Path | None,
    start_command: Path | None = None,
) -> tuple[list[str] | None, Path]:
    """Build a POSIX command for ComfyUI and its working directory."""
    section = cfg.get("comfyui", {})
    endpoint = str(section.get("endpoint", "http://127.0.0.1:8188"))
    host = "127.0.0.1"
    port = 8188
    try:
        from urllib.parse import urlparse

        parsed = urlparse(endpoint)
        host = parsed.hostname or host
        port = parsed.port or port
    except Exception:  # noqa: BLE001
        pass

    if start_command is not None and start_command.exists():
        suffix = start_command.suffix.lower()
        if suffix in {".sh", ".bash"}:
            if os.access(start_command, os.X_OK):
                return [str(start_command)], start_command.parent
            shell = shutil.which("bash") or shutil.which("sh")
            if shell:
                return [shell, str(start_command)], start_command.parent
            return None, start_command.parent
        if suffix == ".py":
            if python is None:
                return None, start_command.parent
            return [str(python), str(start_command)], start_command.parent
        if os.access(start_command, os.X_OK):
            return [str(start_command)], start_command.parent
        return None, start_command.parent

    main = comfyui_main(root)
    if main is None or python is None:
        return None, root or Path.cwd()
    argv = [str(python), str(main)]
    if host in {"127.0.0.1", "localhost", "::1"}:
        argv.extend(["--port", str(port), "--disable-auto-launch"])
    return argv, main.parent


def start_comfyui_process(
    cfg: dict[str, Any],
    python: Path | None,
    root: Path | None,
    start_command: Path | None = None,
    *,
    log_path: Path | None = None,
) -> subprocess.Popen[Any]:
    argv, cwd = comfyui_start_argv(cfg, python, root, start_command)
    if not argv:
        raise RuntimeError(
            "Impossible de trouver ComfyUI/main.py ou un start_command exécutable.\n"
            "Renseigne [comfyui] root, python et start_command dans config.toml."
        )
    log = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("a", encoding="utf-8")
    try:
        return subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=log if log is not None else subprocess.DEVNULL,
            stderr=subprocess.STDOUT if log is not None else subprocess.DEVNULL,
            start_new_session=True,
        )
    finally:
        if log is not None:
            log.close()


def find_listening_pid(port: int) -> int | None:
    try:
        import psutil  # noqa: PLC0415
    except ImportError:
        return None
    try:
        for connection in psutil.net_connections(kind="inet"):
            if (
                connection.laddr
                and connection.laddr.port == int(port)
                and connection.status == psutil.CONN_LISTEN
                and connection.pid
            ):
                return int(connection.pid)
    except (psutil.Error, OSError):
        return None
    return None


def terminate_pid(pid: int, timeout: float = 10.0) -> bool:
    try:
        import psutil  # noqa: PLC0415

        process = psutil.Process(int(pid))
        process.terminate()
        process.wait(timeout=timeout)
        return True
    except ImportError:
        try:
            os.kill(int(pid), signal.SIGTERM)
            return True
        except OSError:
            return False
    except Exception:  # noqa: BLE001
        return False


def stop_comfyui_port(port: int) -> bool:
    pid = find_listening_pid(port)
    if pid is None:
        return False
    return terminate_pid(pid)


def open_path(path: Path) -> None:
    """Open a file or folder with the desktop's default handler."""
    if IS_WINDOWS:
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    opener = shutil.which("xdg-open") or shutil.which("gio")
    if not opener:
        raise RuntimeError("xdg-open introuvable.")
    if Path(opener).name == "gio":
        subprocess.Popen([opener, "open", str(path)])
    else:
        subprocess.Popen([opener, str(path)])
