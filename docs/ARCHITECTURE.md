# Architecture — StableCraft sans fork

> Décision : **pas de fork de PhotoCraft**. StableCraft est une application compagne
> installable qui se greffe à une installation PhotoCraft existante via son **control
> channel** local, et qui parle à **ComfyUI** en HTTP. PhotoCraft reste intact et se met
> à jour normalement.

## 1. Pourquoi un compagnon, et pas un plugin dans l'app ?

Le SDK de plugins PhotoCraft (ABI v1) accepte uniquement des **filtres WebAssembly** :

- aucun import hôte (pas de réseau, pas de fichiers, pas d'horloge) ;
- pas de panneau UI ;
- pas d'accès aux calques, à la sélection ou au composite.

Il est donc impossible d'héberger un panneau IA + client HTTP dans un plugin v1.
Deux options existaient :

1. forker PhotoCraft (rejeté : maintenance trop lourde) ;
2. piloter PhotoCraft de l'extérieur via son **control channel** (retenu).

Le control channel est l'API d'automatisation officielle de PhotoCraft : TCP loopback,
authentification par token, commandes JSON. C'est exactement ce qu'utilisent les agents
et le serveur MCP. On l'utilise comme une API de plugin, sans modifier l'application.

### Ce qu'on peut faire

- Lire l'état du document, la sélection, les calques, l'historique.
- Sauvegarder le composite et le masque en PNG temporaires.
- Ouvrir le résultat, le copier dans le document original, créer un calque masqué.
- Déclencher des commandes, annuler, fermer des documents temporaires.
- Détecter la version et les commandes disponibles.

### Ce qu'on ne peut pas faire (v1)

- Afficher un panneau **dans** la fenêtre de PhotoCraft (ce serait un fork ou un
  changement upstream).
- Récupérer le composite ou le masque **en mémoire** (il faut passer par `app.save`).
- Être notifié en temps réel des changements de sélection (on lit à la demande).
- Regrouper plusieurs commandes en une seule étape d'undo (on peut enchaîner, mais
  chaque commande peut créer son étape).

Ces limites sont acceptables pour le MVP. Si le projet prend, on pourra proposer un
petit patch upstream (commande `document.renderPreview` + panneau) sans maintenir un fork.

## 2. Vue d'ensemble

```
┌─────────────────────────────┐        TCP JSON (loopback)        ┌──────────────────┐
│ StableCraft (UI + bridge)   │ ◄────────────────────────────────► │ PhotoCraft       │
│  - prompt / profils         │   control channel + token          │  (installation   │
│  - crops / masques          │                                    │   officielle)    │
│  - previews                 │                                    └──────────────────┘
│  - config / model manager   │
└──────────────┬──────────────┘
               │ HTTP (loopback)
               ▼
┌─────────────────────────────┐
│ ComfyUI                     │
│  /system_stats              │
│  /upload/image              │
│  /prompt  /history  /view   │
│  /interrupt  /queue         │
└─────────────────────────────┘
```

Trois composants :

1. **StableCraft Bridge** : logique Python (ou Rust) qui parle aux deux APIs, prépare
   les images, construit les workflows, applique les résultats.
2. **StableCraft UI** : panneau flottant (Qt/PySide6 recommandé) avec prompt, profils,
   réglages, vignettes, progression.
3. **StableCraft Installer** : détecte PhotoCraft et ComfyUI, crée les raccourcis,
   écrit la config, installe les dépendances, propose les modèles manquants.

## 3. Flux « lasso → prompt → résultat »

```
1. L'utilisateur dessine un lasso dans PhotoCraft.
2. Il clique « Générer » dans StableCraft.
3. Bridge : document.inspect → index du document, bounds de sélection, calque actif.
4. Bridge : app.save → composite.png (document aplati, PNG).
5. Bridge : channel.duplicate {channel:"selection", document:"new"} → mask doc.
6. Bridge : app.save → mask.png ; file.close du mask doc ; réactiver l'original.
7. Bridge : lit mask.png, calcule la bbox, ajoute le contexte, aligne sur 16 px.
8. Bridge : crop composite + mask, feather, upload dans ComfyUI.
9. Bridge : POST /prompt avec le workflow du profil choisi.
10. Bridge : poll /history, télécharge le PNG via /view.
11. Bridge : resize au crop, recompose dans le crop, écrit result.png.
12. Bridge : app.open result.png → doc temporaire.
13. Bridge : layer.copyToDocument {document: original, source: temp,
             layers:[result_layer], offset:[x0,y0], name:"StableCraft — …"}.
14. Bridge : (optionnel) layer.layerMask.revealSelection pour un masque éditable.
15. Bridge : file.close du doc temporaire, réactive l'original.
16. L'utilisateur voit la preview et peut annuler (edit.undo) ou garder.
```

