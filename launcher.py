"""StableCraft one-click launcher.

Double-click StableCraft.bat. This script:

1. reads config.toml;
2. checks the required paths (PhotoCraft, ComfyUI, Python UI);
3. starts ComfyUI if its port is closed;
4. starts PhotoCraft with the control channel if port 7878 is closed;
5. starts the Tkinter UI.

Missing models are not blocking: the UI reports them and disables Generate.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.toml"
USER_DIR = ROOT / "user"
MODELS_DIR = ROOT / "models"
LOG_DIR = USER_DIR / "logs"
LOG_PATH = LOG_DIR / "launcher.log"
UI_LOG_PATH = LOG_DIR / "ui.log"
LEGACY_SESSIONS = ROOT / ".runtime" / "automation" / "stablecraft" / "sessions"

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_NEW_CONSOLE = 0x00000010 if os.name == "nt" else 0


def log(message: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {message}"
    print(line)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def show_error(title: str, message: str) -> None:
    log(f"ERREUR: {title} — {message}")
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
        except Exception:  # noqa: BLE001
            print(message)


def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_port(host: str, port: int, timeout: float, label: str) -> bool:
    deadline = time.time() + timeout
    last = 0
    while time.time() < deadline:
        if port_open(host, port):
            return True
        now = int(time.time())
        if now - last >= 5:
            print(f"  ... attente de {label} ({int(deadline - time.time())}s)")
            last = now
        time.sleep(1)
    return port_open(host, port)


def as_path(value: str, base: Path = ROOT) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path)


def load_config() -> dict[str, Any] | None:
    if not CONFIG_PATH.exists():
        show_error(
            "StableCraft — config.toml manquant",
            f"Fichier introuvable :\n{CONFIG_PATH}\n\n"
            "Copie config.example.toml en config.toml, ou lance installer\\install.ps1.",
        )
        return None
    try:
        with CONFIG_PATH.open("rb") as f:
            return tomllib.load(f)
    except Exception as exc:  # noqa: BLE001
        show_error(
            "StableCraft — config.toml invalide",
            f"{CONFIG_PATH}\n\n{exc}\n\nCorrige le fichier ou repart de config.example.toml.",
        )
        return None


def find_photocraft(cfg: dict[str, Any]) -> tuple[Path | None, str | None]:
    configured = str(cfg.get("photocraft", {}).get("executable", "") or "")
    if configured:
        path = as_path(configured)
        if path.exists():
            return path, None
        return None, f"[photocraft] executable introuvable :\n{path}"

    candidates = [
        Path("D:/Programmes/photocraft-0.14.0-windows-x64-portable/photocraft.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/PhotoCraft/photocraft.exe",
        Path("C:/Program Files/PhotoCraft/photocraft.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate, None

    bases = [
        Path("D:/Programmes"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path("C:/Program Files"),
    ]
    for base in bases:
        if not base.exists():
            continue
        for pattern in ("photocraft*/photocraft.exe", "PhotoCraft/photocraft.exe", "photocraft.exe"):
            for found in base.glob(pattern):
                if found.exists():
                    return found, None
    return None, (
        "PhotoCraft introuvable.\n\n"
        "Renseigne [photocraft] executable dans config.toml, par exemple :\n"
        "executable = \"D:/Programmes/photocraft-0.14.0-windows-x64-portable/photocraft.exe\""
    )


def find_comfyui(cfg: dict[str, Any]) -> tuple[Path | None, Path | None, Path | None, str | None]:
    section = cfg.get("comfyui", {})
    root_value = str(section.get("root", "") or "")
    start_value = str(section.get("start_command", "") or "")
    python_value = str(section.get("python", "") or "")

    root: Path | None = None
    if root_value:
        root = as_path(root_value)
        if not root.exists():
            return None, None, None, f"[comfyui] root introuvable :\n{root}"

    start = as_path(start_value) if start_value else (root / "run_nvidia_gpu.bat" if root else None)
    python = as_path(python_value) if python_value else (root / "python_embeded/python.exe" if root else None)

    if start is None or python is None:
        candidates = [
            Path("F:/ComfyUI_windows_portable"),
            Path("C:/ComfyUI_windows_portable"),
            Path("D:/ComfyUI_windows_portable"),
            Path("E:/ComfyUI_windows_portable"),
        ]
        for drive in ("F:/", "C:/", "D:/", "E:/"):
            base = Path(drive)
            if base.exists():
                candidates.extend(p for p in base.glob("ComfyUI*") if p.is_dir())
        for candidate in candidates:
            if not candidate.exists():
                continue
            candidate_start = candidate / "run_nvidia_gpu.bat"
            candidate_python = candidate / "python_embeded/python.exe"
            if candidate_start.exists() and candidate_python.exists():
                root = candidate
                start = candidate_start
                python = candidate_python
                break

    if start is None or not start.exists():
        return None, None, None, (
            "ComfyUI introuvable.\n\n"
            "Renseigne [comfyui] root dans config.toml, par exemple :\n"
            "root = \"F:/ComfyUI_windows_portable\""
        )
    if python is None or not python.exists():
        return None, None, None, (
            "Python embarqué de ComfyUI introuvable.\n\n"
            "Renseigne [comfyui] python dans config.toml, par exemple :\n"
            "python = \"F:/ComfyUI_windows_portable/python_embeded/python.exe\""
        )
    return start, python, root, None


def find_ui_python(cfg: dict[str, Any]) -> tuple[Path | None, Path | None, str | None]:
    configured = str(cfg.get("app", {}).get("python_ui", "") or "")
    base_python = as_path(configured) if configured else Path(sys.executable)
    if not base_python.exists():
        return None, None, f"Python UI introuvable :\n{base_python}"
    try:
        check = subprocess.run(
            [str(base_python), "-c", "import tkinter"],
            capture_output=True,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        if check.returncode != 0:
            return None, None, (
                f"Tkinter est absent de {base_python}.\n\n"
                "Installe Python 3.11+ depuis python.org (coche tcl/tk et pip)."
            )
    except Exception as exc:  # noqa: BLE001
        return None, None, f"Impossible de tester {base_python} :\n{exc}"
    pythonw = base_python.with_name("pythonw.exe")
    return base_python, (pythonw if pythonw.exists() else base_python), None


def migrate_legacy_sessions(target: Path, log_prefix: str = "") -> int:
    """Copy old .runtime sessions into the configured sessions folder."""
    if not LEGACY_SESSIONS.exists():
        return 0
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source in LEGACY_SESSIONS.iterdir():
        if not source.is_dir() or not (source / "session.json").exists():
            continue
        destination = target / source.name
        if destination.exists():
            continue
        try:
            shutil.copytree(source, destination)
            copied += 1
        except OSError as exc:
            log(f"{log_prefix}Migration de {source.name} impossible : {exc}")
    if copied:
        log(f"{log_prefix}{copied} session(s) migrée(s) vers {target}")
    return copied


def photocraft_running_without_control(port: int) -> bool:
    if os.name != "nt":
        return False
    if port_open("127.0.0.1", port):
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq photocraft.exe"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        return "photocraft.exe" in result.stdout.lower()
    except Exception:  # noqa: BLE001
        return False


def configured_sessions_dir(cfg: dict[str, Any]) -> Path:
    configured = str(cfg.get("app", {}).get("sessions_dir", "") or "")
    return as_path(configured) if configured else USER_DIR / "sessions"


def configured_models_dir(cfg: dict[str, Any]) -> Path:
    configured = str(cfg.get("models", {}).get("store_dir", "") or "")
    return as_path(configured) if configured else MODELS_DIR


def main() -> int:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log("=== StableCraft launcher ===")

    cfg = load_config()
    if cfg is None:
        return 1

    sessions = configured_sessions_dir(cfg)
    sessions.mkdir(parents=True, exist_ok=True)
    configured_models_dir(cfg).mkdir(parents=True, exist_ok=True)
    migrate_legacy_sessions(sessions)

    errors: list[str] = []

    photocraft, error = find_photocraft(cfg)
    if error:
        errors.append(error)

    start_command, comfy_python, comfy_root, error = find_comfyui(cfg)
    if error:
        errors.append(error)

    _ui_python, ui_pythonw, error = find_ui_python(cfg)
    if error:
        errors.append(error)

    if errors or photocraft is None or start_command is None or comfy_python is None or ui_pythonw is None:
        show_error(
            "StableCraft — chemins manquants",
            "StableCraft ne peut pas démarrer :\n\n" + "\n\n".join(errors) +
            "\n\nCorrige config.toml puis relance StableCraft.bat.",
        )
        return 1

    endpoint = str(cfg.get("comfyui", {}).get("endpoint", "http://127.0.0.1:12452"))
    parsed = urllib.parse.urlparse(endpoint)
    comfy_host = parsed.hostname or "127.0.0.1"
    comfy_port = parsed.port or 8188
    is_local = comfy_host in {"127.0.0.1", "localhost", "::1"}

    if not port_open(comfy_host, comfy_port):
        if not is_local:
            show_error(
                "StableCraft — ComfyUI injoignable",
                f"Le ComfyUI distant {endpoint} ne répond pas.\n\n"
                "Démarre-le ou corrige [comfyui] endpoint dans config.toml.",
            )
            return 1
        log(f"ComfyUI n'écoute pas sur {comfy_host}:{comfy_port}; démarrage…")
        try:
            subprocess.Popen(
                ["cmd", "/c", str(start_command)],
                cwd=str(start_command.parent),
                creationflags=CREATE_NEW_CONSOLE,
            )
        except Exception as exc:  # noqa: BLE001
            show_error("StableCraft — ComfyUI", f"Impossible de lancer ComfyUI :\n{exc}")
            return 1
        if not wait_port(comfy_host, comfy_port, 240, "ComfyUI"):
            show_error(
                "StableCraft — ComfyUI",
                "ComfyUI n'a pas démarré dans les 4 minutes.\n\n"
                f"Lance-le manuellement :\n{start_command}\n\n"
                f"Puis relance StableCraft.bat. Détails : {LOG_PATH}",
            )
            return 1
    else:
        log("ComfyUI est déjà lancé.")

    photocraft_cfg = cfg.get("photocraft", {})
    host = str(photocraft_cfg.get("control_host", "127.0.0.1"))
    port = int(photocraft_cfg.get("control_port", 7878))
    token = as_path(
        str(photocraft_cfg.get("control_token_file", "") or str(USER_DIR / "control.token"))
    )
    automation = as_path(
        str(photocraft_cfg.get("automation_root", "") or str(USER_DIR))
    )

    if port_open(host, port) and not token.exists():
        show_error(
            "StableCraft — PhotoCraft à redémarrer",
            "PhotoCraft tourne déjà, mais avec une ancienne configuration "
            "(le fichier de contrôle n'est plus au même endroit).\n\n"
            "Ferme complètement PhotoCraft, puis relance StableCraft.bat.\n\n"
            f"Fichier attendu :\n{token}",
        )
        return 1

    if not port_open(host, port):
        if photocraft_running_without_control(port):
            show_error(
                "StableCraft — PhotoCraft déjà ouvert",
                "PhotoCraft est déjà ouvert, mais sans le control channel.\n\n"
                "Ferme PhotoCraft complètement, puis relance StableCraft.bat.",
            )
            return 1
        log(f"PhotoCraft n'écoute pas sur {host}:{port}; démarrage avec control channel…")
        token.parent.mkdir(parents=True, exist_ok=True)
        automation.mkdir(parents=True, exist_ok=True)
        args = [
            str(photocraft),
            "--control",
            str(port),
            "--control-token-file",
            str(token),
            "--automation-read-root",
            str(automation),
            "--automation-write-root",
            str(automation),
        ]
        try:
            subprocess.Popen(args, cwd=str(photocraft.parent))
        except Exception as exc:  # noqa: BLE001
            show_error("StableCraft — PhotoCraft", f"Impossible de lancer PhotoCraft :\n{exc}")
            return 1
        if not wait_port(host, port, 90, "PhotoCraft"):
            show_error(
                "StableCraft — PhotoCraft",
                "PhotoCraft n'a pas exposé le control channel.\n\n"
                "Ferme PhotoCraft s'il est déjà ouvert, puis relance StableCraft.bat.\n"
                f"Détails : {LOG_PATH}",
            )
            return 1
    else:
        log("PhotoCraft control channel déjà actif.")

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["STABLECRAFT_COMFY_PYTHON"] = str(comfy_python)
    comfy_root_for_env = comfy_root or (
        start_command.parent if start_command is not None else None
    )
    if comfy_root_for_env is not None:
        env["STABLECRAFT_COMFY_ROOT"] = str(comfy_root_for_env)

    UI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ui_log = UI_LOG_PATH.open("a", encoding="utf-8")
    ui_log.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] launch\n")
    ui_log.flush()
    creation = CREATE_NO_WINDOW if ui_pythonw.name.lower().startswith("pythonw") else 0
    log("Démarrage de l'UI StableCraft…")
    try:
        ui = subprocess.Popen(
            [str(ui_pythonw), str(ROOT / "prototypes/stablecraft_ui.py"), "--config", str(CONFIG_PATH)],
            cwd=str(ROOT),
            env=env,
            stdout=ui_log,
            stderr=subprocess.STDOUT,
            creationflags=creation,
        )
    except Exception as exc:  # noqa: BLE001
        show_error("StableCraft — UI", f"Impossible de lancer l'UI :\n{exc}")
        return 1

    time.sleep(2)
    if ui.poll() is not None:
        show_error(
            "StableCraft — UI",
            f"L'UI s'est fermée immédiatement.\n\n"
            f"Journal : {UI_LOG_PATH}\n\n"
            f"Lance dans un terminal pour voir l'erreur :\n"
            f"{ui_pythonw} prototypes\\stablecraft_ui.py --config config.toml",
        )
        return 1

    log("StableCraft est lancé.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        show_error("StableCraft — erreur inattendue", str(exc))
        sys.exit(1)
