# Modèles, réglages et VRAM — recherche du 23/10/2026

> Aucun modèle n'a été téléchargé. Tous les tests ci-dessous utilisent uniquement les
> fichiers déjà présents sur la machine. Les tailles sont celles des fichiers locaux.

## 1. Ce que veut dire « modèle Edit »

C'est le point le plus important, et il y a beaucoup de confusion dans les noms.

### FLUX.2 Klein et FLUX.3 Klein : pas de checkpoint « Edit » séparé

FLUX.2 Klein et FLUX.3 Klein sont des modèles **unifiés** : le même checkpoint fait la
génération texte→image **et** l'édition d'image. Les workflows « Edit » sont des graphes
différents, pas des modèles différents.

Il existe en revanche plusieurs **variantes** :

| Variante | Rôle | Réglages |
|---|---|---|
| **Distilled** | rapide, 4 étapes (FLUX.2) / 16 étapes (FLUX.3), CFG 1 | usage interactif |
| **Base** | non distillé, 50 étapes, CFG plus élevé | qualité maximale, fine-tuning |
| **KV** (FLUX.2 9B) | cache KV des références, jusqu'à ~2,5× plus rapide en multi-référence | même qualité, plus rapide |

Donc « FLUX.2 Klein Edit » dans un nom de fichier ou de workflow veut généralement dire
« workflow d'édition avec le modèle Klein », pas un poids différent. Ton
`flux-2-klein-Distilled-9b-Q8_0.gguf` est bien le bon modèle pour éditer.

### Krea 2 : l'édition est un LoRA, pas le modèle de base

Krea 2 est un modèle **texte→image**. L'édition vient de LoRA communautaires :

- `krea2_identity_edit_v1_2.safetensors` : restage/identité (tu l'as) ;
- `krea2_general_edit_v2.safetensors` : édition par instruction (pas présent en local) ;
- `krea2_turbo_edit-Q4_K_M.gguf` : modèle fusionné qui embarque probablement un LoRA
  d'édition (c'est celui qui fonctionne chez toi).

Les LoRA d'édition Krea 2 nécessitent les nœuds `comfyui-krea2edit`
(`Krea2EditModelPatch`, `Krea2EditGroundedEncode`), pas les nœuds standards.

### Qwen-Image-Edit : un vrai modèle d'édition dédié

Qwen-Image-Edit 2509 est un modèle **20B** spécialisé édition, avec un encodeur
Qwen2.5-VL-7B. C'est un vrai « Edit model », mais :

- Q4_K_M ≈ 12–13 Go pour le diffusion seul ;
- l'encodeur 7B ajoute ~4–7 Go ;
- il faut ComfyUI nightly pour les nœuds 2509 ;
- tu n'as pas les poids en local.

Ce n'est donc pas un candidat pour le MVP sur 12 Go, malgré sa qualité.

### FLUX.1 Kontext / Fill

Ce sont les anciens modèles d'édition/inpainting de FLUX.1. Tu as des métadonnées mais
pas les poids. Ils sont plus lourds et moins bons que FLUX.2/3 Klein. À ignorer.

## 2. Inventaire local utile

### Modèles de diffusion

| Fichier | Taille | Architecture GGUF | État |
|---|---:|---|---|
| `flux-3-image-klein-Q8_0.gguf` | 5,67 Go | `flux` | ✅ testé, édition |
| `flux-2-klein-Distilled-9b-Q8_0.gguf` | 9,29 Go | `flux` | ✅ testé, édition |
| `krea2_turbo_edit-Q4_K_M.gguf` | 6,76 Go | `qwen_image` (fusionné) | ✅ testé, édition |
| `Krea-2-Turbo-Q4_K_M.gguf` | 6,72 Go | `krea2` | ❌ `UnetLoaderGGUF` refuse l'architecture `krea2` |
| `flux1-dev-Q8_0.gguf` | 11,84 Go | `flux` | T2I seulement, pas d'édition |
| `zImage_turbo_bf16.safetensors` | 11,46 Go | — | T2I, pas d'édition |

### Encodeurs texte