### Détails importants

- **Coordonnées** : `layer.copyToDocument` accepte `offset: [dx, dy]` depuis la place
  du calque dans le document source. Le PNG de résultat est un document de la taille
  du crop, à (0,0) ; l'offset est donc `[x0, y0]`.
- **Masque** : le PNG de résultat peut déjà contenir l'alpha de la sélection. C'est la
  voie la plus fiable pour le MVP. Ensuite, on peut ajouter un masque de calque
  éditable via `layer.layerMask.revealSelection` si la sélection est encore active.
- **Sélection perdue** : si `layer.copyToDocument` ou l'activation du document
  original efface la sélection, recharger le masque depuis un canal alpha sauvegardé
  (`select.saveSelection` / `select.loadSelection`) ou utiliser l'alpha du PNG.
- **Undo** : `layer.copyToDocument` est une étape ; le masque peut en ajouter une
  seconde. Si on veut une seule étape, on bake l'alpha et on n'ajoute pas de masque.
- **Couleur** : `app.save` écrit un PNG converti depuis le document. Pour les
  documents CMYK/Lab/16/32 bits, vérifier le résultat et prévoir une conversion via le
  profil du document avant l'insertion. MVP : RGB 8 bits.
- **Performance** : `app.save` écrit le document entier. Pour un 4K, compter quelques
  secondes et ~50 Mo par génération. Le mask doc est en grayscale, plus léger.
- **Annulation** : `POST /interrupt` pour ComfyUI ; si le résultat n'est pas encore
  appliqué, il suffit d'arrêter le job. Après application, `edit.undo`.

## 4. Compatibilité avec les builds PhotoCraft

### Principe : détection de capacités, pas seulement de version

Un numéro de version seul est fragile. Au démarrage, StableCraft :

1. se connecte au control channel ;
2. appelle `engine.commands` et récupère les IDs disponibles ;
3. vérifie une liste de commandes requises :

```
app.open
app.save
document.inspect
document.activate
channel.duplicate
file.close
layer.copyToDocument
layer.layerMask.revealSelection
layer.select
select.saveSelection
select.loadSelection
edit.undo
```

4. appelle `ui.inspect` et vérifie les champs utilisés (`document`, `selectionBounds`,
   `selectedLayers`, etc.) ;
5. lance éventuellement un **self-test** dans un document temporaire :
   créer un document, faire une sélection, sauvegarder, dupliquer le canal, copier un
   calque, fermer. Ce test valide le comportement réel, pas seulement la présence des
   commandes.

Si une commande manque, l'application affiche :

> PhotoCraft 0.15.0 détecté. La commande `layer.copyToDocument` a changé ou disparu.
> StableCraft 0.1.x est testé avec PhotoCraft 0.14.0. Mettez à jour StableCraft ou
> utilisez une build compatible.

### Matrice de compatibilité

Fichier `compat.toml` dans le repo :

```toml
[[tested]]
stablecraft = "0.1.x"
photocraft = "0.14.0"
os = "windows-x64"
status = "tested"
notes = "Control channel + calques + masque vérifiés."

[[tested]]
stablecraft = "0.1.x"
photocraft = "0.13.x"
os = "windows-x64"
status = "untested"
notes = "À vérifier ; les commandes de base existent."
```

L'application affiche la version testée et un avertissement pour les builds non
testées. On peut aussi lire la version de `photocraft.exe` (ressource Windows) ou la
version renvoyée par le help/system info si elle existe. Le control channel n'expose
pas forcément la version ; la détection de commandes reste la source de vérité.

### Versionnement

- `StableCraft 0.1.0` : première version publique.
- Le numéro de build peut inclure la compatibilité testée :
  `0.1.0+pc0.14.0`.
- L'installateur affiche : « Testé avec PhotoCraft 0.14.0 ; vérification des capacités
  au premier lancement. »

## 5. Gestion des modèles et configuration

### Principe

- **Aucun modèle n'est obligatoire** pour installer StableCraft.
- Si l'utilisateur n'utilise pas un profil, il n'a pas à renseigner ses chemins.
- StableCraft interroge ComfyUI (`/object_info`) pour savoir quels fichiers sont
  visibles. C'est la source de vérité pour les noms de fichiers.
- Si un profil est choisi et qu'un fichier manque, StableCraft propose un
  téléchargement **avec consentement** : taille, chemin de destination, licence,
  URL. Jamais de téléchargement silencieux.
