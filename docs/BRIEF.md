# Brief de projet — StableCraft

> Recherche menée le 23/10/2026 sur les dépôts `isekaidev/stable.art` et
> `storytold/photocraft`, et sur l'installation ComfyUI locale.

## 1. Stable.art : ce qui marchait, et pourquoi c'est mort

Stable.art est un plugin Photoshop **UXP** en Vue 2.7 qui parle à Automatic1111
(`/sdapi/v1/img2img`, `/sdapi/v1/txt2img`). Il n'a plus été maintenu depuis mars 2023.
Les causes de rupture sont structurelles :

- Photoshop a changé son API UXP et ses manifests ; le plugin `v0.0.1` n'a pas suivi.
- A1111 a déprécié `sampler_index` au profit de `sampler_name` ; le payload du plugin
  n'est plus conforme.
- Le build de production chargeait du code distant (`https://stable.art/plugin-code`),
  ce qui est à la fois fragile et un problème de sécurité.
- Aucun test réel : le seul fichier de test est entièrement commenté.
- Les erreurs partaient dans Sentry avec des pièces jointes (prompts, images).

### Le flux « magique » à reproduire

1. **Sélection quelconque** (lasso, baguette, quick selection) → dupliquée dans un
   canal alpha `stableart_mask`.
2. **Export du composite** aplati, puis export d'un masque noir/blanc via des calques
   de remplissage temporaires.
3. **BBox du masque**, expansion à au moins 512×512, crop de l'image et du masque.
4. **A1111 img2img/inpaint** : `denoising_strength` 0.75, `mask_blur` 4,
   `inpaint_full_res` true, padding 32.
5. **Placement** du résultat dans la sélection d'origine via `placeEvent`, en smart
   object, puis **calque masqué** par la sélection avec un feather de 10 px.
6. **Generate More** réutilise le même crop/masque pour itérer sans re-sélectionner.

Les leçons à garder : sélection = masque, crop avec contexte, résultat non destructif
(nouveau calque), masque de fusion, itération rapide. Les leçons à jeter : le bricolage
des calques temporaires, le resize DPI, les canaux cachés, le code distant, A1111.

## 2. PhotoCraft : architecture et point d'intégration

PhotoCraft est un éditeur natif **Rust + egui/eframe + wgpu**, sans Electron ni webview.

- **Tout est commande** : le registre `crates/engine/src/commands.rs` expose plus de
  500 commandes ; l'UI, le CLI, le control channel et le MCP passent par elles.
- **UI mince** : les panneaux sont dans `crates/ui-egui/src/panels.rs` et
  `crates/ui-egui/src/dock.rs` ; le docking custom est dans `panel_docking.rs`.
- **Modèle de document** : `photocraft-doc`, surfaces COW, calques, masques,
  calques de réglage, objets intelligents, PSD/PSB, 8/16/32 bits, RGB/Gray/CMYK/Lab.
- **Composition** : `photocraft-compose::render(&doc, rect)` et
  `photocraft_io::export(&doc, "png", ...)` ; la sélection est `doc.selection: Option<Surface>`
  (grayscale, 0..1).
- **Jobs** : `jobs::run` / `jobs::edit_job` pour les traitements longs, avec progression
  et annulation.
- **Plugins** : WebAssembly sandboxé, **sans réseau, sans UI**, uniquement des filtres
  pixels (ABI v1). Inadapté à un panneau IA.
- **Intégrations** : la section de préférences `integrations` existe déjà
  (`allowAgentControl`, `controlPort`) et le menu `Edit > Preferences > AI Integrations…`
  est déjà câblé. La crate `ml` est réservée mais non démarrée.
- **Gap officiel** : `docs/gaps.md` G15 liste « Generative Fill and Expand, Neural
  Filters, ML Select Subject/Sky… There is no ML runtime. » Un panneau IA natif est
  donc aligné avec la roadmap du projet.

