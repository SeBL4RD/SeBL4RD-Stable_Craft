# Utilisation

Guide pas à pas pour tester StableCraft en conditions réelles.

## Démarrage normal : un seul clic

**Double-clique sur `StableCraft.bat`.**

Il fait tout :

1. vérifie les chemins (PhotoCraft, ComfyUI, Python UI) ;
2. démarre ComfyUI s'il ne tourne pas, **sans ouvrir le navigateur** ;
3. démarre PhotoCraft avec le control channel s'il ne tourne pas ;
4. nettoie les fichiers temporaires StableCraft de « Ouvrir un fichier récent » ;
5. ouvre l'UI.

### Si un chemin manque

Un message clair s'affiche et le lanceur s'arrête. Il indique la clé à corriger dans
`config.toml`, par exemple :

- `[photocraft] executable` : le chemin de `photocraft.exe` ;
- `[comfyui] root` : le dossier qui contient `run_nvidia_gpu.bat` et `python_embeded` ;
- `[comfyui] python` : le `python_embeded\python.exe` de ComfyUI.

Les **modèles manquants ne bloquent pas** : l'UI les signale et désactive Générer.
Le téléchargement assisté viendra plus tard.

### Ce que tu dois voir dans l'UI

- `PhotoCraft : connecté`
- `ComfyUI : 0.42.1 · RTX 3080 Ti · … Go libres`
- `Document : …`
- `Sélection : …` ou `Aucune — fais un lasso`
- `Modèles : OK`

## Développement : lancer à la main

Utile seulement pour déboguer. Le chemin normal reste `StableCraft.bat`.

ComfyUI :

```powershell
F:\ComfyUI_windows_portable\run_nvidia_gpu.bat
```

PhotoCraft avec le control channel :

```powershell
& "D:\Programmes\photocraft-0.14.0-windows-x64-portable\photocraft.exe" `
  --control 7878 `
  --control-token-file "C:\DEV_Seb\SeBL4RD-Stable_Craft\user\control.token" `
  --automation-read-root "C:\DEV_Seb\SeBL4RD-Stable_Craft\user" `
  --automation-write-root "C:\DEV_Seb\SeBL4RD-Stable_Craft\user"
```

UI :

```powershell
cd C:\DEV_Seb\SeBL4RD-Stable_Craft
python prototypes\stablecraft_ui.py --config config.toml
```

Le token est créé automatiquement s'il n'existe pas. Si tu changes ces chemins, mets
les mêmes dans `config.toml`.

## Faire une édition

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
   - PhotoCraft reçoit un **calque StableCraft** avec un **masque de calque** ;
   - la galerie du calque s'affiche ;
   - la sélection est restaurée pour pouvoir itérer.
6. Pour comparer/annuler :
   - `Édition > Annuler` dans PhotoCraft ;
   - ou masque le calque dans le panneau Calques ;
   - ou supprime le calque.

### Régénérer et galerie

- **Même sélection** : le bouton devient **Régénérer**. La nouvelle génération reste
  dans le **même calque** et s'ajoute à la galerie ; elle n'empile pas un nouveau calque.
- **Input figé** : toutes les générations d'une session repartent du `base.png` pris au
  moment du lasso. Une génération précédente n'est jamais réinjectée comme image source.
- **Sélection perdue** : sélectionne le calque `StableCraft [id]` dans PhotoCraft, puis
  clique **Régénérer**. StableCraft relit la sélection et le masque depuis la session,
  même si le lasso n'est plus actif.
- **Ancien calque** : clique sur un calque `StableCraft [id]` pour recharger sa galerie.
  Clique sur une vignette pour appliquer cette génération au calque, sans relancer
  ComfyUI.
- **Nouvelle sélection** : dès qu'un nouveau lasso différent est détecté, la galerie
  de l'ancienne sélection se vide et le bouton redevient **Générer**. Le prochain clic
  crée un nouveau calque et une nouvelle galerie. L'ancien calque reste intact.
