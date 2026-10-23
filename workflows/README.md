# Workflows ComfyUI (format API)

Ces fichiers sont des workflows **API** (pas le format UI sauvegardé par ComfyUI).
Ils contiennent des placeholders (`__IMAGE__`, `__PROMPT__`, etc.) que StableCraft
remplace avant `POST /prompt`.

| Fichier | Profil | Statut |
|---|---|---|
| `flux3_klein_edit.api.json` | FLUX.3 Klein Edit | ✅ validé sur RTX 3080 Ti 12 Go |
| `flux2_klein_edit.api.json` | FLUX.2 Klein 9B Edit | ✅ validé sur RTX 3080 Ti 12 Go |

## Remplacements

- `__IMAGE__` : nom du fichier uploadé via `/upload/image` (dans `input/`).
- `__PROMPT__` / `__NEGATIVE__` : texte.
- `__UNET__` / `__TEXT_ENCODER__` / `__VAE__` : noms exacts des fichiers dans
  `ComfyUI/models/`.
- `__SEED__`, `__STEPS__`, `__CFG__` : valeurs numériques (à injecter dans le JSON,
  pas comme chaînes).

## Pièges validés

1. **FLUX.3** : `CLIPLoader` + `Qwen-3-VL-4B-Scaled-FP8-v2.safetensors` (type `flux3`).
   Le GGUF `Qwen3VL-4B-Instruct-Q4_K_M.gguf` avec `CLIPLoaderGGUF` échoue
   (`mat1 and mat2 shapes cannot be multiplied`).
2. **Combo dynamique** : écrire `"resolution": "resize"` **et**
   `"resolution.megapixels": 1.0` au même niveau. Un objet imbriqué est rejeté.
3. **Autogrow** : l'image de référence s'écrit `"images.image0"` (pas `"images"`).
4. **FLUX.2** : `UnetLoaderGGUF` + `CLIPLoaderGGUF` (type `flux2`) + `ReferenceLatent`.
   Le VAE est `flux2_vae.safetensors` pour FLUX.2 et FLUX.3.
5. **Alignement** : les dimensions du crop doivent être des multiples de 16.
6. **Sortie** : `ReferenceMultiLatent` renvoie un latent à la taille de la référence
   (environ 1 MP). Redimensionner le PNG au crop avant recomposition.

## Test rapide

```powershell
# ComfyUI doit tourner sur 12452
Invoke-RestMethod http://127.0.0.1:12452/system_stats
F:\ComfyUI_windows_portable\python_embeded\python.exe prototypes\stablecraft_proto.py
```