### Deux voies d'intégration

| | Fork natif (écarté) | Compagnon + installateur (retenu) |
|---|---|---|
| UI | Panneau docké dans PhotoCraft | Fenêtre séparée, alignable |
| Accès composite/sélection | Direct, en mémoire | Via `app.save` + `channel.duplicate` + fichiers temporaires |
| Calques/masques | Direct, une étape d'undo | Via commandes `layer.copyToDocument` / `layerMask` |
| Déploiement | Un seul exe, build Rust | PhotoCraft + app + control channel |
| Maintenance | Rebase upstream à chaque release | Aucune modification de PhotoCraft |
| UX | Vraie intégration | Correcte mais moins « magique » |

Le control channel n'expose **pas** de méthode pour récupérer le composite ou le masque
en mémoire. Le compagnon sauvegarde donc des PNG temporaires et ouvre des documents
jetables. C'est le prix de l'absence de fork ; il est acceptable pour le MVP, et une
petite commande upstream (`document.renderPreview`) pourrait l'éliminer plus tard.

## 3. ComfyUI : le bon backend

ComfyUI expose une API HTTP simple et stable :

- `GET /system_stats` : version, GPU, VRAM libre ;
- `POST /upload/image` : upload multipart dans `input/` ;
- `POST /prompt` : file un workflow au format API (JSON de nœuds) ;
- `GET /history/{prompt_id}` : statut, erreurs, sorties ;
- `GET /view?filename=…` : récupère le PNG ;
- `POST /interrupt`, `GET/POST /queue` : annulation.

L'installation locale (port **12452**) contient déjà :

- `ComfyUI-GGUF` (Unet/CLIP GGUF) ;
- `comfyui-krea2edit` (édition Krea 2 par LoRA) ;
- `comfyui-inpaint-cropandstitch`, `comfyui_layerstyle`, `comfyui-sam3`, `comfyui-rmbg` ;
- les modèles FLUX.2/3 Klein et Krea 2, les text encoders et les VAE.

### Matrice des modèles

| Profil | Fichiers | VRAM approximative | Réglages validés |
|---|---|---|---|
| FLUX.3 Klein Edit | Unet Q8 5,7 Go + Qwen3-VL-4B FP8 5,6 Go + VAE 0,3 Go | ~11 Go (offload ComfyUI) | 16 steps, CFG 1, euler/simple |
| FLUX.2 Klein 9B Edit | Unet Q8 9,3 Go + Qwen3-8B Q4 4,7 Go + VAE 0,3 Go | ~14 Go (offload) | 6 steps, CFG 1, euler/simple |
| Krea 2 Turbo | Unet Q4 6,7 Go + Qwen3-VL-4B FP8 + VAE Qwen | ~12 Go | 8 steps, CFG 1 |
| Krea 2 Edit | `krea2_turbo_edit-Q4_K_M.gguf` + `Krea2EditModelPatch` + `Krea2EditGroundedEncode` | ~12 Go | 8 steps, CFG 1 (Raw/CFG 3 pour les suppressions) |

**Piège identifié** : `CLIPLoaderGGUF` avec `Qwen3VL-4B-Instruct-Q4_K_M.gguf` et
`type=flux3` échoue (`mat1 and mat2 shapes cannot be multiplied`). Il faut le
safetensors `Qwen-3-VL-4B-Scaled-FP8-v2.safetensors` avec `CLIPLoader` (type `flux3`).
C'est le seul couple validé pour FLUX.3 sur cette machine.

### Workflow FLUX.3 Klein validé

Nœuds API :

```
UnetLoaderGGUF(flux-3-image-klein-Q8_0.gguf)
CLIPLoader(Qwen-3-VL-4B-Scaled-FP8-v2.safetensors, flux3)
VAELoader(flux2_vae.safetensors)
CLIPTextEncode(positive) / CLIPTextEncode(negative="")
LoadImage(crop)
ReferenceMultiLatent(positive, negative, vae, images.image0,
                     resolution="resize", resolution.megapixels=1.0)
KSampler(model, seed, steps=16, cfg=1, euler/simple,
         positive, negative, latent_image, denoise=1)
VAEDecode → SaveImage
```