- Les modèles sont stockés par défaut dans `<dossier StableCraft>/models`, à côté de
  `user/`. Rien n'est écrit dans AppData. Le chemin reste configurable via
  `[models] store_dir`.
- Pour que ComfyUI voie ce dossier, l'installateur peut :
  1. écrire une section `stablecraft` dans `extra_model_paths.yaml` (avec sauvegarde) ;
  2. ou créer des junctions/symlinks depuis les dossiers `models/` de ComfyUI ;
  3. ou demander à l'utilisateur d'ajouter le chemin et redémarrer ComfyUI.
  L'option 1 est la plus propre ; elle est proposée, jamais imposée.

### `config.toml`

Un exemple complet est fourni dans `config.example.toml`. Les chemins sont
**optionnels** et commentés. Priorité :

1. `--config <path>` ;
2. `%APPDATA%\StableCraft\config.toml` ;
3. `config.toml` à côté de l'exécutable (mode portable) ;
4. valeurs par défaut.

Extrait :

```toml
[comfyui]
endpoint = "http://127.0.0.1:12452"

[models]
# Dossier des téléchargements. Vide = dossier dédié de l'application.
# models_dir = "F:/IA/StableCraft/models"

[models.flux3_klein]
# Tous les chemins sont optionnels. Si absents, StableCraft utilise ce que
# ComfyUI voit déjà.
# unet = "F:/IA/Models IA/Checkpoints/flux-3-image-klein-Q8_0.gguf"
# text_encoder = "F:/Stable Diffusion/.../Qwen-3-VL-4B-Scaled-FP8-v2.safetensors"
# vae = "F:/Stable Diffusion/.../flux2_vae.safetensors"
enabled = true
steps = 16
cfg = 1.0

[models.flux2_klein_9b]
enabled = false
steps = 4
cfg = 1.0

[models.krea2_edit]
enabled = false
steps = 8
cfg = 1.0
```

### Manifeste des modèles

`models.json` (dans le repo) décrit chaque profil :

```json
{
  "profiles": {
    "flux3_klein": {
      "label": "FLUX.3 Klein Edit",
      "license": "FLUX Kommunity License",
      "source": "https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy",
      "vram_gb": 12,
      "files": {
        "unet": {
          "filename": "flux-3-image-klein-Q8_0.gguf",
          "folder": "unet",
          "size": 6092755872,
          "sha256": "…",
          "url": "…"
        },
        "text_encoder": { "filename": "Qwen-3-VL-4B-Scaled-FP8-v2.safetensors", "folder": "text_encoders", "size": 5610000000 },
        "vae": { "filename": "flux2_vae.safetensors", "folder": "vae", "size": 335000000 }
      },
      "settings": { "steps": 16, "cfg": 1.0, "sampler": "euler", "scheduler": "simple" }
    }
  }
}
```

L'application :

- compare les noms de fichiers aux listes de `/object_info` ;
- marque chaque profil `installed` / `missing` / `partial` ;
- affiche la taille totale et la VRAM estimée ;
- propose « Télécharger » (dialogue de consentement) ou « Choisir un dossier » ;
- ne télécharge jamais un modèle sans action explicite ;
- vérifie le SHA256 quand il est connu ;
- ouvre la page Hugging Face pour les modèles sous licence/gated.

### Ce qui n'est pas requis

- Un utilisateur qui ne fait que du FLUX.3 n'a pas besoin de configurer FLUX.2,
  Krea 2, Qwen, etc.
- Un utilisateur qui a déjà tout dans ComfyUI n'a pas besoin de `models_dir`.
- Un utilisateur qui ne veut pas télécharger peut utiliser « Choisir un dossier »
  ou ignorer le profil.

## 6. Choix de la stack UI

### MVP : Python + Tkinter (retenu)

- Python 3.11 est déjà présent ; Tkinter est inclus, donc **zéro téléchargement**.
- L'UI ne fait que du stdlib : statut, formulaires, previews, sous-processus.
- Le bridge tourne dans le Python embarqué de ComfyUI (Pillow + requests déjà là).
- Itération rapide, facile à contribuer pour un repo public.
- Inconvénient : look Tkinter basique ; on peut passer à PySide6 plus tard sans
  réécrire le bridge.

### Alternative : Python + PySide6

- Meilleur rendu, tray, raccourcis globaux, dialogues de fichiers.
- Nécessite ~200 Mo de dépendances ; à envisager pour la version publique si le look
  devient un critère.
- Packaging : PyInstaller/Nuitka + Inno Setup.