- **Seed** : StableCraft ne réécrit jamais le seed réel dans le champ. Il garde la
  valeur que tu as saisie, `-1` par défaut. Le seed utilisé est affiché dans la ligne
  sous la galerie. Si tu saisis volontairement un seed fixe déjà utilisé avec le même
  prompt/profil/réglages, le bouton est bloqué pour éviter un doublon. `-1` ou un autre
  seed repart.
- **Feather** : chaque génération garde son feather. Quand tu changes de vignette, le
  masque du calque est recréé avec le feather de cette génération.

Si tu renommes un calque et retires son identifiant `[id]`, StableCraft ne peut plus
retrouver sa galerie. Les calques créés avant cette version n'ont pas d'identifiant et
n'ont donc pas de galerie rétroactive.

### Image de référence

Sous le prompt :

1. coche **Utiliser une image de référence** ;
2. clique sur la vignette pour ouvrir l'explorateur, ou dépose une image dessus ;
3. l'image est normalisée en PNG et stockée avec le calque ;
4. décris dans le prompt **ce que tu prends de la référence** et **où tu l'appliques**.

La référence est **propre au calque StableCraft courant** :

- elle est rechargée quand tu sélectionnes ce calque ;
- elle n'apparaît pas sur un autre calque ;
- une nouvelle sélection repart sans référence ;
- si tu changes de calque avant la première génération, la référence en attente est
  oubliée.

Profils compatibles : **Krea 2 Edit** et **FLUX.3 Klein**. FLUX.2 9B n'utilise pas la
référence.

Quand une référence est chargée, le modèle reçoit deux images :

- **image 1 = scène** : ton image PhotoCraft (le crop du lasso) ;
- **image 2 = référence** : l'image ajoutée.

Un system prompt n'est ajouté que dans ce cas. Sans image chargée, le workflow reste
strictement celui d'avant.

Exemples :

> Add the black leather glove from the reference image to the man's right hand.
> Keep the hand pose, arm, skin tone, lighting and background unchanged.

> Use the reference image for the fabric pattern only. Keep the garment shape,
> folds, lighting and the rest of the scene unchanged.

> Replace the surfboard's design with the pattern from the reference image.
> Keep the board shape, feet, water, splash and lighting unchanged.

Le bouton **Guide** à côté de `PROMPT` ouvre une fenêtre non bloquante avec ces
explications et d'autres exemples.

## Réglages conseillés

| Profil | Steps | CFG | Remarque |
|---|---:|---:|---|
| FLUX.3 Klein | 16 | 1.0 | défaut, meilleure fidélité locale |
| FLUX.2 Klein 9B | 4 | 1.0 | plus texturé, plus lourd |
| Krea 2 Edit | 8 | 1.0 | identité/style, peut changer la silhouette |

- **Contexte** : marge autour du lasso incluse dans le crop envoyé au modèle, mais pas
  dans le masque final. 96 px par défaut. Pour un petit objet ou un membre (jambe, main,
  visage), monte à 128–192 px pour donner plus de scène et d'attache anatomique au
  modèle. Au bord de l'image, cette marge est tronquée.
- **Feather** : 10 px par défaut. Descends à 4–6 px pour un bord net ; monte à 15–20 px
  pour un fondu doux.
- **Seed** : `-1` = aléatoire et valeur par défaut. Le champ n'est pas remplacé par le
  seed réel après génération. Mets une valeur fixe seulement si tu veux reproduire ou
  comparer ; pour régénérer, reviens à `-1` ou change la valeur.
- **Prompt** : décris le résultat, pas seulement le changement. Exemple :

  > Recolor the dress fabric to royal blue. Keep the exact silhouette, neckline,
  > skin, arms, legs, pose and background unchanged. Even studio lighting.

