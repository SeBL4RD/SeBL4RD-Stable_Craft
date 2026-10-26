# StableCraft on Linux

Tested on Arch Linux (Hyprland + XWayland) with the native PhotoCraft 0.16.0 package,
ComfyUI 0.42.0 from a git checkout, and an RTX 4090 Laptop. Other distributions should
work with adapted paths, but they are not tested.

French version: [LINUX.fr.md](LINUX.fr.md).

## Install

1. Install the Linux package of PhotoCraft, for example
   `sudo pacman -U photocraft-<version>-linux-x86_64.pkg.tar.zst`. The `photocraft`
   command must be in `PATH`.
2. Install Tk for Python 3.11+: `sudo pacman -S tk`.
3. Copy `config.example.toml` to `config.toml`.
4. In `[comfyui]`, set `root` to the folder that contains `main.py`, and `endpoint` to
   the ComfyUI port. An empty `python` means the first `.venv` or `venv` found next to
   `main.py`, then in `<root>`; with no venv,
   StableCraft tries its own Python and writes that to `user/logs/launcher.log`.
5. In `[profiles.*]`, use the file names that ComfyUI sees (`unet`, `text_encoder`,
   `vae`, `lora`). Profiles with a `.gguf` model need the ComfyUI-GGUF custom node.
6. Run `./stablecraft.sh`.

## Menu entry (optional)

Save this as `~/.local/share/applications/stablecraft.desktop`, with your own path:

```ini
[Desktop Entry]
Type=Application
Name=StableCraft
Comment=Lasso editing in PhotoCraft with ComfyUI
Exec=/path/to/StableCraft/stablecraft.sh
Terminal=false
Categories=Graphics;
```

## What differs from Windows

- PhotoCraft is found in `PATH` and starts as a separate instance (`--new-instance`)
  with the control channel. Its output goes to `user/logs/photocraft-app.log`: from a
  menu there is no terminal, and an inherited closed pipe made PhotoCraft crash before
  it opened the control channel.
- ComfyUI starts with `python main.py --disable-auto-launch` on the configured port.
  Its output goes to `user/logs/comfyui.log`.
- Files and folders open with `xdg-open`.
- HiDPI: under Hyprland with `xwayland:force_zero_scaling`, `stablecraft.sh` reads the
  monitor scale. Elsewhere, set `STABLECRAFT_UI_SCALE=2` yourself.
- Dragging a reference image onto the window is Windows-only and is not ported (the
  "Click or drop" hint still shows): click to pick the image.
- At `STABLECRAFT_UI_SCALE=2`, some long labels wrap too early: `wraplength` is not
  scaled.

## Restart command

"Restart ComfyUI" stops the process that listens on the port, then starts ComfyUI again.
If ComfyUI runs as a service, set `restart_command` (a script, or
`systemctl --user restart <unit>`). StableCraft also uses it to start ComfyUI when it
is not running at launch. For "Restart ComfyUI", StableCraft waits for the command to
finish. A
non-zero exit code is shown as a refusal. A good script refuses (for example with exit
code 3) while the ComfyUI queue is not empty, so that a running render is never cut.

## Checks and test tools

- `<ComfyUI python> tools/check_profiles.py config.toml` checks that each enabled
  profile finds its files and nodes in ComfyUI.
- `tools/diag_canal.py` is a short, bounded probe of the PhotoCraft control channel.
- `tools/e2e.py` and `tools/e2e_session.py` run an edit end to end through the control
  channel. They use the default ports 7990 and 8188. `e2e_session.py` first closes
  every open PhotoCraft document, without saving.