### Alternative : Rust + egui

- Un seul exécutable, aligné avec PhotoCraft, pas de runtime Python.
- Plus de travail pour l'UI et les dialogues ; build Rust nécessaire.

Le **bridge** est isolé de l'UI (`prototypes/bridge_cli.py` + `control_client.py`)
pour permettre un portage PySide6/Rust plus tard sans réécrire la logique.

## 7. UI / UX

- Panneau flottant compact, thème sombre, toujours au-dessus en option.
- Peut s'aligner à droite de la fenêtre PhotoCraft (suivi de position via Win32 ;
  fallback : position mémorisée).
- Raccourci global configurable (ex. `Ctrl+Alt+G`) pour générer.
- Barre d'état : PhotoCraft connecté (version), ComfyUI connecté (version/GPU),
  profil actif, VRAM libre.
- Prompt + negative prompt (collapsible), bouton « Améliorer le prompt » plus tard.
- Profil : menu avec badge `installé` / `manquant`, taille, VRAM.
- Réglages : mode (sélection / calque actif / canvas), padding, feather, steps, CFG,
  seed, batch.
- Progression : étape ComfyUI (upload, sampling, decode), temps écoulé, bouton
  Annuler.
- Galerie par calque : chaque session garde ses générations ; clic sur une vignette
  applique cette génération au calque, sans relancer ComfyUI.
- Régénération sur la même sélection : même calque, `base.png` figé, seed identique
  bloqué pour éviter les doublons.
- Historique des générations (prompt, seed, profil) dans `session.json`.
- Messages d'erreur actionnables : ComfyUI down, modèle manquant, nœud custom
  manquant, sélection vide, document non RGB.

## 8. Installation et mise à jour

### Installateur Windows (Inno Setup)

1. Vérifie Windows x64, Python si build source, ou installe le bundle.
2. Cherche PhotoCraft :
   - registre/uninstall entries ;
   - `%LOCALAPPDATA%\Programs\PhotoCraft` ;
   - `C:\Program Files\PhotoCraft` ;
   - sinon, demande le chemin de `photocraft.exe`.
3. Cherche ComfyUI :
   - `ComfyUI_windows_portable` dans les lecteurs ;
   - `extra_model_paths.yaml` ;
   - sinon, demande l'endpoint et le dossier `models`.
4. Écrit `config.toml` avec les chemins détectés (sans écraser une config existante).
5. Crée **un seul raccourci** « StableCraft » vers `StableCraft.bat`.
6. `StableCraft.bat` lance ComfyUI, PhotoCraft avec
   `--control 7878 --control-token-file … --automation-read-root … --automation-write-root …`,
   puis l'UI. Si un chemin obligatoire manque, message clair et arrêt.
7. Propose d'ajouter le dossier de modèles à ComfyUI (`extra_model_paths.yaml`).
8. Ne télécharge aucun modèle à l'installation.

### Données locales et sorties ComfyUI

```
<dossier StableCraft>/
  user/
    control.token
    sessions/<id>/
      session.json
      base.png        # composite figé au moment du lasso
      mask.png
      reference.png   # image de référence propre au calque
      reference_thumb.png
      generations/<n>/result.png, thumb.png
    logs/
  models/             # téléchargements consentis, vide par défaut
```

`user/` est le `automation_root` de PhotoCraft : les échanges de fichiers restent dans
ce bac à sable. Rien n'est écrit dans AppData.

Les workflows utilisent `PreviewImage` (et non `SaveImage`) : ComfyUI écrit l'image
dans son dossier `temp`, StableCraft la télécharge puis la supprime. Le dossier
`output` de ComfyUI n'est pas touché.

Pour capturer `base.png` / `after.png`, StableCraft duplique le document en version
fusionnée (`image.duplicate mergedOnly`), enregistre ce duplicata en PNG, puis le ferme.
Un document à un seul calque n'affiche pas l'avertissement « layers flattened » de
PhotoCraft : aucune notice ne s'affiche en bas à droite.

### Image de référence

La référence est stockée par session (`reference.png`) et jamais composée directement.
Elle est envoyée comme **deuxième image** :

- Krea 2 : `source_image` = scène, `source_image_b` = référence ;
  `Krea2EditGroundedEncode` reçoit `image` + `image_b`, avec un system prompt qui nomme
  image 1 (scène) et image 2 (référence) ;
- FLUX.3 : `ReferenceMultiLatent` reçoit `images.image0` (scène) et `images.image1`
  (référence), avec un préfixe de prompt explicite.