- Si le modèle change la silhouette ou la couleur au bord, c'est une limite des modèles
  d'édition instructionnelle. Un prompt plus précis et une sélection plus large
  (ourlet inclus) aident.

## Installer pour un usage quotidien

Pour ne plus lancer les trois commandes à la main :

```powershell
cd C:\DEV_Seb\SeBL4RD-Stable_Craft
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1 `
  -ConfigFile "C:\DEV_Seb\SeBL4RD-Stable_Craft\config.toml"
```

L'installateur :

- détecte PhotoCraft et le Python de ComfyUI (ou demande les chemins) ;
- copie l'UI, le bridge, la config et les docs dans
  `%USERPROFILE%\StableCraft` (hors AppData ; modifiable avec `-InstallDir`) ;
- crée un seul raccourci **StableCraft** (menu Démarrer et bureau) ;
- ne télécharge aucun modèle.

Ensuite, utilise **StableCraft.bat** (ou le raccourci **StableCraft**). Il lance
ComfyUI, PhotoCraft avec le control channel, puis l'UI.

Si l'auto-détection échoue :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1 `
  -PhotoCraft "D:\Programmes\photocraft-0.14.0-windows-x64-portable\photocraft.exe" `
  -ComfyPython "F:\ComfyUI_windows_portable\python_embeded\python.exe" `
  -ConfigFile "C:\DEV_Seb\SeBL4RD-Stable_Craft\config.toml"
