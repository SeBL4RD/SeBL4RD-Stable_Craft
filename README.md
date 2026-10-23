# StableCraft

**Le geste de Stable.art, ressuscité pour PhotoCraft, avec ComfyUI comme moteur.**

On sélectionne une zone au lasso, on écrit ce qu'on veut changer, et le résultat arrive
dans un nouveau calque — sans toucher aux pixels d'origine. Le tout en local, sur sa GPU,
avec des modèles récents quantifiés en GGUF.

> **Statut** : preuve de concept validée le 23/10/2026. Le backend ComfyUI fonctionne,
> et le **control channel de PhotoCraft 0.14.0 est validé de bout en bout** : lasso →
> composite → FLUX.3 → nouveau calque + masque de calque featheré. L'intégration est
> conçue comme une **application compagne installable**, sans fork de PhotoCraft.

---

## La décision : pas de fork

PhotoCraft est activement maintenu ; maintenir un fork serait pénible. Ses plugins
officiels sont des **filtres WebAssembly sandboxés** : pas de réseau, pas d'UI, pas
d'accès aux calques. Un panneau IA ne peut donc pas être un plugin v1.

StableCraft sera donc une **application compagne** qui :

- s'installe à côté d'une installation PhotoCraft existante ;
- se connecte à son **control channel** local (l'API d'automatisation officielle) ;
- parle à **ComfyUI** en HTTP ;
- lit la sélection, sauvegarde composite + masque, génère, puis insère le résultat
  comme nouveau calque masqué.

PhotoCraft n'est pas modifié et se met à jour normalement. La compatibilité sera
vérifiée **par capacités** (`engine.commands`) et non par un simple numéro de version :
si une commande change, StableCraft le dit clairement.

