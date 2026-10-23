# StableCraft

**Le geste de Stable.art, ressuscité pour PhotoCraft, avec ComfyUI comme moteur.**

On sélectionne une zone au lasso, on écrit ce qu'on veut changer, et le résultat arrive
dans un nouveau calque — sans toucher aux pixels d'origine. Le tout en local, sur sa GPU,
avec des modèles récents quantifiés en GGUF.

> **Statut** : preuve de concept validée le 23/10/2026. Le backend ComfyUI fonctionne.
> L'intégration PhotoCraft est conçue comme une **application compagne installable**,
> sans fork de PhotoCraft. Le pont control channel reste à tester de bout en bout.

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
| Encodage texte | ⚠️ les GGUF Qwen3-VL ne marchent **pas** pour FLUX.3 ni Krea 2 ; il faut le FP8 safetensors |

Images dans [`docs/demo/`](docs/demo) :

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

## Prototype backend

Le script [`prototypes/stablecraft_proto.py`](prototypes/stablecraft_proto.py) reproduit
le flux complet **sans PhotoCraft** (image de test, lasso synthétique) :

1. calcule la bbox, ajoute 96 px de contexte, aligne sur 16 px ;
2. uploade le crop dans ComfyUI ;
3. lance le workflow FLUX.3 Klein ;
4. récupère le PNG, le redimensionne au crop ;
5. le recompose dans l'image d'origine via le masque feathered ;
6. écrit `before.png`, `after.png`, `side_by_side.png`.

```powershell
F:\ComfyUI_windows_portable\python_embeded\python.exe prototypes\stablecraft_proto.py
```

Prérequis : ComfyUI sur `http://127.0.0.1:12452` avec les modèles FLUX.3.

Workflows API validés : [`workflows/`](workflows).

---

## Prochaines étapes

1. **Valider le control channel** sur PhotoCraft 0.14.0 (portable, 87 Mo) : sélection,
   `app.save`, `channel.duplicate`, `layer.copyToDocument`, masque.
2. **Prototype bridge Python** sans UI, testé de bout en bout.
3. **UI PySide6** + installateur Inno Setup.
4. **Model manager** : détection, profils, téléchargements avec consentement.
5. **MVP public**, puis FLUX.2/Krea 2/outpaint.

Voir [`docs/BRIEF.md`](docs/BRIEF.md) (recherche Stable.art/PhotoCraft) et
[`docs/MODELS.md`](docs/MODELS.md) (modèles et réglages).
