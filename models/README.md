# Models

Local folder for StableCraft models. **No weights are versioned.**

Expected subfolders: `unet/`, `text_encoders/`, `vae/`, `loras/`.

ComfyUI must see this folder, for example through a `stablecraft` section in
`extra_model_paths.yaml`. StableCraft's model manager creates that section
automatically when it downloads or copies a file.

If the models already live in ComfyUI's folders, leave the paths commented out in
`config.toml`; the manager will detect them through ComfyUI.

**Locate** accepts any supported filename (GGUF or safetensors); it does not need to
match the name in `models.json`. Files already in a ComfyUI model folder are used in
place, without being copied here.

StableCraft never downloads a model without explicit confirmation.
