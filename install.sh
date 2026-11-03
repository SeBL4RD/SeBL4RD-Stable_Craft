#!/usr/bin/env bash
# StableCraft installer for Linux.
#
# Supported: Debian/Ubuntu, Fedora/RHEL, Arch. Python 3.11+ and Tkinter are
# required; older distributions are intentionally not supported.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

say() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERREUR: %s\n' "$*" >&2; exit 1; }

if command -v apt-get >/dev/null 2>&1; then
    PKG_CMD="sudo apt install python3 python3-tk python3-venv"
elif command -v dnf >/dev/null 2>&1; then
    PKG_CMD="sudo dnf install python3 python3-tkinter"
elif command -v pacman >/dev/null 2>&1; then
    PKG_CMD="sudo pacman -S python tk"
else
    PKG_CMD=""
fi

if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 est introuvable. Installe Python 3.11+ :
  ${PKG_CMD:-installe Python 3.11+ avec le gestionnaire de paquets de ta distribution}"
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    fail "Python $(python3 -V 2>&1 | cut -d' ' -f2) est trop ancien. StableCraft exige Python 3.11+.
  ${PKG_CMD:-Installe Python 3.11+}"
fi

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    fail "Tkinter est absent. Installe-le :
  ${PKG_CMD:-Installe le paquet Tkinter de ta distribution}"
fi

say "Création du venv StableCraft"
if [ -x ".venv/bin/python" ] && ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    fail "Le .venv existant utilise un Python trop ancien. Supprime .venv puis relance :
  rm -rf .venv && bash install.sh"
fi
if [ ! -x ".venv/bin/python" ]; then
    if ! python3 -m venv .venv; then
        fail "Impossible de créer .venv. Sur Debian/Ubuntu :
  sudo apt install python3-venv"
    fi
fi

say "Installation des dépendances Python (requests, Pillow, psutil)"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r prototypes/requirements.txt

if [ ! -f config.toml ]; then
    say "Création de config.toml"
    cp config.example.toml config.toml
    # Linux often uses Comfy Desktop or a separately started ComfyUI. Avoid
    # trying to launch an instance behind Desktop's back by default.
    sed -i 's/^manage = true/manage = false/' config.toml
fi

mkdir -p user/logs models
chmod +x StableCraft.sh install.sh 2>/dev/null || true

say "Création du raccourci applicatif"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/applications"
mkdir -p "$APP_DIR"
cat > "$APP_DIR/stablecraft.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=StableCraft
Comment=Lasso editing in PhotoCraft with ComfyUI
Exec="$ROOT/StableCraft.sh"
Path=$ROOT
Terminal=false
Categories=Graphics;
EOF

cat <<EOF

Installation terminée.

Prochaines étapes :
1. Ouvre config.toml et renseigne [photocraft] executable.
2. Renseigne [comfyui] endpoint.
   - config.toml est créé avec manage = false par défaut.
   - Si ComfyUI est lancé par Comfy Desktop ou séparément : garde manage = false.
   - Si StableCraft doit le démarrer : passe manage = true
       root = "/chemin/vers/ComfyUI"
       python = "/chemin/vers/ComfyUI/.venv/bin/python"
       start_command = "/chemin/vers/ComfyUI/start.sh"   # optionnel

3. Lance StableCraft :
   ./StableCraft.sh

Python 3.11+ et Tkinter sont requis. Les distributions plus anciennes ne sont
pas prises en charge.
EOF