Le system prompt, le second latent et le préfixe ne sont ajoutés que si une image de
référence est réellement chargée. Sans référence, le workflow est inchangé. FLUX.2 9B
n'utilise pas la référence.

### Mise à jour

- StableCraft vérifie ses propres releases (optionnel, désactivable).
- PhotoCraft se met à jour indépendamment ; au lancement, StableCraft refait le
  contrôle de capacités.
- Si une commande a changé, message clair et lien vers la matrice de compatibilité.

## 9. Sécurité

- Control channel : token 256 bits, fichier protégé (ACL utilisateur), loopback only.
- ComfyUI : endpoint loopback par défaut ; URL distante interdite sans opt-in.
- Aucune télémétrie, aucun envoi d'image hors de la machine par défaut.
- Les prompts et images ne quittent la machine que si l'utilisateur configure un
  ComfyUI distant.
- Les téléchargements de modèles sont explicites, avec URL et hash.
- Les fichiers temporaires sont dans un dossier dédié, nettoyés au démarrage et à la
  fermeture.
- Ne pas exécuter de code arbitraire provenant d'un workflow ComfyUI non fiable :
  les workflows personnalisés sont une fonction avancée, avec avertissement.

## 10. Limites connues et plan de sortie

| Limite | Contournement | Sortie |
|---|---|---|
| Pas de panneau dans PhotoCraft | Fenêtre flottante alignée | PR upstream `document.renderPreview` + panneau |
| Composite via fichier | `app.save` + cache par révision | Commande upstream de rendu mémoire |
| Sélection non temps réel | Lecture au clic Générer | Événement upstream |
| Deux étapes d'undo | Baker l'alpha | Commande de transaction upstream |
| Dépendance au control channel | Détection de capacités | API stable / MCP |
| ComfyUI doit tourner | Lancer/détecter au démarrage | Gestion du processus ComfyUI |

## 11. Découpage MVP

**MVP = Minimum Viable Product** : la plus petite version qui rend le service principal,
pas la version finale.

### Dans le MVP

- Installateur Windows + config.
- Connexion PhotoCraft (control channel) + ComfyUI.
- Trois profils : **FLUX.3 Klein (défaut)**, **FLUX.2 Klein 9B**, **Krea 2 Edit**.
- Lasso → prompt → preview → nouveau calque + masque de calque featheré.
- Détection des modèles locaux, message si manquant, aucun téléchargement automatique.
- Annulation, erreurs lisibles, log local.
- Testé sur PhotoCraft 0.14.0 + ComfyUI 0.42.1 + RTX 3080 Ti 12 Go.

### Hors MVP (phases suivantes)

- FLUX.2 Klein 4B (profil basse VRAM), Qwen-Image-Edit.
- Batch de variantes, historique, presets.
- Outpaint, upscale, suppression d'objet.
- Téléchargement assisté des modèles.
- Panneau natif upstream.
- macOS/Linux.

## 12. Validation du 23/10/2026

Le control channel a été testé avec PhotoCraft portable **0.14.0** et ComfyUI 0.42.1 :

- `select.lasso`, `document.inspect` : bounds corrects.
- `app.save` du composite, puis crop.
- `select.saveSelection` (création et remplacement du canal « StableCraft Mask »).
- `channel.duplicate` vers un document grayscale, `app.save`, `file.close`.
- `layer.copyToDocument` : offset, bounds, nom, sélection préservée.
- `layer.layerMask.revealSelection`, `layer.layerMask.edit {feather}`.
- `select.loadSelection` : sélection restaurée.
- `app.open` d'un PNG dans un sous-dossier du write root.
- Capture UI avec calque, masque, densité, feather.

Le prototype [`../prototypes/bridge_cli.py`](../prototypes/bridge_cli.py) exécute tout
le flux. Preuves visuelles : `docs/demo/photocraft-bridge.png` et
`docs/demo/photocraft-flux3-blue.png`.

### Pièges

- PhotoCraft ferme parfois une connexion de contrôle inactive pendant le sampling
  ComfyUI (~30 s). Le bridge se reconnecte avant l'application.
- `app.save` d'un PNG aplati avertit que les calques/masques ne sont pas conservés ;
  le document PhotoCraft, lui, garde tout.
- Ne pas `app.open` un fichier encore en cours d'écriture.

### Prochaines étapes

1. Bundle PyInstaller + Inno Setup (supprimer la dépendance au Python système).
2. Model manager (détection ComfyUI, consentement, dossier dédié).
3. Batch, outpaint, FLUX.2 Klein 4B.
4. Tests CMYK/Lab/16 bits et documents 4K.
6. PR upstream éventuelle pour un panneau natif.