| Fichier | Taille | Usage |
|---|---:|---|
| `Qwen-3-VL-4B-Scaled-FP8-v2.safetensors` | 5,61 Go | ✅ FLUX.3 (`flux3`) et Krea 2 (`krea2`) |
| `Qwen3-8B-Q4_K_M.gguf` | 4,68 Go | ✅ FLUX.2 9B (`flux2`) |
| `Qwen3-8B-Q8_0.gguf` | 8,11 Go | FLUX.2 9B, plus lourd |
| `qwen_3_4b.safetensors` | 7,49 Go | FLUX.2 4B (mais pas le modèle 4B en local) |
| `Qwen3VL-4B-Instruct-Q4_K_M.gguf` | 2,33 Go | ❌ FLUX.3 (dimension) et Krea 2 (features 12×2560) |
| `Qwen2.5-VL-7B-Instruct-Q4_0.gguf` + mmproj | 5,4 Go | Qwen-Image-Edit (pas de modèle local) |
| `t5xxl_fp8_e4m3fn.safetensors` | 4,56 Go | anciens FLUX.1 |

### VAE

| Fichier | Taille | Usage |
|---|---:|---|
| `flux2_vae.safetensors` | 0,31 Go | FLUX.2 et FLUX.3 |
| `qwen_image_vae.safetensors` | 0,24 Go | Krea 2, Qwen-Image |
| `ae.safetensors` / `ae.sft` | 0,31 Go | FLUX.1 |

### LoRA utiles

| Fichier | Taille | Usage |
|---|---:|---|
| `krea2_identity_edit_v1_2.safetensors` | 1,70 Go | Krea 2 identité (nécessite krea2edit) |
| `klein_snofs_v1_2.safetensors` | 1,02 Go | style FLUX.2 Klein |
| `realism_engine_krea2_v3.1.safetensors` | 1,46 Go | style Krea 2 |
| `snofs_krea_v1_1.safetensors` | 1,46 Go | style Krea 2 |

## 3. Matrice des profils

### FLUX.3 Klein Edit — recommandé pour le lasso

| | |
|---|---|
| Diffusion | `flux-3-image-klein-Q8_0.gguf` (5,67 Go) |
| Text encoder | `Qwen-3-VL-4B-Scaled-FP8-v2.safetensors`, `CLIPLoader` type `flux3` |
| VAE | `flux2_vae.safetensors` |
| Poids totaux | ~11,6 Go |
| Steps / CFG | **16 / 1.0** (distilled) |
| Sampler | euler / simple |
| Résolution | ~1 MP (reference resize) |
| VRAM | 12 Go OK avec offload ; 8 Go avec INT8/NVFP4 |
| Licence | FLUX Kommunity License (commercial gratuit < 5 M$ de revenu) |
| Test local | ✅ ~34 s pour 1024², 16 steps |

**Pourquoi c'est le meilleur choix MVP** : le plus petit des profils haute qualité
locaux, le plus fidèle pour garder le reste de l'image, pas de nœud custom au-delà de
ComfyUI-GGUF, et un encodeur texte qui fonctionne réellement.

**Pour les utilisateurs 8–10 Go** : le même modèle en INT8/Q4 (non présent en local)
descend à ~8–10 Go avec l'encodeur FP8. Pour un profil vraiment basse VRAM, FLUX.2
Klein 4B est plus adapté.

### FLUX.2 Klein 9B Edit — qualité maximale, plus lourd

| | |
|---|---|
| Diffusion | `flux-2-klein-Distilled-9b-Q8_0.gguf` (9,29 Go) |
| Text encoder | `Qwen3-8B-Q4_K_M.gguf`, `CLIPLoaderGGUF` type `flux2` |
| VAE | `flux2_vae.safetensors` |
| Poids totaux | ~14,3 Go |
| Steps / CFG | **4 / 1.0** (distilled ; 6–8 possible) |
| Sampler | euler / simple |
| VRAM | 12 Go avec offload ; Q4_K_M + Qwen3-8B Q4 ≈ 10,5 Go pour un vrai 12 Go |
| Licence | 9B non-commercial ; 4B Apache 2.0 |
| Test local | ✅ ~60 s pour 1024², 6 steps |

