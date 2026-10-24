# Installateur StableCraft

Un seul clic : **StableCraft.bat**. Il démarre ComfyUI, PhotoCraft avec le control
channel, puis l'UI. Si un chemin obligatoire manque, il affiche un message clair et
s'arrête. Les modèles manquants ne bloquent pas : l'UI les signale.

## Prérequis

- Windows x64.
- PhotoCraft 0.14.0 (portable ou installé).
- ComfyUI portable avec `python_embeded\python.exe` (Pillow + requests inclus).
- Python 3.11+ avec Tkinter pour l'UI (`python.exe` dans le PATH).
- Les modèles FLUX.3/FLUX.2/Krea 2 doivent être visibles par ComfyUI
  (voir `docs/MODELS.md`).

## Utilisation sans installer

Depuis le dossier du repo :

```powershell
.\StableCraft.bat
```

C'est tout. Le lanceur lit `config.toml`, démarre ce qui manque, puis ouvre l'UI.
Pour un premier lancement, `config.toml` doit exister (copie `config.example.toml`
ou lance l'installateur).

## Installer

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1
```

Ou double-clique sur `installer\install.cmd`.

Installation avec chemins explicites :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1 `
  -InstallDir "C:\Users\Seb\StableCraft" `
  -PhotoCraft "D:\Programmes\photocraft-0.14.0-windows-x64-portable\photocraft.exe" `
  -ComfyPython "F:\ComfyUI_windows_portable\python_embeded\python.exe" `
  -ConfigFile ".\config.toml"
```

Options :

| Option | Rôle |
|---|---|
| `-InstallDir` | dossier d'installation (défaut `%USERPROFILE%\StableCraft`, hors AppData) |
| `-PhotoCraft` | chemin de `photocraft.exe` (auto-détection sinon) |
| `-ComfyPython` | chemin du `python_embeded\python.exe` de ComfyUI |
| `-ComfyEndpoint` | endpoint ComfyUI (défaut `http://127.0.0.1:12452`) |
| `-ConfigFile` | config existante à importer (les chemins d'installation sont réécrits) |
| `-NoShortcuts` | ne crée aucun raccourci |
| `-NoDesktopShortcut` | crée le raccourci du menu Démarrer mais pas celui du bureau |

## Ce que fait l'installateur

1. Détecte PhotoCraft et le Python de ComfyUI.
2. Copie l'UI, le bridge, `StableCraft.bat`, `launcher.py`, la config et les docs.
3. Écrit `config.toml` avec `photocraft.executable`, `comfyui.root`,
   `comfyui.start_command`, le Python de ComfyUI, `user/` (token + sessions) et
   `models/`.
4. Crée **un seul raccourci** : `StableCraft` (menu Démarrer et bureau).
5. Ne télécharge aucun modèle.

Le raccourci lance `StableCraft.bat`. Ce dernier :

- vérifie les chemins (message clair + arrêt si un chemin obligatoire manque) ;
- démarre ComfyUI si le port `12452` est fermé ;
- démarre PhotoCraft avec `--control` si le port `7878` est fermé ;
- lance l'UI Tkinter.

Si PhotoCraft est déjà ouvert **sans** control channel, le lanceur affiche :
« PhotoCraft est déjà ouvert, mais sans le control channel. Ferme-le, puis relance
StableCraft.bat. »

## Désinstallation

Menu Démarrer → **Désinstaller StableCraft**. Le script demande s'il faut supprimer
aussi `models/`, `user/` et `config.toml` ; réponds `N` pour les conserver. Les
sessions et générations sont dans `user/`.

## Limites du MVP

- L'UI nécessite Python 3.11+ avec Tkinter. Un bundle PyInstaller est prévu.
- Pas encore d'installeur `.exe` Inno Setup ; le `.bat` + PowerShell est la première
  version.
- Pas de téléchargement de modèles dans l'UI : les profils manquants sont signalés.
- Le premier démarrage de ComfyUI peut prendre 30–60 s ; le lanceur attend jusqu'à
  4 minutes.
