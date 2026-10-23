# Utilisation

Guide pas à pas pour tester StableCraft en conditions réelles.

## 0. Ce qu'il faut lancer

Trois choses :

1. **ComfyUI** (le moteur) sur `http://127.0.0.1:12452`.
2. **PhotoCraft** avec le control channel activé.
3. **StableCraft** (l'UI).

L'ordre n'est pas critique, mais PhotoCraft doit être lancé **avec** les options du
control channel. Si tu le lances normalement (double-clic), l'UI ne pourra pas s'y
connecter.

## 1. Lancer ComfyUI

```powershell
F:\ComfyUI_windows_portable\run_nvidia_gpu.bat
```

Vérifie que le serveur répond :

```powershell
Invoke-RestMethod http://127.0.0.1:12452/system_stats
```

## 2. Lancer PhotoCraft avec le control channel

Ferme d'abord toute instance PhotoCraft déjà ouverte **sans** control channel.

```powershell
& "D:\Programmes\photocraft-0.14.0-windows-x64-portable\photocraft.exe" `
  --control 7878 `
  --control-token-file "C:\DEV_Seb\SeBL4RD-Stable_Craft\.runtime\control.token" `
  --automation-read-root "C:\DEV_Seb\SeBL4RD-Stable_Craft\.runtime\automation" `
  --automation-write-root "C:\DEV_Seb\SeBL4RD-Stable_Craft\.runtime\automation"
```

- Le token est créé automatiquement s'il n'existe pas.
- Les dossiers read/write root doivent exister ; `.runtime\automation` est déjà créé.
- Si tu changes ces chemins, mets les mêmes dans `config.toml`.

## 3. Lancer l'UI

```powershell
cd C:\DEV_Seb\SeBL4RD-Stable_Craft
python prototypes\stablecraft_ui.py --config config.toml
```

Tu dois voir :

- `PhotoCraft : connecté`
- `ComfyUI : 0.42.1 · RTX 3080 Ti · … Go libres`
- `Document : …`
- `Sélection : …` ou `Aucune — fais un lasso`
- `Modèles : OK`

Si `Modèles manquants` apparaît, voir la section Dépannage.

## 4. Faire une édition

1. Ouvre une image dans PhotoCraft (`Fichier > Ouvrir`).
2. Prends le **lasso** (ou n'importe quel outil de sélection) et entoure la zone à
   modifier. Pour un vêtement, sélectionne tout le vêtement, y compris l'ourlet.
3. Dans StableCraft :
   - choisis le profil : **FLUX.3** (défaut), **FLUX.2 9B** ou **Krea 2 Edit** ;
   - écris le prompt ;
   - ajuste si besoin `Contexte`, `Feather`, `Steps`, `CFG`, `Seed` ;
   - clique **Générer**.
4. Pendant la génération :
   - la barre de progression tourne ;
   - **Annuler** arrête le bridge et envoie `/interrupt` à ComfyUI ;
   - le journal en bas (scroll) montre les étapes.
5. À la fin :
   - l'aperçu s'affiche ;
   - PhotoCraft reçoit un **nouveau calque** avec un **masque de calque** ;
   - la sélection est restaurée pour pouvoir itérer.
6. Pour comparer/annuler :
   - `Édition > Annuler` dans PhotoCraft ;
   - ou masque le calque dans le panneau Calques ;
   - ou supprime le calque.

Chaque génération ajoute un calque. Pour itérer, garde la sélection et clique à
nouveau Générer, puis supprime les variantes que tu ne gardes pas.

## 5. Réglages conseillés

| Profil | Steps | CFG | Remarque |
|---|---:|---:|---|
| FLUX.3 Klein | 16 | 1.0 | défaut, meilleure fidélité locale |
| FLUX.2 Klein 9B | 4 | 1.0 | plus texturé, plus lourd |
| Krea 2 Edit | 8 | 1.0 | identité/style, peut changer la silhouette |

- **Contexte** : 96 px par défaut. Pour un petit objet, monte à 128–192 px pour donner
  plus de scène au modèle.
- **Feather** : 10 px par défaut. Descends à 4–6 px pour un bord net ; monte à 15–20 px
  pour un fondu doux.
- **Seed** : `-1` = aléatoire. Mets une valeur fixe pour comparer deux prompts.
- **Prompt** : décris le résultat, pas seulement le changement. Exemple :

  > Recolor the dress fabric to royal blue. Keep the exact silhouette, neckline,
  > skin, arms, legs, pose and background unchanged. Even studio lighting.

- Si le modèle change la silhouette ou la couleur au bord, c'est une limite des modèles
  d'édition instructionnelle. Un prompt plus précis et une sélection plus large
  (ourlet inclus) aident.

## 6. Installer pour un usage quotidien

Pour ne plus lancer les trois commandes à la main :

```powershell
cd C:\DEV_Seb\SeBL4RD-Stable_Craft
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1 `
  -ConfigFile "C:\DEV_Seb\SeBL4RD-Stable_Craft\config.toml"
```

L'installateur :

- détecte PhotoCraft et le Python de ComfyUI (ou demande les chemins) ;
- copie l'UI, le bridge, la config et les docs dans
  `%LOCALAPPDATA%\Programs\StableCraft` ;
- crée les raccourcis **StableCraft** et **PhotoCraft + StableCraft** ;
- ne télécharge aucun modèle.

Ensuite, utilise le raccourci **PhotoCraft + StableCraft**. Il lance PhotoCraft avec
le control channel, attend 3 s, puis lance l'UI.

Si l'auto-détection échoue :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1 `
  -PhotoCraft "D:\Programmes\photocraft-0.14.0-windows-x64-portable\photocraft.exe" `
  -ComfyPython "F:\ComfyUI_windows_portable\python_embeded\python.exe" `
  -ConfigFile "C:\DEV_Seb\SeBL4RD-Stable_Craft\config.toml"
```

## 7. Où sont les fichiers

- **Config locale** : `config.toml` (gitignoré). Exemple public :
  `config.example.toml`.
- **Sorties d'une génération** : `.runtime\automation\stablecraft\<date-heure>\` :
  `composite.png`, `crop.png`, `result.png`, `after.png`.
- **Journal UI** : panneau JOURNAL en bas (scrollbar).
- **Docs** : `docs/MODELS.md` (modèles, réglages, VRAM), `docs/TESTLOG.md`
  (validation), `docs/ARCHITECTURE.md` (design).

## 8. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `PhotoCraft : déconnecté` | PhotoCraft lancé sans `--control`, mauvais port/token | relance avec la commande du §2 ; vérifie `control_token_file` |
| `PhotoCraft : connecté (aucun document)` | aucune image ouverte | ouvre une image |
| `Sélection : aucune` | pas de lasso actif | fais une sélection ; attends 3 s (rafraîchissement) |
| `ComfyUI : déconnecté` | ComfyUI arrêté ou mauvais port | lance `run_nvidia_gpu.bat` ; vérifie `endpoint` |
| `Modèles manquants : X` | fichier invisible par ComfyUI | vérifie `config.toml` et `extra_model_paths.yaml` |
| `ComfyUI error in KSampler` | mauvais encodeur/loader | FLUX.3/Krea2 : Qwen3-VL FP8 ; FLUX.2 : Qwen3-8B GGUF |
| `Python ComfyUI introuvable` | `[comfyui] python` absent | mets le chemin de `python_embeded\python.exe` |
| `Aucune sélection` alors que le lasso existe | statut pas encore rafraîchi | attends 3 s ou change de profil puis revient |
| Bord rose/ancienne couleur | feather + résultat plus court que la sélection | sélectionne l'ourlet, baisse le feather, ou augmente le contexte |
| `WinError 10053` | connexion de contrôle fermée pendant le sampling | le bridge se reconnecte ; relance si nécessaire |

## 9. Limites actuelles

- L'UI est une fenêtre séparée, pas un panneau docké dans PhotoCraft.
- L'installateur PowerShell nécessite Python 3.11+ avec Tkinter. Un bundle `.exe`
  est prévu.
- Pas encore de téléchargement de modèles dans l'UI : les profils manquants sont
  signalés et Générer est désactivé. Le model manager avec consentement est la suite.
- Pas de batch/outpaint.
- Les documents CMYK/Lab/16 bits et 4K ne sont pas encore testés ; utilise du RGB 8 bits
  pour l'instant.
- Krea 2 Edit peut modifier la silhouette ; FLUX.2 9B est plus lourd (offload sur 12 Go).

## 10. Test recommandé

1. FLUX.3, lasso sur la robe, prompt « recolor … keep everything else unchanged »,
   Contexte 96, Feather 10.
2. Même sélection avec FLUX.2 9B, 4 steps : compare la texture et la fidélité.
3. Même sélection avec Krea 2 Edit, 8 steps : compare l'identité/style.
4. Annule les calques non retenus, garde le meilleur, puis teste un prompt plus
   complexe (remplacer un objet, changer un fond, ajouter un accessoire).

Note ce qui te gêne (vitesse, fidélité, bord, UI) : ce sera la base des prochains
réglages.