```

## Où sont les fichiers

Rien n'est écrit dans AppData.

- **Config locale** : `config.toml` (gitignoré). Exemple public :
  `config.example.toml`.
- **Données utilisateur** : `user\` (configurable via `[app] sessions_dir`, mais doit
  rester sous `[photocraft] automation_root`)
  - `user\control.token` : token du control channel ;
  - `user\sessions\<id>\session.json` : sélection, réglages, document, galerie ;
  - `user\sessions\<id>\base.png` : composite figé au moment du lasso ;
  - `user\sessions\<id>\mask.png` : masque de sélection ;
  - `user\sessions\<id>\reference.png` + `reference_thumb.png` : image de référence
    du calque, si elle existe ;
  - `user\sessions\<id>\generations\<n>\result.png` + `thumb.png` ;
  - `user\logs\launcher.log` et `user\logs\ui.log`.
- **Modèles téléchargés** : `models\` (vide par défaut, voir `models\README.md`).
- **Lanceur ComfyUI sans navigateur** : `user\runtime\comfyui-no-browser.bat`,
  régénéré au démarrage à partir de `run_nvidia_gpu.bat`.
- **Journal UI** : panneau JOURNAL en bas (scrollbar).
- **Docs** : `docs/MODELS.md` (modèles, réglages, VRAM), `docs/TESTLOG.md`
  (validation), `docs/ARCHITECTURE.md` (design).

Les images générées par ComfyUI passent par `PreviewImage` dans le dossier `temp` de
ComfyUI, sont téléchargées par StableCraft puis supprimées. Le dossier `output` de
ComfyUI n'est plus utilisé.

### Notifications de PhotoCraft

Les cartes qui apparaissent en bas à droite sont des **notices PhotoCraft**, pas des
popups StableCraft. Elles étaient déclenchées par `app.save` quand PhotoCraft aplatissait
un PNG multicouche (« layers flattened »). StableCraft duplique maintenant le document
en version fusionnée avant de l'enregistrer : l'aplatissement n'a plus lieu sur le
document multicouche, donc plus de notice pour les captures `base.png` et `after.png`.
Les autres notices PhotoCraft (erreurs, avertissements d'import) peuvent toujours
apparaître ; elles viennent de PhotoCraft et disparaissent selon ses préférences
d'interface.

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `PhotoCraft : déconnecté` | PhotoCraft lancé sans `--control`, mauvais port/token | relance avec la commande du §2 ; vérifie `control_token_file` |
| « PhotoCraft à redémarrer » | PhotoCraft tourne encore avec l'ancien `automation_root` | ferme complètement PhotoCraft, puis relance `StableCraft.bat` |
| `result.png` en masse dans « Ouvrir un fichier récent » | anciennes ouvertures techniques du bridge | nettoyé au prochain lancement de `StableCraft.bat` et après chaque génération |
| ComfyUI ouvre une page web au démarrage | `--auto-launch` forcé par `--windows-standalone-build` | StableCraft ajoute `--disable-auto-launch` ; mets `[comfyui] disable_browser = false` pour retrouver l'ancien comportement |
| `PhotoCraft : connecté (aucun document)` | aucune image ouverte | ouvre une image |
| `Sélection : aucune` | pas de lasso actif | fais une sélection, ou clique un calque `StableCraft [id]` puis Régénérer (sélection stockée) |
| `Régénérer` grisé, « existe déjà » | seed fixe identique à une génération | mets le seed à `-1` ou change le prompt |
| Case « Image de référence » grisée | profil FLUX.2 sélectionné | passe sur Krea 2 ou FLUX.3 Klein |
| La référence n'a aucun effet | case décochée, vignette vide, ou prompt ne dit pas quoi reprendre | coche la case, charge l'image et décris « use the reference image for… » |
| La référence copie son fond | image de référence trop large | utilise un crop propre de l'objet sur un fond simple |
| `ComfyUI : déconnecté` | ComfyUI arrêté ou mauvais port | lance `run_nvidia_gpu.bat` ; vérifie `endpoint` |
| `Modèles manquants : X` | fichier invisible par ComfyUI | vérifie `config.toml` et `extra_model_paths.yaml` |
| `ComfyUI error in KSampler` | mauvais encodeur/loader | FLUX.3/Krea2 : Qwen3-VL FP8 ; FLUX.2 : Qwen3-8B GGUF |
| `Python ComfyUI introuvable` | `[comfyui] python` absent | mets le chemin de `python_embeded\python.exe` |
| `Aucune sélection` alors que le lasso existe | statut pas encore rafraîchi | attends 3 s ou change de profil puis revient |
| Bord rose/ancienne couleur | feather + résultat plus court que la sélection | sélectionne l'ourlet, baisse le feather, ou augmente le contexte |
| `WinError 10053` | connexion de contrôle fermée pendant le sampling | le bridge se reconnecte ; relance si nécessaire |

## Limites

- L'UI est une fenêtre séparée, pas un panneau docké dans PhotoCraft.
- L'installateur PowerShell nécessite Python 3.11+ avec Tkinter. Un bundle `.exe`
  est prévu.
- Pas encore de téléchargement de modèles dans l'UI : les profils manquants sont
  signalés et Générer est désactivé. Le model manager avec consentement est la suite.
- Pas de batch/outpaint.
- La galerie est liée au nom du calque (`StableCraft [id]`). Renommer le calque en
  retirant l'identifiant casse le lien.
- Changer de génération remplace le contenu et le masque du calque : les retouches
  manuelles du masque sur cette génération sont perdues.
- Les documents CMYK/Lab/16 bits et 4K ne sont pas encore testés ; utilise du RGB 8 bits
  pour l'instant.
- Krea 2 Edit peut modifier la silhouette ; FLUX.2 9B est plus lourd (offload sur 12 Go).

## Test recommandé

1. FLUX.3, lasso sur la robe, prompt « recolor … keep everything else unchanged »,
   Contexte 96, Feather 10.
2. Même sélection avec FLUX.2 9B, 4 steps : compare la texture et la fidélité.
3. Même sélection avec Krea 2 Edit, 8 steps : compare l'identité/style.
4. Annule les calques non retenus, garde le meilleur, puis teste un prompt plus
   complexe (remplacer un objet, changer un fond, ajouter un accessoire).

Note ce qui te gêne (vitesse, fidélité, bord, UI) : ce sera la base des prochains
réglages.
