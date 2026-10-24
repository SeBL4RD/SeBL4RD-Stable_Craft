# Modèles

Dossier local pour les modèles de StableCraft. **Aucun poids n'est versionné.**

Sous-dossiers attendus : `unet/`, `text_encoders/`, `vae/`, `loras/`.

ComfyUI doit voir ce dossier, par exemple avec une section `stablecraft` dans
`extra_model_paths.yaml` (voir `config.toml`, clé `[models] store_dir`). Si les modèles
sont déjà dans ComfyUI, laisse les chemins commentés dans `config.toml`.

StableCraft ne télécharge aucun modèle sans consentement explicite.