Voir [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) pour le détail, les limites et le
plan de sortie (PR upstream d'un panneau natif plus tard, si le projet prend).

---

## Ce qui est déjà prouvé

Machine de test : **RTX 3080 Ti 12 Go**, 32 Go RAM, ComfyUI 0.42.1 sur le port `12452`.

| Test | Résultat |
|---|---|
| Édition globale **FLUX.3 Klein Q8** | ✅ robe bleue + fond coucher de soleil, personnage/pose conservés, ~34 s |
| **Lasso → crop contexte → édition → recomposition masquée** | ✅ robe verte, fond intact, contour fondu |
| **FLUX.2 Klein 9B Q8** sur le même crop | ✅ plus texturé, mais réinterprète davantage la silhouette |
| **Krea 2 Edit Q4** (`krea2_turbo_edit`) | ✅ robe verte très propre, fond/personnage préservés, silhouette modifiée |
| **PhotoCraft 0.14.0 control channel** | ✅ lasso → `app.save` → ComfyUI → `layer.copyToDocument` → masque + feather |
| Encodage texte | ⚠️ les GGUF Qwen3-VL ne marchent **pas** pour FLUX.3 ni Krea 2 ; il faut le FP8 safetensors |

Images dans [`docs/demo/`](docs/demo) :

- `photocraft-bridge.png` : PhotoCraft avec le calque StableCraft, son masque et le feather 10 px
- `photocraft-flux3-blue.png` : résultat du bridge (robe bleue)
- `stablecraft-ui.png` : l'UI Tkinter du MVP
- `lasso-before.png` → `lasso-after-flux3.png`
- `comparison-original-flux3-flux2.png`
- `krea2-edit.png`

Recherche détaillée sur les modèles, variantes « Edit », réglages CFG/steps, encodeurs
et budgets VRAM : [`docs/MODELS.md`](docs/MODELS.md).

---

## Modèles recommandés

| Profil | Poids locaux | Steps / CFG | Usage |
|---|---|---:|---|
| **FLUX.3 Klein Edit** (défaut) | 11,6 Go | 16 / 1.0 | lasso, meilleure fidélité, 12 Go |
| FLUX.2 Klein 9B Edit | 14,3 Go | 4 / 1.0 | qualité/texture, 12 Go avec offload |
| Krea 2 Edit | 12,6 Go | 8 / 1.0 | identité/style, nœuds `krea2edit` |
| FLUX.2 Klein 4B (public, à venir) | ~5–10 Go | 4 / 1.0 | 8 Go VRAM |
| Qwen-Image-Edit 2509 | ~17 Go | 8–50 | trop lourd pour 12 Go, pas local |

Les poids ne sont **pas** redistribués. Chaque utilisateur installe ses fichiers dans
ComfyUI ou dans le dossier dédié de StableCraft. Les licences des modèles s'appliquent
(FLUX Kommunity, Krea Community, etc.).

---

## Configuration et modèles

- [`config.example.toml`](config.example.toml) : toutes les options, tous les chemins
  commentés. **Aucun chemin de modèle n'est obligatoire.**
- Les modèles sont détectés via ComfyUI (`/object_info`). Si un profil est activé et
  qu'un fichier manque, StableCraft propose un téléchargement **avec consentement**
  (taille, chemin, licence, URL). Jamais de téléchargement silencieux.
- Dossier par défaut : `%LOCALAPPDATA%\StableCraft\models` (Windows). L'installateur
  peut ajouter ce dossier à `extra_model_paths.yaml` de ComfyUI, ou l'utilisateur peut
  pointer ses propres chemins.
- Un utilisateur qui ne se sert que de FLUX.3 n'a rien à configurer pour les autres.

---

## MVP, c'est quoi ?

**MVP = Minimum Viable Product** : la plus petite version qui rend le service principal,
pas la version finale.

Le MVP StableCraft :

1. s'installe et détecte PhotoCraft + ComfyUI ;
2. connecte le control channel et vérifie les commandes ;
3. propose **un seul profil** : FLUX.3 Klein Edit ;
4. fait lasso → prompt → preview → nouveau calque masqué ;
5. gère l'annulation et les erreurs lisibles ;
6. ne télécharge aucun modèle sans accord.

Hors MVP : FLUX.2, Krea 2, batch, outpaint, model manager complet, panneau natif,
macOS/Linux.

---

## Prototypes

### 1. Backend seul, sans PhotoCraft

[`prototypes/stablecraft_proto.py`](prototypes/stablecraft_proto.py) reproduit le flux
sur une image de test avec un lasso synthétique : crop + contexte, ComfyUI, recomposition
masquée, `before.png` / `after.png`.

```powershell
F:\ComfyUI_windows_portable\python_embeded\python.exe prototypes\stablecraft_proto.py
```

### 2. Bridge complet avec PhotoCraft (validé)

[`prototypes/bridge_cli.py`](prototypes/bridge_cli.py) fait le vrai flux :

1. lit la sélection active via `document.inspect` ;
2. sauvegarde le composite avec `app.save` ;
3. crop avec contexte et alignement 16 px ;
4. génère avec FLUX.3 Klein dans ComfyUI ;
5. ouvre le résultat et le copie dans le document avec `layer.copyToDocument` ;
6. crée le masque de calque depuis la sélection (`layer.layerMask.revealSelection`) ;
7. applique le feather (`layer.layerMask.edit`) et restaure la sélection.

Lance PhotoCraft avec le control channel :

```powershell
photocraft.exe --control 7878 `
  --control-token-file C:\...\StableCraft\control.token `
  --automation-read-root C:\...\StableCraft\tmp `
  --automation-write-root C:\...\StableCraft\tmp
```

Fais un lasso dans PhotoCraft, puis :

```powershell
F:\ComfyUI_windows_portable\python_embeded\python.exe prototypes\bridge_cli.py `
  --config config.toml `
  --prompt "Change the dress to royal blue, keep the pose and background" `
  --save-preview
```

Options utiles : `--dry-run` (géométrie seulement), `--no-apply` (génère sans insérer),
`--padding`, `--feather`, `--steps`, `--seed`.

Le bridge tourne avec le Python embarqué de ComfyUI (Pillow + requests déjà présents).
Avec un Python système 3.11+ : `pip install -r prototypes/requirements.txt`.

Détail important : PhotoCraft peut fermer une connexion de contrôle restée inactive
pendant le sampling ComfyUI. Le bridge se reconnecte avant la phase d'application.

### 3. UI Tkinter (MVP)

[`prototypes/stablecraft_ui.py`](prototypes/stablecraft_ui.py) est l'UI du MVP :
statut PhotoCraft/ComfyUI, document et sélection, prompt, profil, réglages,
Générer/Annuler, progression, aperçu et journal.

- **Zéro téléchargement** : uniquement la stdlib + Tkinter.
- Le bridge tourne dans le Python embarqué de ComfyUI (config `[comfyui] python`).
- L'UI se connecte directement au control channel pour le statut et la sélection.

```powershell
python prototypes\stablecraft_ui.py --config config.toml
```

Le bouton Générer vérifie la connexion, la sélection et le profil, puis lance le bridge.
En cas d'erreur (modèle manquant, ComfyUI down, sélection vide), le message est dans le
journal et dans la barre de statut.

### 4. Installateur

[`installer/install.ps1`](installer/install.ps1) installe StableCraft à côté de
PhotoCraft : détection des chemins, config, token, dossier temporaire, lanceur
« PhotoCraft + StableCraft » et raccourcis. Aucun modèle n'est téléchargé.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1
```

Voir [`installer/README.md`](installer/README.md) pour les options et les prérequis.

Workflows API validés : [`workflows/`](workflows).

---

## Prochaines étapes

1. **Bundle PyInstaller + Inno Setup** : supprimer la dépendance au Python système et
   produire un vrai installeur `.exe`.
2. **Model manager** : détection via ComfyUI, profils, téléchargements avec consentement.
3. **FLUX.2 / Krea 2**, batch, outpaint.
4. **MVP public**, puis PR upstream éventuelle pour un panneau natif.

Voir [`docs/BRIEF.md`](docs/BRIEF.md) (recherche Stable.art/PhotoCraft),
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (compagnon + installateur),
[`docs/MODELS.md`](docs/MODELS.md) (modèles et réglages) et
[`docs/TESTLOG.md`](docs/TESTLOG.md) (journal de validation).
