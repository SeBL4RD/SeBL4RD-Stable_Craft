# StableCraft sur Linux

Testé sur Arch Linux (Omarchy, Hyprland + XWayland), PhotoCraft 0.16.0, ComfyUI en checkout git.

## Installation

1. Installe le paquet Linux de PhotoCraft : `sudo pacman -U photocraft-<version>-linux-x86_64.pkg.tar.zst`.
2. Installe Tk pour Python : `sudo pacman -S tk`.
3. Copie `config.example.toml` en `config.toml`.
4. Dans `[comfyui]`, mets `root` sur le dossier qui contient `main.py`, et `endpoint` sur le port de ComfyUI.
5. Dans `[profiles.*]`, mets les noms de fichiers que ComfyUI voit (`unet`, `text_encoder`, `vae`, `lora`).
6. Lance `./stablecraft.sh`.

## Ce qui change par rapport à Windows

- PhotoCraft est trouvé dans le `PATH`. Le lanceur démarre une instance séparée (`--new-instance`) avec le canal de contrôle.
- ComfyUI démarre avec `python main.py --disable-auto-launch`, ou avec `restart_command` si tu le renseignes.
- Les fichiers `.safetensors` (int8, fp8, bf16) passent par `UNETLoader` avec `weight_dtype = "default"`.
- Les fichiers et dossiers s'ouvrent avec `xdg-open`.
- Écran HiDPI : `stablecraft.sh` lit l'échelle de l'écran sous Hyprland. Ailleurs, mets `STABLECRAFT_UI_SCALE=2` à la main.

## Vérifier les profils

`<python de ComfyUI> tools/check_profiles.py config.toml` vérifie que chaque profil actif trouve ses fichiers et ses nodes dans ComfyUI.