**Constat de test** : plus de texture et de détail que FLUX.3, mais il a tendance à
réinterpréter la silhouette et le cadrage quand le crop est petit. Pour du lasso, il
faut un contexte plus large et un prompt qui décrit précisément ce qui doit rester.
C'est le profil « qualité » à proposer, pas le défaut.

**Base vs Distilled** : le Base (50 steps, CFG 1 en édition) est plus fidèle mais
beaucoup trop lent pour l'interaction. Le Distilled est le bon choix.

**KV** : `FLUX.2-klein-9b-kv` est une variante avec cache KV, jusqu'à 2,5× plus rapide
en multi-référence. Tu ne l'as pas. À proposer plus tard pour les utilisateurs qui
travaillent avec plusieurs références.

### Krea 2 Edit — identité et style, mais plus contraignant

| | |
|---|---|
| Diffusion | `krea2_turbo_edit-Q4_K_M.gguf` (6,76 Go) |
| Text encoder | `Qwen-3-VL-4B-Scaled-FP8-v2.safetensors`, `CLIPLoader` type `krea2` |
| VAE | `qwen_image_vae.safetensors` |
| Poids totaux | ~12,6 Go |
| Steps / CFG | **8 / 1.0** (Turbo) |
| Nœuds | `Krea2EditModelPatch`, `Krea2EditGroundedEncode` |
| `ref_boost` | 2 pour l'identité, 4 pour l'édition générale |
| `grounding_px` | 768 (défaut) |
| Licence | Krea 2 Community License (vérifier les conditions commerciales) |
| Test local | ✅ édition robe verte, 8 steps, ~? s |

**Constat de test** : très bon rendu, mais la robe a changé de silhouette (bretelles,
jupe évasée) alors que le fond et le personnage étaient préservés. C'est un modèle
d'édition instructionnelle : il ne se contente pas de recolorer, il réinterprète.
Pour un lasso, la recomposition masquée limite l'impact à l'intérieur de la sélection.

**Limites locales** :
- `Krea-2-Turbo-Q4_K_M.gguf` (arch `krea2`) n'est **pas** chargeable par
  `UnetLoaderGGUF` dans cette version de ComfyUI-GGUF. Le modèle fusionné
  `krea2_turbo_edit` (arch `qwen_image`) fonctionne, lui.
- L'encodeur GGUF `Qwen3VL-4B-Instruct-Q4_K_M.gguf` ne fonctionne **pas** pour Krea 2 :
  il manque les 12 couches de features (12×2560=30720). Il faut le FP8 safetensors.
- Pas de Krea 2 Raw local, donc les suppressions d'objets (Raw, 20 steps, CFG 3) ne
  sont pas testables.
- Le cache KV de Krea 3 / les nœuds `Krea3ImageNode` sont des modèles **API/partner**,
  pas des poids locaux.

### Krea 2 Turbo T2I — pas exploitable en local avec les GGUF actuels

Le modèle `Krea-2-Turbo-Q4_K_M.gguf` a l'architecture GGUF `krea2`, que
`UnetLoaderGGUF` refuse (`Unexpected architecture type in GGUF file: 'krea2'`). Il
faudrait :
- un loader Krea 2 GGUF dédié (nœud TJ ou mise à jour de ComfyUI-GGUF) ;
- ou le safetensors Krea 2 Turbo.
Tu n'as ni l'un ni l'autre en local. Le mode T2I Krea 2 n'est donc pas dans le MVP.

### Qwen-Image-Edit 2509 — à écarter pour l'instant

| | |
|---|---|
| Diffusion | 20B, Q4_K_M ≈ 12–13 Go |
| Text encoder | Qwen2.5-VL-7B (~4–7 Go) |
| VAE | `qwen_image_vae.safetensors` |
| Steps / CFG | 50 / 4.0 (base) ; 20 / 2.5 (FP8) ; 8 / 1.0 avec Lightning LoRA |
| VRAM | 12 Go borderline, 16 Go conseillé |
| Licence | Apache 2.0 |
| Local | ❌ poids absents |

C'est un vrai modèle d'édition dédié, mais trop lourd pour 12 Go et absent du disque.
À réévaluer plus tard, quand tu auras les poids ou une version plus petite.

