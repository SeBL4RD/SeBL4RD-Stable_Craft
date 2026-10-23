# Journal de validation

## 2026-10-23 — PhotoCraft 0.14.0 + ComfyUI 0.42.1

### Environnement

- Windows x64
- PhotoCraft portable 0.14.0 (`D:\Programmes\photocraft-0.14.0-windows-x64-portable`)
- ComfyUI 0.42.1, port `12452`
- NVIDIA RTX 3080 Ti 12 Go, 32 Go RAM
- Modèles locaux uniquement, aucun téléchargement

### Backend ComfyUI

| Test | Résultat |
|---|---|
| FLUX.3 Klein Q8 + Qwen3-VL-4B FP8 + VAE FLUX.2, 16 steps, CFG 1 | ✅ édition globale, ~34 s |
| FLUX.2 Klein 9B Q8 + Qwen3-8B Q4, 6 steps, CFG 1 | ✅ édition, ~60 s, plus texturé |
| Krea 2 Edit Q4 (`krea2_turbo_edit`) + Qwen3-VL FP8 + nœuds krea2edit, 8 steps, CFG 1 | ✅ édition, silhouette modifiée |
| Krea 2 Turbo Q4 (arch `krea2`) avec `UnetLoaderGGUF` | ❌ `Unexpected architecture type in GGUF file: 'krea2'` |
| `Qwen3VL-4B-Instruct-Q4_K_M.gguf` avec `CLIPLoaderGGUF` pour Flux3 | ❌ `mat1 and mat2 shapes cannot be multiplied` |
| `Qwen3VL-4B-Instruct-Q4_K_M.gguf` avec `CLIPLoaderGGUF` pour Krea2 | ❌ `Krea2 expects conditioning with 12x2560=30720 features` |

### Control channel PhotoCraft

| Commande | Résultat |
|---|---|
| `select.lasso` | ✅ bounds `[271,294,226,380]` |
| `document.inspect` | ✅ `hasSelection`, `selectionBounds`, calques |
| `app.save` composite PNG | ✅ |
| `select.saveSelection` (canal « StableCraft Mask ») | ✅ création et remplacement |
| `channel.duplicate` vers document grayscale | ✅ retourne `{document: 1}` |
| `app.save` masque PNG | ✅ |
| `file.close` document temporaire | ✅ |
| `document.activate` | ✅ |
| `app.open` PNG dans sous-dossier | ✅ |
| `layer.copyToDocument` offset `[175,192]` | ✅ calque 14, bounds `[175,192,416,576]`, sélection préservée |
| `layer.layerMask.revealSelection` | ✅ `hasMask: true` |
| `layer.layerMask.edit {"feather": 10}` | ✅ `{density:100, feather:10}` |
| `select.loadSelection` | ✅ sélection restaurée |
| `ui.screenshot` | ✅ capture 1920×1032 |

### Bridge CLI

Commande testée :

```powershell
F:\ComfyUI_windows_portable\python_embeded\python.exe prototypes\bridge_cli.py `
  --config config.toml `
  --prompt "Recolor the dress fabric to royal blue. Keep the exact silhouette, neckline, skin, arms, legs, pose and background unchanged. Even studio lighting, no extra shadows or folds." `
  --save-preview
```

Résultat :

- crop `(180,224)` 400×544, padding 96 ;
- génération 31,3 s, 16 steps, seed 2708149655317791484 ;
- nouveau calque 28, bounds `[180,224,400,544]`, masque + feather 10 ;
- sélection restaurée ;
- preview `after.png` et capture UI.

### Problèmes rencontrés

1. **Connexion inactive** : PhotoCraft a fermé la connexion de contrôle pendant le
   sampling ComfyUI (~36 s). `app.open` a échoué avec `WinError 10053`. Solution :
   reconnecter avant la phase d'application. Implémenté dans `bridge_cli.py`.
2. **Fichier en cours d'écriture** : `app.open` sur un PNG encore en écriture renvoie
   `codec: unrecognized image format`. Attendre la fin de l'écriture.
3. **Bord du masque** : un feather de 10 px sur un lasso serré laisse parfois
   transparaître la couleur d'origine au bord (ourlet). Réglable via `--feather` ;
   un `select.modify.expand` de 1–2 px pourrait améliorer.
4. **PNG aplati** : `app.save` prévient que les calques/masques ne sont pas conservés
   dans le PNG. Le document PhotoCraft, lui, garde le calque et le masque.

### Bridge : profils FLUX.2 et Krea 2

| Profil | Commande | Résultat |
|---|---|---|
| FLUX.2 Klein 9B | `bridge_cli.py --profile flux2_klein_9b --no-apply` | ✅ 4 steps, 47,7 s, crop 400×544 |
| Krea 2 Edit | `bridge_cli.py --profile krea2_edit --no-apply` | ✅ 8 steps, 25,2 s, crop 400×544 |

Les deux profils passent la validation des modèles/nœuds et produisent un PNG au crop.
L'UI les propose dans le combo de profils ; le bridge reçoit bien `--profile`.

### UI Tkinter

Testée avec le Python système 3.11 (Tkinter, sans dépendance) et le Python embarqué de
ComfyUI pour le bridge.

- ✅ démarrage, connexion PhotoCraft + ComfyUI ;
- ✅ document `input.png`, sélection `215×346`, modèles OK ;
- ✅ bouton Générer → bridge → nouveau calque, statut « Terminé — nouveau calque dans
  PhotoCraft », preview chargée ;
- ✅ bouton Annuler disponible pendant la génération ;
- ✅ scrollbar pour le journal et les sections basses ;
- ✅ profils FLUX.3, FLUX.2 et Krea 2 : smoke test OK, modèles/nœuds OK ;
- ✅ passage en Krea 2 : 8 steps / CFG 1 / 12,6 Go affichés, bouton Générer actif.

Preuve : `docs/demo/stablecraft-ui.png`.

### Installateur

Testé avec :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1 `
  -InstallDir .runtime\install_test3 `
  -PhotoCraft "D:\Programmes\photocraft-0.14.0-windows-x64-portable\photocraft.exe" `
  -ComfyPython "F:\ComfyUI_windows_portable\python_embeded\python.exe" `
  -ConfigFile config.toml -NoShortcuts
```

- ✅ détection PhotoCraft / Python ComfyUI / Python UI ;
- ✅ copie des fichiers, `tmp/`, `models/` ;
- ✅ `config.toml` avec token, automation root, endpoint et Python réécrits ;
- ✅ `launch.cmd` avec les flags du control channel ;
- ✅ `uninstall.ps1` en UTF-8 BOM, conservation optionnelle des modèles/config ;
- ✅ aucun téléchargement de modèle.

### Preuves

- `docs/demo/photocraft-bridge.png` : UI PhotoCraft avec calque StableCraft, masque,
  densité 100 %, feather 10 px, sélection active.
- `docs/demo/photocraft-flux3-blue.png` : rendu final.
- `docs/demo/photocraft-crop.png` : crop envoyé à ComfyUI.
- `docs/demo/stablecraft-ui.png` : UI Tkinter du MVP après génération.
