#!/usr/bin/env bash
# StableCraft installer for Linux.
#
# Supported: Debian/Ubuntu, Fedora/RHEL, Arch. Python 3.11+ and Tkinter are
# required; older distributions are intentionally not supported.
#
# Usage: bash install.sh [-y|--yes]
#   -y, --yes   install missing system packages without asking
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

say() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERREUR: %s\n' "$*" >&2; exit 1; }

ASSUME_YES=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes) ASSUME_YES=1 ;;
        -h|--help)
            printf 'Usage: bash install.sh [-y|--yes]\n'
            printf '  -y, --yes   installe les paquets système manquants sans demander\n'
            exit 0
            ;;
        *) fail "Option inconnue : $arg (utilise --help)" ;;
    esac
done

if command -v apt-get >/dev/null 2>&1; then
    PM="apt"
    PY_PKG="python3"
    TK_PKG="python3-tk"
    VENV_PKG="python3-venv"
elif command -v dnf >/dev/null 2>&1; then
    PM="dnf"
    PY_PKG="python3"
    TK_PKG="python3-tkinter"
    VENV_PKG="python3"
elif command -v pacman >/dev/null 2>&1; then
    PM="pacman"
    PY_PKG="python"
    TK_PKG="tk"
    VENV_PKG="python"
else
    PM=""
    PY_PKG="python3"
    TK_PKG="tk"
    VENV_PKG="python3"
fi

pm_install() {
    case "$PM" in
        apt)
            run_root apt-get update
            run_root apt-get install -y "$@"
            ;;
        dnf)
            run_root dnf install -y "$@"
            ;;
        pacman)
            run_root pacman -S --needed --noconfirm "$@"
            ;;
    esac
}

if [ "$(id -u)" -eq 0 ]; then
    run_root() { "$@"; }
elif command -v sudo >/dev/null 2>&1; then
    run_root() { sudo "$@"; }
else
    run_root() {
        fail "Cette étape a besoin des droits root mais sudo est absent.
  Installe les paquets manquants avec le compte root, puis relance bash install.sh"
    }
fi

pm_command() {
    case "$PM" in
        apt) printf 'sudo apt install %s' "$*" ;;
        dnf) printf 'sudo dnf install %s' "$*" ;;
        pacman) printf 'sudo pacman -S %s' "$*" ;;
        *) printf 'installe %s avec le gestionnaire de paquets de ta distribution' "$*" ;;
    esac
}

say "Vérification de Python et Tkinter"
MISSING=()
if ! command -v python3 >/dev/null 2>&1; then
    # A fresh system may lack all three; let the package manager pull them in.
    MISSING+=("$PY_PKG" "$TK_PKG" "$VENV_PKG")
else
    python3 -c 'import tkinter' >/dev/null 2>&1 || MISSING+=("$TK_PKG")
    python3 -c 'import ensurepip' >/dev/null 2>&1 || MISSING+=("$VENV_PKG")
fi

# Clipboard tools for the reference Paste button: wl-paste on Wayland,
# xclip on X11 (also works under XWayland). Keep both available.
case "$PM" in
    apt|dnf|pacman)
        command -v wl-paste >/dev/null 2>&1 || MISSING+=("wl-clipboard")
        command -v xclip >/dev/null 2>&1 || MISSING+=("xclip")
        ;;
esac

if [ ${#MISSING[@]} -gt 0 ]; then
    # Remove duplicates while keeping the order.
    UNIQUE=()
    for pkg in "${MISSING[@]}"; do
        case " ${UNIQUE[*]} " in
            *" $pkg "*) ;;
            *) UNIQUE+=("$pkg") ;;
        esac
    done
    MISSING=("${UNIQUE[@]}")
    say "Paquets système manquants : ${MISSING[*]}"
    if [ -z "$PM" ]; then
        fail "Gestionnaire de paquets non reconnu (apt, dnf ou pacman requis).
  Installe : ${MISSING[*]}"
    fi
    INSTALL_CMD="$(pm_command "${MISSING[@]}")"
    if [ "$ASSUME_YES" -eq 0 ]; then
        if [ -t 0 ]; then
            printf 'Installer maintenant avec %s ? [O/n] ' "$PM"
            read -r answer
            case "$answer" in
                n|N|non|Non|NON) fail "Dépendances manquantes. Lance : $INSTALL_CMD" ;;
            esac
        else
            fail "Dépendances manquantes. Relance avec --yes ou lance : $INSTALL_CMD"
        fi
    fi
    pm_install "${MISSING[@]}"
    say "Vérification après installation"
    command -v python3 >/dev/null 2>&1 || fail "python3 reste introuvable après installation."
    python3 -c 'import tkinter' >/dev/null 2>&1 \
        || fail "Tkinter reste introuvable après installation. Lance : $INSTALL_CMD"
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    fail "Python $(python3 -V 2>&1 | cut -d' ' -f2) est trop ancien. StableCraft exige Python 3.11+.
  Installe un Python 3.11+ (par exemple python3.13), puis relance bash install.sh."
fi

say "Création du venv StableCraft"
# A .venv created with another Python version (Fedora upgrade, pyenv change…)
# may exist but no longer have a working interpreter.
if [ -e ".venv" ] && [ ! -x ".venv/bin/python" ]; then
    say "Le .venv existant est inutilisable ; il est recréé"
    rm -rf .venv
fi
if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv \
        || fail "Impossible de créer .venv. Vérifie que le module venv/ensurepip est installé."
fi
if ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    fail "Le .venv existant utilise un Python trop ancien. Supprime .venv puis relance :
  rm -rf .venv && bash install.sh"
fi

say "Installation des dépendances Python (requests, Pillow, psutil)"
.venv/bin/python -m pip install --upgrade pip
if ! .venv/bin/python -m pip install -r prototypes/requirements.txt; then
    fail "Échec de l'installation des dépendances Python.
  Vérifie ta connexion réseau. Si pip doit compiler depuis les sources :
    Debian/Ubuntu : sudo apt install build-essential python3-dev
    Fedora/RHEL   : sudo dnf install gcc python3-devel
    Arch          : sudo pacman -S base-devel"
fi

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
ICON="$ROOT/installer/logo_full.ico"
if [ ! -f "$ICON" ]; then
    ICON="$ROOT/demo/logo_full.ico"
fi
if [ ! -f "$ICON" ]; then
    echo "Attention : logo StableCraft introuvable, icône système utilisée." >&2
    ICON="applications-graphics"
fi

cat > "$APP_DIR/stablecraft.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=StableCraft
Comment=Lasso editing in PhotoCraft with ComfyUI
Exec="$ROOT/StableCraft.sh"
Path=$ROOT
Icon=$ICON
Terminal=false
Categories=Graphics;
EOF

cat <<EOF

Installation terminée.

Prochaines étapes :
1. PhotoCraft est détecté automatiquement (deb, rpm, snap, flatpak, AppImage,
   tarball). Si besoin, renseigne [photocraft] executable dans config.toml.
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