## 4. Encodeurs texte : ce qui marche vraiment

C'est le point qui casse le plus souvent.

| Modèle | Encodeur attendu | Loader | GGUF possible ? |
|---|---|---|---|
| FLUX.2 Klein 9B | Qwen3-8B | `CLIPLoaderGGUF` type `flux2` | ✅ `Qwen3-8B-Q4_K_M.gguf` |
| FLUX.2 Klein 4B | Qwen3-4B | `CLIPLoaderGGUF` type `flux2` | ✅ `qwen_3_4b` / Qwen3-4B GGUF (à tester) |
| FLUX.3 Klein | Qwen3-VL-4B | `CLIPLoader` type `flux3` | ❌ le GGUF Q4 échoue (`mat1 and mat2`) |
| Krea 2 | Qwen3-VL-4B (12 couches) | `CLIPLoader` type `krea2` | ❌ le GGUF Q4 échoue (12×2560) |
| Qwen-Image-Edit | Qwen2.5-VL-7B | `CLIPLoader` type `qwen_image` | ✅ avec mmproj |

**Règle** : ne pas supposer qu'un GGUF de text encoder est compatible. Tester le
couple réel. Pour FLUX.3 et Krea 2, le FP8 safetensors `Qwen-3-VL-4B-Scaled-FP8-v2`
est le seul validé sur cette machine.

## 5. Réglages recommandés (officiels + testés)

| Profil | Steps | CFG | Sampler | Remarque |
|---|---:|---:|---|---|
| FLUX.3 Klein Distilled | 16 | 1.0 | euler / simple | 4–16 selon la qualité ; 16 par défaut |
| FLUX.3 Klein Base | 50 | 3.5 (T2I) / 1.0 (edit) | euler / simple | trop lent pour l'interaction |
| FLUX.2 Klein 9B Distilled | 4 | 1.0 | euler / simple | 6–8 possible, gain décroissant |
| FLUX.2 Klein 9B Base | 50 | 4.0 (T2I) / 1.0 (edit) | euler / simple | qualité max, lent |
| FLUX.2 Klein 4B Distilled | 4 | 1.0 | euler / simple | ~8,4 Go VRAM |
| Krea 2 Turbo | 8 | 1.0 | euler / simple | 8–12 pour les visages |
| Krea 2 Turbo Edit (identité) | 8 | 1.0 | euler / simple | `ref_boost` 2, `grounding_px` 768 |
| Krea 2 Turbo Edit (général) | 8 | 1.0 | euler / simple | `ref_boost` 4 |
| Krea 2 Raw (suppressions) | 20 | 3.0 | euler / simple | nécessite le modèle Raw |
| Qwen-Image-Edit 2509 | 8 (Lightning) | 1.0 | euler / simple | 20/2.5 sans LoRA |

**Ne pas monter le CFG sur les modèles distillés** : FLUX.2/3 Klein distillés sont
entraînés à CFG 1 ; au-dessus, la qualité casse. Krea 2 Turbo aussi.

## 6. Budget VRAM / disque

| Profil | Poids | VRAM pratique | Disque | Local |
|---|---:|---:|---:|---|
| FLUX.3 Q8 + Qwen3VL FP8 | 11,6 Go | 12 Go (offload) | 11,6 Go | ✅ |
| FLUX.2 9B Q8 + Qwen3-8B Q4 | 14,3 Go | 12 Go (offload) | 14,3 Go | ✅ |
| FLUX.2 9B Q4 + Qwen3-8B Q4 | ~10,5 Go | 10–12 Go | ~10,5 Go | ❌ (à télécharger) |
| FLUX.2 4B Q4 + Qwen3-4B Q4 | ~5,3 Go | 6–8 Go | ~5,3 Go | ❌ (à télécharger) |
| FLUX.2 4B Q8 + qwen_3_4b | ~12,1 Go | 12 Go | ~12,1 Go | partiel (encodeur seulement) |
| Krea 2 Edit Q4 + Qwen3VL FP8 | 12,6 Go | 12 Go (offload) | 12,6 Go | ✅ |
| Krea 2 Edit + encodeur Q4 (si supporté) | ~9,3 Go | 10 Go | ~9,3 Go | ❌ (GGUF non supporté) |
| Qwen-Image-Edit 2509 Q4 + Qwen2.5-VL Q4 | ~17 Go | 16 Go+ | ~17 Go | ❌ |

