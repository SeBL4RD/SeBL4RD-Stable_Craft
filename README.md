# StableCraft

**Stable.art's lasso editing, inside PhotoCraft, powered by ComfyUI.**

StableCraft is a companion app for PhotoCraft: draw a lasso around an area, describe
the change, and the result arrives as a **new masked layer**. Everything runs locally
on your own GPU, with ComfyUI as the generation engine.

![Version](https://img.shields.io/badge/version-0.2.0-3b82f6)
![Status](https://img.shields.io/badge/status-working%20MVP-22c55e)
![Platform](https://img.shields.io/badge/platform-Windows%20x64-6b7280)
![License](https://img.shields.io/badge/license-MIT-8b5cf6)

**Repository:** [github.com/SeBL4RD/SeBL4RD-Stable_Craft](https://github.com/SeBL4RD/SeBL4RD-Stable_Craft)

## Highlights

- lasso → prompt → edit → PhotoCraft layer;
- layer with **mask and feather**;
- **persistent gallery per layer**: regenerate, compare, switch generations;
- regeneration works even after the selection is lost;
- **two modes**: EDIT (source image) or T2I (text only), EDIT by default;
- **per-layer reference image** (Krea 2, FLUX.3 Klein and Qwen Image 2.1);
- five profiles: FLUX.3 Klein, FLUX.2 Klein 9B, Krea 2 General Edit
  (base + LoRA), Krea 2 Identity Edit and Qwen Image 2.1;
- on-demand model manager (**Locate** / **Download**) and automatic check for the
  `comfyui-krea2edit` node;
- English/French UI, English by default;
- no model weights in the repository;
- no silent downloads.


<a href="./demo/t2i_forest.png" target="_blank"><img src="./demo/t2i_forest.png" alt="Image 1" width="400"></a> <a href="./demo/DEMO_StableCraft_EDIT.jpg" target="_blank"><img src="./demo/DEMO_StableCraft_EDIT.jpg" alt="Image 2" width="400"></a>


<a href="./demo/DEMO_full.jpg" target="_blank">
  <img src="./demo/DEMO_full.jpg" alt="image info" width="600">
</a>

## How it works

StableCraft does not modify or fork PhotoCraft.

PhotoCraft is driven through its **local control channel**: reading the selection,
saving the composite, inserting the layer and creating the mask. ComfyUI is driven over
HTTP. Both applications stay independent and can be updated separately. Compatibility is
checked through the commands exposed by each build, not through a fixed version number.

## Requirements

### Hardware

- Windows 10/11 **x64**.
- **NVIDIA** GPU only, for now.
- **12 GB of VRAM** tested on an RTX 3080 Ti; 32 GB of RAM.
- Below 12 GB of VRAM is not validated today.

### Software

- **PhotoCraft 0.16.0** or newer (portable or installed).
- **ComfyUI portable** (with `python_embeded\python.exe`), recent enough:
  `0.42.1+` for Qwen Image 2.1 and the Krea 2 nodes.
- **Python 3.11+**.
- For Krea 2: the custom node
  [`comfyui-krea2edit`](https://github.com/lbouaraba/comfyui-krea2edit).
- `ComfyUI-GGUF` to load GGUF UNet models.

### Models

Weights are **not** bundled. They must be visible to ComfyUI. StableCraft can locate
or download missing files on demand, with explicit confirmation.

| Profile | UNet | Text encoder | VAE | Steps / CFG |
|---|---|---|---|---|
| **FLUX.3 Klein** (default) | `flux-3-image-klein-Q8_0.gguf` | `qwen3vl_4b_fp8_scaled.safetensors` | `flux2_vae.safetensors` | 16 / 1.0 |
| **FLUX.2 Klein 9B** | `flux-2-klein-Distilled-9b-Q8_0.gguf` | `Qwen3-8B-Q4_K_M.gguf` | `flux2_vae.safetensors` | 4 / 1.0 |
| **Krea 2 General Edit** | `krea2_turbo_fp8_scaled.safetensors` + `krea2_general_edit_v2.safetensors` | `qwen3vl_4b_fp8_scaled.safetensors` | `qwen_image_vae.safetensors` | 8 / 1.0 |
| **Krea 2 Identity Edit** | `krea2_turbo_edit-Q4_K_M.gguf` | `qwen3vl_4b_fp8_scaled.safetensors` | `qwen_image_vae.safetensors` | 8 / 1.0 |
| **Qwen Image 2.1** | `qwen_image_2.1_Q4_K_M.gguf` (or Q8_0) | `qwen3vl_8b_w4a8.safetensors` (or INT8) | `qwen_image_2.1_vae_bf16.safetensors` | 25 / 1.0 |

Notes:

- **Krea 2 EDIT is experimental**: results are inconsistent, especially on large areas.
  The **General Edit** profile (official base + LoRA) is recommended for general editing;
  the **Identity Edit** profile is a merged file intended for characters. In T2I, Krea 2
  General Edit uses the base alone, without the LoRA;
- the tested `Qwen3VL-4B-Instruct-Q4_K_M.gguf` GGUF is not compatible with FLUX.3 or
  Krea 2; StableCraft uses the FP8 safetensors instead;
- `Qwen3-8B-Q4_K_M.gguf` works for FLUX.2;
- Qwen Image 2.1 uses a **dedicated VAE** (`qwen_image_2.1_vae_bf16.safetensors`) and a
  **Qwen3-VL-8B** text encoder, both different from Krea 2. The GGUF diffusion model is
  offered as Q4_K_M and Q8_0. The official text encoder defaults to **W4A8**
  (`qwen3vl_8b_w4a8.safetensors`, 6.3 GB) instead of INT8 (9.35 GB): same vision
  encoder, native ComfyUI W4A8 support, about 3 GB saved. Select **INT8** in the
  download menu for maximum fidelity;
- the Qwen 2.1 GGUF must contain the `qwen_image` architecture metadata expected by
  `UnetLoaderGGUF`. The **Unsloth** files do not contain it and cannot be loaded as-is;
  StableCraft points to
  [`Abiray/Qwen-Image-2.1-GGUF`](https://huggingface.co/Abiray/Qwen-Image-2.1-GGUF),
  converted for ComfyUI-GGUF;
- Qwen Image 2.1 uses ComfyUI's **built-in** nodes (`TextEncodeQwenImage21`,
  `QwenImage21Cache`): no extra custom node is required;
- Qwen Image 2.1 is under a **non-commercial research license**;
- model licenses apply (FLUX Kommunity, Krea Community, Qwen Research, etc.),
  separately from the MIT license of the code.

## Installation

### Option 1 — Windows installer (recommended)

Double-click **`InstallStableCraft.bat`** at the repository root.

The installer configures **the current folder**: it detects PhotoCraft and ComfyUI,
creates `user\` and `models\`, writes `config.toml` when needed and adds a
**StableCraft** shortcut. It does not copy anything to AppData or another folder, and
does not download any model.

Command line:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\install.ps1
```

### Option 2 — manual

```powershell
Copy-Item config.example.toml config.toml
.\StableCraft.bat
```

The launcher needs `config.toml`; the simplest path is to copy the example. Paths can
stay empty when auto-detection is enough. The important paths are:

```toml
[photocraft]
executable = "D:/.../photocraft.exe"
control_port = 7990

[comfyui]
root = "F:/ComfyUI_windows_portable"
python = "F:/ComfyUI_windows_portable/python_embeded/python.exe"
```

The default control port is **7990**. Port 7878 is inside a Windows excluded port
range on some machines, which makes PhotoCraft's control channel fail with an
“access permissions” error.

When launched, `StableCraft.bat`:

1. checks the required paths;
2. starts ComfyUI when needed, **without opening a browser**;
3. starts PhotoCraft with the control channel when needed;
4. cleans temporary StableCraft files from “Open Recent”;
5. opens the UI.

A clear message is shown when a required path is missing. Missing models do not block
installation: the UI reports them and **Generate** opens the model manager with
**Locate** and **Download** actions.

## Usage

1. Open an image in PhotoCraft.
2. Draw a **lasso** around the area to edit.
3. In StableCraft: choose the **mode** (EDIT by default, or T2I), the profile,
   write the prompt, then click **Generate**.
4. The result is added as a **StableCraft layer** with a mask.
5. The layer gallery appears under the prompt.

In **T2I**, no scene image is sent: the prompt generates an image at the crop size
(selection + context), then PhotoCraft masks it with the selection. A rectangular
selection gives cleaner results than an irregular lasso. The session's `base.png`
remains the original image: switching back to EDIT on the same layer always uses that
scene, never the previous T2I image. To use the T2I image as a new scene, draw a new
lasso.

### Regenerate and gallery

- Same selection → **Regenerate** updates the **same layer** and adds a thumbnail.
- Every generation starts from the `base.png` frozen at lasso time, never from the
  composite with previous generations.
- Click a thumbnail to apply that generation without running ComfyUI again.
- Selection lost → select the `StableCraft [id]` layer, then **Regenerate**.
- New selection → new gallery and new layer.

### Reference image

- check **Use a reference image**;
- click the thumbnail or drop an image;
- the reference belongs to the layer and reloads when you return to it;
- supported by **Krea 2**, **FLUX.3 Klein** and **Qwen Image 2.1**;
- in **EDIT**, the model receives **image 1 = scene** and **image 2 = reference**;
- in **T2I**, FLUX.3 Klein and Qwen Image 2.1 use the reference as image 1 to guide
  a new image. Krea 2 uses references in EDIT;
- describe in the prompt what you take from the reference.

Example:

> Add the black leather glove from the reference image to the man's right hand.
> Keep the hand pose, arm, skin tone, lighting and background unchanged.

The **Guide** button next to `PROMPT` opens a non-blocking window with best practices
and examples.

### Models and custom node

- missing files are listed with **Locate** (use an existing file) and **Download**
  (with size, source and confirmation);
- quantization choices are limited to **Q4_K_M**, **Q8_0** and **BF16** where the model
  provides them;
- downloaded files go to the project's `models/` folder and are added to ComfyUI's
  `extra_model_paths.yaml`;
- after a file is located or downloaded, the manager offers to restart ComfyUI
  automatically so the file becomes visible;
- a file already inside `models/` is moved to the expected subfolder instead of being
  copied again;
- the **comfyui-krea2edit** node is checked at startup and can be installed or updated
  from the model manager.

### Preview

- **Document**: the PhotoCraft composite after applying the layer.
- **Crop**: the generated result at crop size, before masking.

## Storage

Nothing is stored in AppData.

```text
<StableCraft folder>/
  user/
    control.token
    sessions/<id>/       # base, mask, reference, gallery
    logs/
    model_selection.json # selected quantization per profile
  models/                # local models, no weights in git
```

Paths are configurable in `config.toml` (`[app]`, `[photocraft]`, `[comfyui]`,
`[models]`).

## Language

The UI supports **English and French**. English is the default for new installations.
Use the language selector in the header; the choice is saved in
`config.toml` (`[app] language`). Restart the UI to apply it.

A French version of this README is available in [`README.fr.md`](README.fr.md).

## Updates

StableCraft checks the latest GitHub Release at startup. When a newer version exists,
a clickable notice appears in the header and opens the Releases page. Files are not
replaced at runtime: `config.toml`, `user/` and `models/` are always preserved, and
updating remains an explicit action.

## Credits

- **Stable.art** — inspiration for the lasso + prompt experience.
- **PhotoCraft** — host application and control channel:
  [storytold/photocraft](https://github.com/storytold/photocraft).
- **ComfyUI** — generation engine:
  [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI).
- **FLUX.3 Klein / FLUX.2 Klein** — Black Forest Labs.
- **Krea 2** — Krea.
- **Qwen** — Qwen team, Alibaba.
- **ComfyUI-GGUF** — [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF).
- **comfyui-krea2edit** — [lbouaraba/comfyui-krea2edit](https://github.com/lbouaraba/comfyui-krea2edit).

StableCraft is not affiliated with Stable.art, PhotoCraft, ComfyUI or any model provider.

## License

StableCraft code is released under the **MIT** license (see [`LICENSE`](LICENSE)).
Models, ComfyUI and PhotoCraft keep their own licenses. No model weights are
distributed in this repository.
