"""Small cross-platform helpers for launching and locating ComfyUI.

Windows keeps its existing batch/PowerShell behaviour.  These helpers cover the
POSIX side (Linux) without importing anything outside the standard library,
except psutil which is only needed to stop a process on Linux.
"""

from __future__ import annotations

import os
import shlex
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

    extra = section.get("extra_args", [])
    if isinstance(extra, str):
        extra_args = shlex.split(extra)
    elif isinstance(extra, (list, tuple)):
        extra_args = [str(value) for value in extra]
    else:
        extra_args = []

    if start_command is not None and start_command.exists():
        name = start_command.name.lower()
        if name.startswith(("python", "pypy")):
            raise RuntimeError(
                "[comfyui] start_command ne doit pas pointer vers l'interpréteur "
                f"Python ({start_command}).\n"
                "Laisse start_command vide pour utiliser main.py, ou donne un "
                "script .sh."
            )
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
            argv = [str(python), str(start_command)]
            if host in {"127.0.0.1", "localhost", "::1"}:
                argv.extend(["--port", str(port), "--disable-auto-launch"])
            argv.extend(extra_args)
            return argv, start_command.parent
        if os.access(start_command, os.X_OK):
            return [str(start_command)], start_command.parent
        return None, start_command.parent

    main = comfyui_main(root)
    if main is None or python is None:
        return None, root or Path.cwd()
    argv = [str(python), str(main)]
    if host in {"127.0.0.1", "localhost", "::1"}:
        argv.extend(["--port", str(port), "--disable-auto-launch"])
    argv.extend(extra_args)
    return argv, main.parent


def _terminal_command(
    argv: list[str], cwd: Path, log_path: Path | None
) -> list[str] | None:
    """Wrap a command in the desktop's terminal, if one is available."""
    if IS_WINDOWS:
        return None
    if log_path is None:
        return None
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None

    # Use a real script file: terminal emulators sometimes re-parse their
    # arguments through a shell, which would expand $PIPESTATUS too early.
    runtime = log_path.parent.parent / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    script_path = runtime / "comfyui-console.sh"
    command = " ".join(shlex.quote(str(value)) for value in argv)
    script = (
        "#!/usr/bin/env bash\n"
        "set -o pipefail\n"
        f"cd {shlex.quote(str(cwd))} || exit 1\n"
        f"{command} 2>&1 | tee -a {shlex.quote(str(log_path))}\n"
        "status=${PIPESTATUS[0]}\n"
        "if [ \"$status\" -ne 0 ] && [ \"$status\" -ne 130 ] && [ \"$status\" -ne 143 ]; then\n"
        "  echo\n"
        "  echo \"ComfyUI stopped (exit $status). Press Enter to close.\"\n"
        "  read -r\n"
        "fi\n"
        "exit \"$status\"\n"
    )
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o755)

    specs = (
        ("ptyxis", ["--"]),
        ("gnome-terminal", ["--"]),
        ("kgx", ["--"]),
        ("konsole", ["-e"]),
        ("xfce4-terminal", ["-x"]),
        ("xterm", ["-e"]),
        ("alacritty", ["-e"]),
        ("kitty", ["--"]),
        ("wezterm", ["start", "--"]),
    )
    for name, arguments in specs:
        path = shutil.which(name)
        if path:
            return [path, *arguments, "bash", str(script_path)]

    path = shutil.which("x-terminal-emulator")
    if path:
        real_name = Path(path).resolve().name
        if real_name in {"ptyxis", "gnome-terminal", "kgx"}:
            arguments = ["--"]
        elif real_name == "xfce4-terminal":
            arguments = ["-x"]
        elif real_name == "konsole":
            arguments = ["-e"]
        else:
            arguments = ["-e"]
        return [path, *arguments, "bash", str(script_path)]
    return None


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
    section = cfg.get("comfyui", {})
    if bool(section.get("open_console", True)):
        terminal = _terminal_command(argv, cwd, log_path)
        if terminal is not None:
            return subprocess.Popen(
                terminal,
                cwd=str(cwd),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
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
