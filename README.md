# StableCraft

**L'édition par lasso de Stable.art, dans PhotoCraft, avec ComfyUI.**

StableCraft est une application compagne pour PhotoCraft : on entoure une zone au
lasso, on décrit le changement, et le résultat arrive dans un **nouveau calque masqué**.
Tout tourne en local, sur son propre GPU, avec ComfyUI comme moteur de génération.

![Statut](https://img.shields.io/badge/statut-MVP%20fonctionnel-22c55e)
![Plateforme](https://img.shields.io/badge/plateforme-Windows%20x64-3b82f6)
![Licence](https://img.shields.io/badge/licence-MIT-8b5cf6)

## Présentation

- lasso → prompt → édition → calque PhotoCraft ;
- calque avec **masque et feather** ;
- **galerie persistante par calque** : régénérer, comparer, changer de génération ;
- régénération possible même si la sélection a été perdue ;
- **image de référence par calque** (Krea 2 et FLUX.3 Klein) ;
- trois profils : FLUX.3 Klein, FLUX.2 Klein 9B, Krea 2 Edit ;
- aucun poids de modèle dans le dépôt ;
- aucun téléchargement silencieux.

## Fondement

StableCraft ne modifie pas PhotoCraft et n'est pas un fork.

PhotoCraft est piloté par son **control channel local** : lecture de la sélection,
sauvegarde du composite, insertion du calque, création du masque. ComfyUI est piloté en
HTTP. Les deux applications restent indépendantes et peuvent être mises à jour
séparément. La compatibilité est vérifiée par les commandes disponibles, pas par un
numéro de version figé.

## Dépendances

### Matériel

- Windows 10/11 **x64**.
- GPU **NVIDIA** seulement, pour le moment.
- **12 Go de VRAM** testés sur RTX 3080 Ti ; 32 Go de RAM.
- En dessous de 12 Go de VRAM, ce n'est pas validé aujourd'hui.

### Logiciel

- **PhotoCraft 0.14.0** ou supérieur (portable ou installé).
- **ComfyUI portable** (avec `python_embeded\python.exe`).
- **Python 3.11+**.
- Pour Krea 2 : le nœud custom
  [`comfyui-krea2edit`](https://github.com/lbouaraba/comfyui-krea2edit).
- `ComfyUI-GGUF` pour charger les modèles UNet GGUF.

### Modèles

Les poids ne sont **pas** fournis. Ils doivent être visibles par ComfyUI.

| Profil | UNet | Text encoder | VAE | Steps / CFG |
|---|---|---|---|---|
| **FLUX.3 Klein Edit** (défaut) | `flux-3-image-klein-Q8_0.gguf` | `Qwen-3-VL-4B-Scaled-FP8-v2.safetensors` | `flux2_vae.safetensors` | 16 / 1.0 |
| **FLUX.2 Klein 9B Edit** | `flux-2-klein-Distilled-9b-Q8_0.gguf` | `Qwen3-8B-Q4_K_M.gguf` | `flux2_vae.safetensors` | 4 / 1.0 |
| **Krea 2 Edit** | `krea2_turbo_edit-Q4_K_M.gguf` | `Qwen-3-VL-4B-Scaled-FP8-v2.safetensors` | `qwen_image_vae.safetensors` | 8 / 1.0 |

Notes :

- le GGUF `Qwen3VL-4B-Instruct-Q4_K_M.gguf` testé n'est pas compatible avec FLUX.3
  ni Krea 2 ; StableCraft utilise le FP8 safetensors ;
- `Qwen3-8B-Q4_K_M.gguf` fonctionne pour FLUX.2 ;
- les licences des modèles s'appliquent (FLUX Kommunity, Krea Community, etc.),
  séparément de la licence MIT du code.

## Installation

### Option 1 — installateur Windows

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1
```

L'installateur détecte PhotoCraft et ComfyUI, copie StableCraft dans
`%USERPROFILE%\StableCraft`, crée les dossiers `user\` et `models\`, et ajoute un
raccourci **StableCraft**. Aucun modèle n'est téléchargé.

### Option 2 — depuis le dépôt

```powershell
Copy-Item config.example.toml config.toml
.\StableCraft.bat
```

Le lanceur a besoin de `config.toml` ; le plus simple est de copier l'exemple. Les
chemins peuvent rester vides si l'auto-détection suffit. Les chemins importants :

```toml
[photocraft]
executable = "D:/.../photocraft.exe"

[comfyui]
root = "F:/ComfyUI_windows_portable"
python = "F:/ComfyUI_windows_portable/python_embeded/python.exe"
```

Au lancement, `StableCraft.bat` :

1. vérifie les chemins ;
2. démarre ComfyUI si nécessaire, **sans ouvrir le navigateur** ;
3. démarre PhotoCraft avec le control channel si nécessaire ;
4. nettoie les fichiers temporaires de « Ouvrir un fichier récent » ;
5. ouvre l'interface.

Si un chemin obligatoire manque, un message clair s'affiche. Les modèles manquants ne
bloquent pas : l'UI les signale et désactive la génération.

## Utilisation

1. Ouvre une image dans PhotoCraft.
2. Fais un **lasso** autour de la zone à modifier.
3. Dans StableCraft : choisis le profil, écris le prompt, clique **Générer**.
4. Le résultat est ajouté comme **calque StableCraft** avec un masque.
5. La galerie du calque apparaît sous le prompt.

### Régénérer et galerie

- Même sélection → **Régénérer** met à jour le **même calque** et ajoute une vignette.
- Chaque génération repart du `base.png` figé au moment du lasso, jamais du composite
  avec les générations précédentes.
- Clique sur une vignette pour appliquer cette génération, sans relancer ComfyUI.
- Sélection perdue → sélectionne le calque `StableCraft [id]`, puis **Régénérer**.
- Nouvelle sélection → nouvelle galerie et nouveau calque.

### Image de référence

- coche **Utiliser une image de référence** ;
- clique sur la vignette ou dépose une image ;
- la référence est propre au calque et se recharge quand tu reviens dessus ;
- compatible **Krea 2 Edit** et **FLUX.3 Klein** ;
- le modèle reçoit **image 1 = scène** et **image 2 = référence** ;
- décris dans le prompt ce que tu prends de l'image 2.

Exemple :

> Add the black leather glove from the reference image to the man's right hand.
> Keep the hand pose, arm, skin tone, lighting and background unchanged.

Le bouton **Guide** à côté de `PROMPT` ouvre une fenêtre non bloquante avec les bonnes
pratiques et des exemples.

### Aperçu

- **Document** : le composite PhotoCraft après application.
- **Crop** : le résultat généré à la taille du crop, avant masque.

## Stockage

Rien n'est stocké dans AppData.

```text
<dossier StableCraft>/
  user/
    control.token
    sessions/<id>/       # base, masque, référence, galerie
    logs/
  models/                # modèles locaux, aucun poids versionné
```

Les chemins sont configurables dans `config.toml` (`[app]`, `[photocraft]`,
`[comfyui]`, `[models]`).

## Crédits

- **Stable.art** — inspiration pour l'expérience lasso + prompt.
- **PhotoCraft** — application hôte et control channel :
  [storytold/photocraft](https://github.com/storytold/photocraft).
- **ComfyUI** — moteur de génération :
  [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI).
- **FLUX.3 Klein / FLUX.2 Klein** — Black Forest Labs.
- **Krea 2** — Krea.
- **Qwen** — équipe Qwen, Alibaba.
- **ComfyUI-GGUF** — [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF).
- **comfyui-krea2edit** — [lbouaraba/comfyui-krea2edit](https://github.com/lbouaraba/comfyui-krea2edit).

StableCraft n'est affilié ni à Stable.art, ni à PhotoCraft, ni à ComfyUI, ni aux
fournisseurs de modèles.

## Licence

Le code de StableCraft est sous licence **MIT** (voir [`LICENSE`](LICENSE)).
Les modèles, ComfyUI et PhotoCraft conservent leurs licences respectives. Aucun poids
de modèle n'est distribué dans ce dépôt.
