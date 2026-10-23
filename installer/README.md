# Installateur StableCraft (MVP)

Installateur PowerShell, sans admin, pour Windows. Il installe StableCraft à côté
d'une installation PhotoCraft existante, sans fork et sans télécharger de modèle.

## Prérequis

- Windows x64.
- PhotoCraft 0.14.0 (portable ou installé).
- ComfyUI qui tourne, avec son Python embarqué (`python_embeded\python.exe`) et
  `requests` + Pillow (présents dans l'installation standard).
- Python 3.11+ **avec Tkinter** pour l'UI (`python.exe` dans le PATH). C'est le cas
  de l'installation Python standard ; si Tkinter manque, l'UI ne démarre pas.
- Les modèles FLUX.3 doivent être visibles par ComfyUI (voir `docs/MODELS.md`).

## Lancer

Double-clique sur `install.cmd`, ou :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1
```

Installation silencieuse avec chemins explicites :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1 `
  -InstallDir "C:\Users\Seb\AppData\Local\Programs\StableCraft" `
  -PhotoCraft "D:\Programmes\photocraft-0.14.0-windows-x64-portable\photocraft.exe" `
  -ComfyPython "F:\ComfyUI_windows_portable\python_embeded\python.exe" `
  -ConfigFile ".\config.toml"
```

Options :

| Option | Rôle |
|---|---|
| `-InstallDir` | dossier d'installation (défaut `%LOCALAPPDATA%\Programs\StableCraft`) |
| `-PhotoCraft` | chemin de `photocraft.exe` (auto-détection sinon) |
| `-ComfyPython` | chemin du `python_embeded\python.exe` de ComfyUI |
| `-ComfyEndpoint` | endpoint ComfyUI (défaut `http://127.0.0.1:12452`) |
| `-ConfigFile` | config existante à importer (les chemins d'installation sont réécrits) |
| `-NoShortcuts` | ne crée aucun raccourci |
| `-NoDesktopShortcut` | crée les raccourcis du menu Démarrer mais pas celui du bureau |

## Ce que fait l'installateur

1. Détecte PhotoCraft et le Python de ComfyUI.
2. Copie l'UI, le bridge, `models.json`, `compat.toml` et les docs dans le dossier
   d'installation.
3. Écrit `config.toml` avec le token, le dossier temporaire, l'endpoint et le Python
   de ComfyUI. Les chemins de modèles de la config importée sont conservés.
4. Crée `tmp/` et `models/`.
5. Crée `launch.cmd` : lance PhotoCraft avec le control channel, attend 3 s, puis
   lance l'UI.
6. Crée les raccourcis :
   - **StableCraft** : l'UI seule (PhotoCraft doit déjà tourner avec le control channel) ;
   - **PhotoCraft + StableCraft** : le lanceur complet ;
   - **Désinstaller StableCraft**.
7. Ne télécharge **aucun** modèle.

## Après l'installation

Lance **PhotoCraft + StableCraft**. PhotoCraft démarre avec :

```
--control 7878
--control-token-file <install>\control.token
--automation-read-root <install>\tmp
--automation-write-root <install>\tmp
```

L'UI lit le token et se connecte. Si PhotoCraft est déjà lancé sans ces options, le
lanceur peut ouvrir une seconde instance ou ne pas exposer le control channel :
ferme PhotoCraft avant d'utiliser le raccourci.

## Désinstallation

Menu Démarrer → **Désinstaller StableCraft**. Le script demande s'il faut supprimer
aussi `models/` et `config.toml` ; réponds `N` pour les conserver.

## Limites du MVP

- L'UI nécessite Python 3.11+ avec Tkinter. Un bundle PyInstaller est prévu pour
  supprimer cette dépendance.
- Pas encore d'installeur `.exe` Inno Setup ; le script PowerShell est la première
  version. Le `.iss` viendra quand le bundle sera prêt.
- Pas de téléchargement de modèles : le model manager avec consentement est la phase
  suivante.
- Le lanceur attend 3 s ; si PhotoCraft met plus de temps, l'UI se reconnecte toute
  seule grâce à son rafraîchissement de statut.