Détail API important : la combo dynamique s'écrit `resolution="resize"` **et**
`resolution.megapixels=1.0` (pas un objet imbriqué). L'image de référence s'écrit
`images.image0` (autogrow).

### Workflow FLUX.2 Klein validé

```
UnetLoaderGGUF(flux-2-klein-Distilled-9b-Q8_0.gguf)
CLIPLoaderGGUF(Qwen3-8B-Q4_K_M.gguf, flux2)
VAELoader(flux2_vae.safetensors)
LoadImage → ImageScaleToTotalPixels(1 MP) → VAEEncode
CLIPTextEncode(positive) → ReferenceLatent(latent)
ConditioningZeroOut(positive) → ReferenceLatent(latent)
KSampler(steps=6, cfg=1, euler/simple)
VAEDecode → SaveImage
```

FLUX.2 9B donne plus de matière et de détails, mais il a tendance à réinterpréter la
silhouette quand le crop est petit. Pour du lasso, FLUX.3 est plus fidèle. On peut
proposer les deux profils et laisser l'utilisateur choisir.

## 4. Pipeline StableCraft

```
Sélection PhotoCraft (Surface grayscale)
        │
        ├─ bbox + padding de contexte (ex. 96 px ou 25 %)
        ├─ clamp au canvas, alignement 16 px
        ├─ crop du composite (ou du calque actif)
        └─ masque crop + feather
                │
        upload PNG + prompt ──► ComfyUI /prompt
                │
        poll /history ──► PNG résultat
                │
        resize au crop ──► recomposition via masque
                │
        nouveau calque raster + masque de calque
        (une seule étape d'undo)
```

Modes :

- **Edit (lasso)** : crop + contexte, édition instructionnelle, recomposition masquée.
- **Generate** : bbox de la sélection (ou canvas), txt2img, placement dans la sélection.
- **Inpaint** : si un modèle le supporte, envoi image + masque ; sinon crop+composite.
- **Outpaint** : extension du canvas, bordure générée, fusion (phase ultérieure).
- **Batch** : plusieurs seeds, vignettes, clic pour appliquer/remplacer.

## 5. Architecture native proposée

### Crate `photocraft-comfy` (L4, natif uniquement)

- Client HTTP minimal (loopback HTTP, pas de TLS nécessaire) : `ureq` ou client
  `std::net::TcpStream` sur le modèle de `photocraft-ipp`.
- Types : `ComfyConfig`, `ComfyStatus`, `ModelProfile`, `GenerationRequest`,
  `GenerationResult`.
- Constructeurs de workflows : `flux3_klein_edit`, `flux2_klein_edit`, `krea2_edit`,
  `txt2img`, `inpaint`.
- Upload multipart, polling, download, annulation.
- Tests unitaires sur le JSON généré ; test d'intégration derrière un flag
  (`COMFYUI_TEST_ENDPOINT`).

### Commandes moteur (`crates/engine/src/ai_cmds.rs`)

| Commande | Rôle |
|---|---|
| `ai.comfy.status` | endpoint, version, GPU, modèles disponibles |
| `ai.comfy.models` | listes Unet/CLIP/VAE filtrables |
| `ai.edit` | snapshot doc + sélection, crop, job ComfyUI, application couche + masque |
| `ai.generate` | txt2img dans la sélection |
| `ai.cancel` | `/interrupt` + suppression de la file |
| `ai.applyResult` | applique une variante (batch) |

Le travail réseau se fait dans `jobs::run` (thread de fond) ; l'application du résultat
se fait sur le thread UI dans `jobs::run`'s `apply`, en une étape `Session::edit`.

