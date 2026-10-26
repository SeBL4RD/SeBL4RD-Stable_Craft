# StableCraft sur Linux

Testé sur Arch Linux (Hyprland + XWayland) avec le paquet natif de PhotoCraft 0.16.0,
ComfyUI 0.42.0 en checkout git et une RTX 4090 Laptop. Les autres distributions
devraient marcher en adaptant les chemins, mais elles ne sont pas testées.

Version anglaise : [LINUX.md](LINUX.md).

## Installation

1. Installe le paquet Linux de PhotoCraft, par exemple
   `sudo pacman -U photocraft-<version>-linux-x86_64.pkg.tar.zst`. La commande
   `photocraft` doit être dans le `PATH`.
2. Installe Tk pour Python 3.11+ : `sudo pacman -S tk`.
3. Copie `config.example.toml` en `config.toml`.
4. Dans `[comfyui]`, mets `root` sur le dossier qui contient `main.py`, et `endpoint` sur
   le port de ComfyUI. `python` vide = premier `.venv` ou `venv` trouvé à côté de
   `main.py`, puis dans `<root>` ; sans venv, StableCraft essaie
   son propre Python et le note dans `user/logs/launcher.log`.
5. Dans `[profiles.*]`, mets les noms de fichiers que ComfyUI voit (`unet`,
   `text_encoder`, `vae`, `lora`). Les profils en `.gguf` demandent le node
   ComfyUI-GGUF.
6. Lance `./stablecraft.sh`.

## Entrée de menu (optionnel)

Enregistre ceci dans `~/.local/share/applications/stablecraft.desktop`, avec ton chemin :

```ini
[Desktop Entry]
Type=Application
Name=StableCraft
Comment=Édition au lasso dans PhotoCraft avec ComfyUI
Exec=/chemin/vers/StableCraft/stablecraft.sh
Terminal=false
Categories=Graphics;
```

## Ce qui change par rapport à Windows

- PhotoCraft est trouvé dans le `PATH` et démarre en instance séparée
  (`--new-instance`) avec le canal de contrôle. Sa sortie va dans
  `user/logs/photocraft-app.log` : depuis un menu il n'y a pas de terminal, et un tuyau
  fermé hérité faisait planter PhotoCraft avant qu'il ouvre le canal.
- ComfyUI démarre avec `python main.py --disable-auto-launch` sur le port configuré. Sa
  sortie va dans `user/logs/comfyui.log`.
- Les fichiers et dossiers s'ouvrent avec `xdg-open`.
- Écran HiDPI : sous Hyprland avec `xwayland:force_zero_scaling`, `stablecraft.sh` lit
  l'échelle de l'écran. Ailleurs, mets `STABLECRAFT_UI_SCALE=2` toi-même.
- Glisser une image de référence sur la fenêtre est réservé à Windows et n'est pas
  porté (l'indication « Clique ou dépose » reste affichée) : clique pour choisir l'image.
- Avec `STABLECRAFT_UI_SCALE=2`, certains libellés longs passent à la ligne trop tôt :
  `wraplength` n'est pas mis à l'échelle.

## Commande de redémarrage

« Redémarrer ComfyUI » arrête le processus qui écoute sur le port, puis relance ComfyUI.
Si ComfyUI tourne en service, renseigne `restart_command` (un script, ou
`systemctl --user restart <unité>`). StableCraft s'en sert aussi pour démarrer ComfyUI
s'il ne tourne pas au lancement. Pour « Redémarrer ComfyUI », StableCraft attend la fin
de la commande. Un code de
sortie non nul s'affiche comme un refus. Un bon script refuse (par exemple avec le
code 3) tant que la file de ComfyUI n'est pas vide, pour ne jamais couper un rendu.

## Vérifications et outils de test

- `<python de ComfyUI> tools/check_profiles.py config.toml` vérifie que chaque profil
  actif trouve ses fichiers et ses nodes dans ComfyUI.
- `tools/diag_canal.py` est une sonde courte et bornée du canal de contrôle de PhotoCraft.
- `tools/e2e.py` et `tools/e2e_session.py` lancent une édition de bout en bout par le
  canal de contrôle. Ils utilisent les ports par défaut 7990 et 8188. `e2e_session.py`
  ferme d'abord tous les documents ouverts dans PhotoCraft, sans enregistrer.
