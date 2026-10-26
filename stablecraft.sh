#!/usr/bin/env bash
# StableCraft on Linux: starts ComfyUI if needed, PhotoCraft with its control channel, then the UI.
cd "$(dirname "$(readlink -f "$0")")" || exit 1

# HiDPI: with Hyprland xwayland:force_zero_scaling, Tk draws at 1:1 physical pixels.
# Use the focused monitor scale so the window and fonts keep their normal size.
if [ -z "${STABLECRAFT_UI_SCALE:-}" ] && command -v hyprctl >/dev/null 2>&1; then
  if [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
    # Launched from a menu or a service: find the live Hyprland instance.
    for dir in $(ls -1dt "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"/hypr/*/ 2>/dev/null); do
      sig=$(basename "$dir")
      if HYPRLAND_INSTANCE_SIGNATURE="$sig" hyprctl -j monitors >/dev/null 2>&1; then
        export HYPRLAND_INSTANCE_SIGNATURE="$sig"
        break
      fi
    done
  fi
  if hyprctl getoption xwayland:force_zero_scaling 2>/dev/null | grep -qE "^(int: 1|bool: true)"; then
    scale=$(hyprctl -j monitors 2>/dev/null | python3 -I -c '
import json, sys
m = json.load(sys.stdin)
f = [x for x in m if x.get("focused")] or m
print(f[0]["scale"])' 2>/dev/null)
    [ -n "$scale" ] && export STABLECRAFT_UI_SCALE="$scale"
  fi
fi

exec env -u PYTHONPATH /usr/bin/python3 launcher.py "$@"