### Panneau (`crates/ui-egui/src/stablecraft.rs`)

- Groupe de dock dédié (« StableCraft ») ou onglet dans le groupe History.
- Prompt / negative prompt, profil de modèle, mode, padding, steps, CFG, seed, batch.
- Bouton Générer / Annuler, barre de progression, temps écoulé.
- Vignettes des variantes, boutons Appliquer / Nouveau calque / Remplacer.
- Indicateur de connexion ComfyUI et lien vers les préférences.
- État sérialisé dans `UiState` (persistant), pas dans le document.

### Préférences

Étendre `Integrations` dans `crates/engine/src/prefs.rs` :

- `comfyEndpoint` (défaut `http://127.0.0.1:12452`) ;
- `comfyProfile` (`flux3Klein`, `flux2Klein`, `krea2`) ;
- `comfyAllowRemote` (faux par défaut : loopback seulement) ;
- `comfyContextPadding`, `comfyFeather`, `comfyOutputMode`.

## 6. Risques et points durs

1. **Churn upstream** : PhotoCraft est en alpha et bouge vite (v0.14.0 le 23/10/2026).
   Garder les modifications chirurgicales et rebaser souvent.
2. **Encodage texte** : les GGUF de text encoder ne sont pas interchangeables ; valider
   chaque couple modèle/encodeur via `/object_info` et un test réel.
3. **VRAM** : 12 Go est la limite basse pour FLUX.3 Q8 + encodeur FP8. Prévoir un mode
   « low VRAM » (Flux.2 4B, Krea 2 Q4, offload).
4. **Couleur** : les documents PhotoCraft peuvent être CMYK/Lab/16/32 bits. Le PNG envoyé
   à ComfyUI doit être converti en sRGB 8 bits ; le retour doit être reconverti dans le
   profil du document. Utiliser `photocraft_io::export` pour le composite.
5. **Géométrie** : le crop doit être aligné sur 16 px et le résultat redimensionné
   exactement au crop avant recomposition. Sinon, décalage d'un pixel visible.
6. **Masque** : le feather doit être appliqué côté PhotoCraft, pas seulement dans le
   modèle. Le masque de calque reste éditable.
7. **Licences** : ne pas redistribuer les poids ; afficher la licence du modèle et la
   source. ComfyUI est appelé par HTTP (pas de linking).
8. **Sécurité** : endpoint loopback par défaut ; ne pas accepter une URL distante sans
   opt-in explicite ; pas de télémétrie.
9. **Qualité** : les modèles d'édition instructionnelle peuvent changer des éléments
   hors sélection ; la recomposition masquée protège l'extérieur, mais l'intérieur peut
   dériver. Prévoir « garder le reste inchangé » dans le prompt et un bouton « Affiner ».

## 7. Décision retenue : compagnon + installateur, pas de fork

Le fork est écarté : PhotoCraft bouge vite, et maintenir un fork serait plus coûteux
que de s'appuyer sur son API d'automatisation.

StableCraft sera une **application compagne installable** :

- elle détecte une installation PhotoCraft existante ;
- elle se connecte à son **control channel** local (token, loopback) ;
- elle lit la sélection et le composite via `document.inspect`, `app.save` et
  `channel.duplicate` ;
- elle insère le résultat via `layer.copyToDocument` et, si possible, un masque de
  calque (`layer.layerMask.revealSelection`) ;
- elle parle à ComfyUI en HTTP ;
- elle vérifie la compatibilité **par capacités** (`engine.commands`) et non par un
  simple numéro de version.

PhotoCraft n'est pas modifié et se met à jour normalement. La contrepartie est une
fenêtre séparée et des allers-retours PNG temporaires, acceptables pour le MVP.

Voir [`ARCHITECTURE.md`](ARCHITECTURE.md) pour le détail.

## 8. Phasage

