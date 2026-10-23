# Modèles

Ce dossier est le dossier dédié **par défaut** pour les modèles téléchargés par
StableCraft. Il est ignoré par git : aucun poids n'est versionné.

```
models/
├─ unet/            # diffusion GGUF (FLUX.2/3 Klein, Krea 2)
├─ text_encoders/   # Qwen3-8B, Qwen3-VL-4B, ...
├─ vae/             # flux2_vae, qwen_image_vae
└─ loras/           # LoRA éventuels
```

## Important

ComfyUI ne voit pas ce dossier automatiquement. Deux options :

1. Ajouter une section dans `extra_model_paths.yaml` de ComfyUI :

   ```yaml
   stablecraft:
     base_path: C:/Users/<user>/AppData/Local/StableCraft/models
     unet: unet
     text_encoders: text_encoders
     vae: vae
     loras: loras
   ```

2. Ou créer des junctions/symlinks depuis les dossiers `models/` de ComfyUI.

Si tes modèles sont déjà dans ComfyUI, tu n'as rien à faire : laisse les chemins
commentés dans `config.toml`, StableCraft utilise ce que ComfyUI voit déjà.

Aucun modèle n'est téléchargé sans consentement. Voir `docs/MODELS.md` pour les
fichiers, tailles, encodeurs et licences.
