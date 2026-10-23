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

| | Fork natif (recommandé) | Compagnon externe |
|---|---|---|
| UI | Panneau docké dans PhotoCraft | Fenêtre séparée |
| Accès composite/sélection | Direct, en mémoire | Via `app.save` + `channel.duplicate` + fichiers temporaires |
| Calques/masques | Direct, une étape d'undo | Via commandes `layer.copyToDocument` / `layerMask` |
| Déploiement | Un seul exe, build Rust | PhotoCraft + app + control channel |
| Maintenance | Rebase upstream | Aucune modification de PhotoCraft |
| UX | Vraie intégration | Correcte mais moins « magique » |

Le control channel de PhotoCraft n'expose **pas** de méthode pour récupérer le composite
ou le masque en mémoire. Un compagnon doit donc sauvegarder des PNG temporaires et
ouvrir des documents jetables. C'est faisable, mais on perd l'avantage principal.

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

## 7. Phasage recommandé

**Phase 0 — fait**
- Recherche des deux repos.
- Validation ComfyUI + FLUX.3 + FLUX.2.
- PoC lasso/crop/masque.

**Phase 1 — MVP natif**
- Fork PhotoCraft + crate `photocraft-comfy` + panneau.
- Mode Edit lasso avec FLUX.3 Klein.
- Nouveau calque + masque, undo, progression, annulation.
- Préférences endpoint/profil.
- Tests : workflow JSON, géométrie crop, application couche.

**Phase 2 — confort**
- FLUX.2 Klein, choix du profil.
- Batch de variantes + vignettes.
- Mode Generate (txt2img) et « Generate More ».
- Historique des prompts, seeds, presets.

**Phase 3 — puissance**
- Krea 2 (T2I + edit via `krea2edit`).
- Outpaint, upscale, remove/relight.
- Workflows ComfyUI personnalisés (JSON API + placeholders).
- Gestionnaire de modèles / téléchargement assisté.

## 8. Décision à prendre

- **Fork natif** (recommandé) : meilleure UX, accès direct aux calques et à la sélection,
  un seul exécutable. Coût : installer Rust, builder ~10 Go, rebaser upstream.
- **Compagnon externe** : plus rapide à prototyper, mais fenêtre séparée et allers-retours
  fichiers. Utile si on veut livrer sans toucher à PhotoCraft.

Une fois la voie choisie, le MVP FLUX.3 est réalisable en s'appuyant sur le workflow
déjà validé et le prototype Python.