**Phase 0 — fait**
- Recherche des deux repos.
- Validation ComfyUI + FLUX.3 + FLUX.2 + Krea 2 Edit.
- PoC lasso/crop/masque.
- Recherche modèles, variantes « Edit », réglages, encodeurs, VRAM.

**Phase 1 — MVP compagnon**
- Installateur Windows + config TOML.
- Connexion PhotoCraft control channel + ComfyUI.
- Un seul profil : FLUX.3 Klein Edit.
- Lasso → prompt → preview → nouveau calque masqué.
- Détection des modèles, message si manquant, aucun téléchargement automatique.
- Tests de bout en bout sur PhotoCraft 0.14.0.

**Phase 2 — confort**
- FLUX.2 Klein, choix du profil.
- Batch de variantes + vignettes.
- Mode Generate (txt2img) et « Generate More ».
- Historique des prompts, seeds, presets.
- Model manager avec téléchargements consentis.

**Phase 3 — puissance**
- Krea 2 Edit (nœuds `krea2edit`), si le profil est stable.
- Outpaint, upscale, remove/relight.
- Workflows ComfyUI personnalisés (JSON API + placeholders).
- Panneau natif upstream (PR), si le projet prend.

## 9. MVP, c'est quoi ?

**MVP = Minimum Viable Product** : la plus petite version qui rend le service principal,
pas la version finale. Ici : un installateur, une connexion PhotoCraft/ComfyUI, un
profil FLUX.3, le lasso → prompt → nouveau calque, et des erreurs lisibles. Le reste
(FLUX.2, Krea 2, batch, outpaint, model manager complet) vient après.

## 10. Ce qui a été validé sur PhotoCraft 0.14.0

Testé le 23/10/2026 avec PhotoCraft portable 0.14.0 et ComfyUI 0.42.1 :

- ✅ `select.lasso` + `document.inspect` : bounds corrects.
- ✅ `app.save` du composite en PNG.
- ✅ `select.saveSelection` (création puis remplacement du canal « StableCraft Mask »).
- ✅ `channel.duplicate` du canal vers un document grayscale, `app.save` du masque,
  `file.close` du document temporaire.
- ✅ `layer.copyToDocument` : copie du résultat à `offset [x0, y0]`, bon calque,
  bonnes bounds, sélection préservée.
- ✅ `layer.layerMask.revealSelection` : masque de calque créé depuis le lasso.
- ✅ `layer.layerMask.edit {"feather": 10}` : adoucissement non destructif.
- ✅ `select.loadSelection` : sélection restaurée après application.
- ✅ `app.open` d'un PNG dans un sous-dossier du write root.
- ✅ Capture UI : calque « StableCraft — … », masque, densité 100 %, feather 10 px.

Fichiers : `docs/demo/photocraft-bridge.png`, `docs/demo/photocraft-flux3-blue.png`,
`prototypes/bridge_cli.py`.

### Pièges découverts

- PhotoCraft peut fermer une connexion de contrôle restée inactive pendant le sampling
  ComfyUI (~30 s). Le bridge se reconnecte avant la phase d'application.
- `app.save` d'un PNG aplati avertit que les calques/masques ne sont pas conservés :
  c'est normal, le document PhotoCraft garde ses calques ; seul le PNG exporté est aplati.
- Un `app.open` lancé pendant que le fichier est encore en cours d'écriture renvoie
  « unrecognized image format ». Toujours attendre la fin de l'écriture.

### Ce qui reste à valider

- La conversion couleur des documents CMYK/Lab/16/32 bits.
- Le temps de `app.save` sur un document 4K/8K.
- La compatibilité des commandes sur les builds PhotoCraft suivants.
- Le comportement sur macOS/Linux (le control channel est cross-platform, le launcher
  et l'installateur sont à adapter).
- Les profils FLUX.2/Krea 2 dans le bridge (les workflows sont validés séparément).