**Recommandation publique** :
- 8 Go VRAM : FLUX.2 Klein 4B Q4 + encodeur Q4.
- 12 Go VRAM : FLUX.2 Klein 9B Q4 + Qwen3-8B Q4, ou FLUX.3 Q8 + Qwen3VL FP8.
- 16–24 Go VRAM : FLUX.2 9B Q8, FLUX.3 Q8, Krea 2.
- Pour le lasso : FLUX.3 Klein est le meilleur compromis fidélité/VRAM.

## 7. Profils branchés dans l'application

Trois profils sont implémentés dans le bridge et sélectionnables dans l'UI :

| Profil | Modèle | Encodeur | VAE | Steps / CFG | État |
|---|---|---|---|---:|---|
| **FLUX.3 Klein Edit** (défaut) | `flux-3-image-klein-Q8_0.gguf` | Qwen3-VL-4B FP8 (`flux3`) | `flux2_vae` | 16 / 1.0 | ✅ testé |
| FLUX.2 Klein 9B Edit | `flux-2-klein-Distilled-9b-Q8_0.gguf` | Qwen3-8B Q4 (`flux2`) | `flux2_vae` | 4 / 1.0 | ✅ testé |
| Krea 2 Edit | `krea2_turbo_edit-Q4_K_M.gguf` | Qwen3-VL-4B FP8 (`krea2`) | `qwen_image_vae` | 8 / 1.0 | ✅ testé |

L'UI vérifie les fichiers et les nœuds custom avant d'activer le bouton Générer :

- FLUX.3 : `UnetLoaderGGUF`, `CLIPLoader`, `VAELoader` ;
- FLUX.2 : `UnetLoaderGGUF`, `CLIPLoaderGGUF`, `VAELoader` ;
- Krea 2 : `UnetLoaderGGUF`, `CLIPLoader`, `VAELoader`, `Krea2EditModelPatch`,
  `Krea2EditGroundedEncode`, `EmptySD3LatentImage`.

### Non branchés

- **FLUX.2 Klein 4B** : pas de modèle local ; profil public à ajouter et à tester.
- **Qwen-Image-Edit 2509** : trop lourd, poids absents.
- **FLUX.1 Kontext / Fill** : poids absents, plus vieux.
- **Krea 2 Turbo T2I** : `Krea-2-Turbo-Q4_K_M.gguf` (arch `krea2`) ne charge pas avec
  `UnetLoaderGGUF` dans cette version. Le modèle fusionné `krea2_turbo_edit`
  (arch `qwen_image`) fonctionne pour l'édition.

Aucun profil ne télécharge de modèle automatiquement. Les fichiers manquants sont
signalés, avec leur taille, leur chemin et leur licence.

## 8. Sources principales

- ComfyUI Docs — FLUX.2 Klein 4B/9B, workflows et fichiers :
  https://docs.comfy.org/tutorials/flux/flux-2-klein
- ComfyUI Docs — FLUX.3 Klein, workflows et réglages :
  https://docs.comfy.org/tutorials/flux/flux-3-klein
- BFL — FLUX.2 Klein et FLUX.3 Klein (licences, variantes) :
  https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence
  https://bfl.ai/blog/flux-3-image-klein
- ComfyUI Docs — Krea 2 (Turbo/Raw, réglages) :
  https://docs.comfy.org/tutorials/image/krea/krea-2
- Krea 2 Identity Edit (LoRA, réglages, VRAM) :
  https://huggingface.co/conradlocke/krea2-identity-edit
- ComfyUI-Krea2Edit (nœuds, câblage) :
  https://github.com/lbouaraba/comfyui-krea2edit
- Qwen-Image-Edit 2509 (poids, étapes, VRAM) :
  https://docs.comfy.org/tutorials/image/qwen/qwen-image-edit
- ComfyUI-GGUF (limites de chargement, architectures) :
  https://github.com/city96/ComfyUI-GGUF
