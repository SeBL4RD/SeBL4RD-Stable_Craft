#!/usr/bin/env bash
# StableCraft launcher for Linux (Debian/Ubuntu, Fedora/RHEL, Arch).
set -euo pipefail
export PYTHONUTF8=1
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "Le venv StableCraft est absent. Lance : bash install.sh"
    exit 1
fi

exec ".venv/bin/python" launcher.py "$@"
