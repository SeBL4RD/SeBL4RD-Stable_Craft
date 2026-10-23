# StableCraft

**Le geste de Stable.art, ressuscité dans PhotoCraft, avec ComfyUI comme moteur.**

On sélectionne une zone au lasso, on écrit ce qu'on veut changer, et le résultat arrive
dans un nouveau calque — sans toucher aux pixels d'origine. Le tout en local, sur sa GPU,
avec des modèles récents quantifiés en GGUF.

> Statut : **preuve de concept validée** (23/10/2026). L'intégration dans PhotoCraft
> reste à construire ; l'architecture est proposée dans [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Ce qui est déjà prouvé

Sur cette machine (RTX 3080 Ti 12 Go, 32 Go RAM, ComfyUI 0.42.1, port `12452`) :

| Test | Résultat |
|---|---|
| Édition globale avec **FLUX.3 Klein Q8** | ✅ robe bleue + fond coucher de soleil, personnage/pose conservés, ~34 s |
| **Lasso → crop avec contexte → édition → recomposition masquée** | ✅ robe verte, fond intact, contour fondu |
| **FLUX.2 Klein 9B Q8** sur le même crop | ✅ rendu plus texturé, mais recompose davantage la silhouette |
| Encodage texte | ⚠️ le GGUF `Qwen3VL-4B-Instruct-Q4_K_M` **ne marche pas** pour FLUX.3 ; il faut `Qwen-3-VL-4B-Scaled-FP8-v2.safetensors` |

Les images sont dans [`docs/demo/`](docs/demo) :

- `lasso-before.png` → `lasso-after-flux3.png`
- `comparison-original-flux3-flux2.png`
- `flux2-raw.png`

---

## Pourquoi ComfyUI ?

Parce que c'est le seul backend local qui :

- charge les modèles **GGUF quantifiés** (Unet + text encoder) avec `ComfyUI-GGUF` ;
- expose une API HTTP simple (`/prompt`, `/history`, `/view`, `/upload/image`) ;
- permet de changer de modèle/workflow sans recompiler l'éditeur ;
- gère FLUX.2 Klein, FLUX.3 Klein, Krea 2, les VAE et les encodeurs associés ;
- tourne déjà sur la machine, avec les modèles et les nœuds custom nécessaires.

Le plugin A1111 de Stable.art est mort ; ComfyUI est aujourd'hui le standard de fait
pour ce type de pipeline local.

---

## Pourquoi pas un « plugin » PhotoCraft classique ?

Le SDK de plugins de PhotoCraft (ABI v1) est un **filtre WebAssembly sandboxé** :

- aucun import hôte : pas de réseau, pas de fichiers, pas d'horloge ;
- uniquement des pixels en entrée/sortie ;
- pas de panneau UI, pas d'appel HTTP.

Donc un panneau IA + client ComfyUI **ne peut pas** être un plugin v1. Deux voies :

1. **Fork natif de PhotoCraft** avec un panneau docké et un crate `photocraft-comfy` — recommandé ;
2. **Compagnon externe** qui pilote PhotoCraft via le control channel — plus simple à prototyper,
   mais fenêtre séparée, allers-retours fichiers et UX moins intégrée.

---

## Modèles validés sur 12 Go de VRAM

| Profil | Diffusion | Text encoder | VAE | Réglages | Remarque |
|---|---|---|---|---|---|
| **FLUX.3 Klein** | `flux-3-image-klein-Q8_0.gguf` (5,7 Go) | `Qwen-3-VL-4B-Scaled-FP8-v2.safetensors` (5,6 Go), type `flux3` | `flux2_vae.safetensors` | 16 steps, CFG 1, euler/simple | meilleure fidélité locale, ~34 s |
| **FLUX.2 Klein 9B** | `flux-2-klein-Distilled-9b-Q8_0.gguf` (9,3 Go) | `Qwen3-8B-Q4_K_M.gguf` (4,7 Go), type `flux2` | `flux2_vae.safetensors` | 6 steps, CFG 1 | plus détaillé, recompose parfois |
| **Krea 2 Turbo** | `Krea-2-Turbo-Q4_K_M.gguf` (6,7 Go) | `Qwen-3-VL-4B-Scaled-FP8-v2.safetensors`, type `krea2` | `qwen_image_vae.safetensors` | 8 steps, CFG 1 | T2I esthétique ; édition via `comfyui-krea2edit` |

Les poids ne sont **pas** redistribués : chaque utilisateur installe ses fichiers dans ComfyUI.
Les licences des modèles (FLUX Kommunity, Krea Community, etc.) s'appliquent.

---

## Prototype CLI

Le script [`prototypes/stablecraft_proto.py`](prototypes/stablecraft_proto.py) reproduit
le flux complet :

1. simule un lasso autour de la robe ;
2. calcule la bbox, ajoute 96 px de contexte, aligne sur 16 px ;
3. uploade le crop dans ComfyUI ;
4. lance le workflow FLUX.3 Klein ;
5. récupère le PNG, le redimensionne au crop ;
6. le recompose dans l'image d'origine via le masque feathered ;
7. écrit `before.png`, `after.png`, `side_by_side.png`.

```powershell
F:\ComfyUI_windows_portable\python_embeded\python.exe prototypes\stablecraft_proto.py
```

Prérequis : ComfyUI lancé sur `http://127.0.0.1:12452` avec les modèles ci-dessus.

---

## Prochaines étapes

1. **Décider l'architecture** : fork natif (recommandé) ou compagnon.
2. **MVP FLUX.3 Klein** : panneau docké, lasso, prompt, contexte, nouveau calque + masque,
   progression, annulation.
3. **FLUX.2 + Krea 2**, variantes multiples, mode génération, outpainting.
4. **Workflows personnalisés** : charger un JSON API ComfyUI avec des placeholders.

Voir [`docs/BRIEF.md`](docs/BRIEF.md) pour l'analyse des deux repos et
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) pour le design technique.
