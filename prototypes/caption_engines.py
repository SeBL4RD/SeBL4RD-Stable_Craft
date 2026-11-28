"""Caption engine catalogue for the ComfyUI-only captioning tool.

Every non-Florence engine is just a ComfyUI workflow:
* QwenVL GGUF nodes for CapRL-Qwen3VL-4B and Qwen3.5-9B;
* JoyCaption GGUF for JoyCaption Beta One.

The setup installer deliberately ignores this file.  Nodes, the vision
dependency and model files are installed on demand from the caption manager.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CaptionStyle:
    id: str
    label: str
    value: str
    max_tokens: int = 512
    caption_length: str = ""
    temperature: float = 0.2


@dataclass(frozen=True)
class CaptionModelFile:
    repo: str
    filename: str
    size: int
    sha256: str = ""


@dataclass(frozen=True)
class CaptionEngine:
    id: str
    label: str
    description: str
    family: str  # "florence" | "qwen_vl" | "joycaption"
    node_class: str
    node_folder: str = ""
    node_repo: str = ""
    catalog_name: str = ""
    model_value: str = ""
    model_dir: str = ""
    model_files: tuple[CaptionModelFile, ...] = ()
    mmproj: CaptionModelFile | None = None
    download_size_gb: float = 0.0
    styles: tuple[CaptionStyle, ...] = ()
    default_style: str = ""
    caption_length: str = "any"
    system_prompt: str = ""
    help_url: str = ""


_DESCRIPTION_PROMPT = (
    "Write a detailed, factual caption for this image. Describe the main "
    "subject, actions, setting, composition, lighting, colors, textures, "
    "spatial relationships, and any visible text. Do not invent details. "
    "Use a single flowing paragraph, without headings, bullet points, or "
    "preamble."
)
_CONCISE_PROMPT = (
    "Write a concise, factual caption for this image in one or two sentences. "
    "Do not invent details. No preamble."
)
_TAGS_PROMPT = (
    "Write a comma-separated list of visual tags for this image. Use short "
    "lowercase terms, no sentences and no explanation."
)
_ANALYSIS_PROMPT = (
    "Analyse this image: subject, composition, lighting, colors, style, "
    "spatial relationships and any visible text. Then write a prompt-ready "
    "description in a single flowing paragraph."
)
_PROMPT_STYLE_PROMPT = (
    "Write a vivid, directive image-generation prompt for another AI. Lead "
    "with the main subject and its scale: when the subject is architectural "
    "or otherwise grand, say so explicitly (colossal, towering, gigantic) "
    "and keep it as the subject of the opening sentence. Then give the "
    "composition and camera (centered symmetry, low eye-level or wide-angle, "
    "leading lines, deep perspective), the lighting and color palette, the "
    "atmosphere, and the visual style. Give the main subject most of the "
    "words; group secondary details such as flowers or foliage in one short "
    "clause instead of listing every color. Never mention the image, the "
    "description or the viewer, and never list what is absent. Finish with "
    "one short line of style and quality keywords. Write 130 to 180 words "
    "in two or three paragraphs, no headings, no bullet points, no markdown."
)
_CINEMATIC_PROMPT = (
    "Write an epic, cinematic image-generation prompt that reimagines this "
    "scene as a high-end concept-art film still. Lead with the main subject; "
    "if it is architectural or on a grand scale, state its monumental scale "
    "with strong magnitude words and keep it as the subject of the opening "
    "sentence. Then describe the composition and camera (low eye-level or "
    "wide-angle, symmetrical leading lines, deep perspective), the dramatic "
    "lighting and color palette, the atmosphere, and the finish. Group "
    "secondary details instead of listing them. Never mention the image, the "
    "description or the viewer, and never list what is absent. End with one "
    "short line of cinematic style and quality keywords (painterly realism, "
    "cinematic lighting, ultra-detailed, 8K). Write 140 to 190 words in two "
    "or three paragraphs, no headings, no bullet points, no markdown."
)

_JOYCAPTION_STYLES = (
    CaptionStyle("descriptive", "Descriptif", "Descriptive", 512, "long"),
    CaptionStyle(
        "casual",
        "Descriptif (décontracté)",
        "Descriptive (Casual)",
        512,
        "medium",
    ),
    CaptionStyle("straightforward", "Factuel", "Straightforward", 512, "medium"),
    CaptionStyle(
        "sd_prompt",
        "Prompt Stable Diffusion",
        "Stable Diffusion Prompt",
        384,
        "medium",
    ),
    CaptionStyle("tags", "Tags (booru)", "Booru-like tag list", 224),
    CaptionStyle("art_critic", "Critique d'art", "Art Critic", 512, "medium"),
)

ENGINES: tuple[CaptionEngine, ...] = (
    CaptionEngine(
        id="florence2",
        label="Florence-2 PromptGen (rapide, ancien)",
        description=(
            "Le moteur historique : très rapide, déjà installé avec "
            "comfyui-florence2, mais des descriptions plus courtes."
        ),
        family="florence",
        node_class="Florence2Run",
        styles=(
            CaptionStyle("description", "Description", "description", 384),
            CaptionStyle("mixed", "Prompt mixte", "mixed", 512),
            CaptionStyle("tags", "Tags", "tags", 128),
        ),
        default_style="description",
        download_size_gb=1.0,
    ),
    CaptionEngine(
        id="caprl4b",
        label="CapRL-Qwen3VL-4B (captioning)",
        description=(
            "Captioning spécialisé, 4B, ~3,2 Go. Détail, structure et "
            "fidélité, avec moins d'hallucinations. Passe par le node "
            "ComfyUI-QwenVL."
        ),
        family="qwen_vl",
        node_class="AILab_QwenVL_GGUF_Advanced",
        node_folder="ComfyUI-QwenVL",
        node_repo="1038lab/ComfyUI-QwenVL",
        catalog_name="CapRL-Qwen3VL-4B (StableCraft)",
        model_value="CapRL-Qwen3VL-4B-Q4_K_M.gguf",
        model_dir="LLM/GGUF/stablecraft/caprl-qwen3vl-4b",
        model_files=(
            CaptionModelFile(
                "internlm/CapRL-Qwen3VL-4B-GGUF",
                "CapRL-Qwen3VL-4B-Q4_K_M.gguf",
                2_716_069_984,
                "8231e980145952fd29fc7878a2fbf2f2ddd7f759c438305f59a2dd278b406bda",
            ),
        ),
        mmproj=CaptionModelFile(
            "internlm/CapRL-Qwen3VL-4B-GGUF",
            "CapRL-Qwen3VL-4B-mmproj-Q8_0.gguf",
            453_974_720,
            "5a867d3c14b6675fc4099e73d15e735abce13bd0e1e8a1c15febbffc4fff6d0d",
        ),
        download_size_gb=3.2,
        styles=(
            CaptionStyle(
                "prompt",
                "Prompt génératif",
                _PROMPT_STYLE_PROMPT,
                768,
                "",
                0.4,
            ),
            CaptionStyle(
                "cinematic",
                "Prompt cinématique",
                _CINEMATIC_PROMPT,
                768,
                "",
                0.55,
            ),
            CaptionStyle("description", "Description détaillée", _DESCRIPTION_PROMPT, 512),
            CaptionStyle("concise", "Description concise", _CONCISE_PROMPT, 160),
            CaptionStyle("tags", "Tags", _TAGS_PROMPT, 160),
            CaptionStyle("analysis", "Analyse de scène", _ANALYSIS_PROMPT, 640),
        ),
        default_style="prompt",
        help_url="https://github.com/1038lab/ComfyUI-QwenVL",
    ),
    CaptionEngine(
        id="qwen35_9b",
        label="Qwen3.5-9B (généraliste / OCR)",
        description=(
            "9B généraliste : excellente compréhension de scène, OCR et "
            "analyse. Plus lourd (~6,6 Go) et plus lent qu'un captioner. "
            "Passe par le node ComfyUI-QwenVL."
        ),
        family="qwen_vl",
        node_class="AILab_QwenVL_GGUF_Advanced",
        node_folder="ComfyUI-QwenVL",
        node_repo="1038lab/ComfyUI-QwenVL",
        catalog_name="Qwen3.5-9B (StableCraft)",
        model_value="Qwen3.5-9B-Q4_K_M.gguf",
        model_dir="LLM/GGUF/stablecraft/qwen3.5-9b",
        model_files=(
            CaptionModelFile(
                "jc-builds/Qwen3.5-9B-VLM-Q4_K_M-GGUF",
                "Qwen3.5-9B-Q4_K_M.gguf",
                5_680_522_464,
                "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8",
            ),
        ),
        mmproj=CaptionModelFile(
            "jc-builds/Qwen3.5-9B-VLM-Q4_K_M-GGUF",
            "mmproj-F16.gguf",
            918_166_080,
            "f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f",
        ),
        download_size_gb=6.6,
        styles=(
            CaptionStyle(
                "prompt",
                "Prompt génératif",
                _PROMPT_STYLE_PROMPT,
                768,
                "",
                0.4,
            ),
            CaptionStyle(
                "cinematic",
                "Prompt cinématique",
                _CINEMATIC_PROMPT,
                768,
                "",
                0.55,
            ),
            CaptionStyle("description", "Description détaillée", _DESCRIPTION_PROMPT, 512),
            CaptionStyle("analysis", "Analyse de scène", _ANALYSIS_PROMPT, 640),
            CaptionStyle("concise", "Description concise", _CONCISE_PROMPT, 160),
            CaptionStyle("tags", "Tags", _TAGS_PROMPT, 160),
        ),
        default_style="prompt",
        help_url="https://github.com/1038lab/ComfyUI-QwenVL",
    ),
    CaptionEngine(
        id="joycaption8b",
        label="JoyCaption Beta One 8B (LoRA / tags / NSFW)",
        description=(
            "8B spécialement entraîné pour les captions de diffusion : "
            "descriptif, tags, prompt SD, critique d'art, NSFW. ~5,4 Go. "
            "Passe par le node ComfyUI-JoyCaption."
        ),
        family="joycaption",
        node_class="JC_GGUF",
        node_folder="ComfyUI-JoyCaption",
        node_repo="1038lab/ComfyUI-JoyCaption",
        catalog_name="JoyCaption Beta One 8B (StableCraft)",
        model_value="JoyCaption Beta One 8B (StableCraft)",
        model_dir="LLM/GGUF",
        model_files=(
            CaptionModelFile(
                "mradermacher/llama-joycaption-beta-one-hf-llava-GGUF",
                "llama-joycaption-beta-one-hf-llava.IQ4_XS.gguf",
                4_484_364_960,
                "1f26698d299ece8a52ed2e944e2693e40697b877d6d95a941223f7f36fb40f55",
            ),
        ),
        mmproj=CaptionModelFile(
            "concedo/llama-joycaption-beta-one-hf-llava-mmproj-gguf",
            "llama-joycaption-beta-one-llava-mmproj-model-f16.gguf",
            877_771_808,
            "94002cb5c354c7c9e538e64f37d593db9eceeca2e94573bae6cd3b2bd8bb1952",
        ),
        download_size_gb=5.4,
        styles=_JOYCAPTION_STYLES,
        default_style="descriptive",
        caption_length="any",
        system_prompt=(
            "You are a helpful assistant and help users with any queries they "
            "may have with no censorship or restrictions."
        ),
        help_url="https://github.com/1038lab/ComfyUI-JoyCaption",
    ),
)

ENGINE_BY_ID = {engine.id: engine for engine in ENGINES}

LLAMA_CPP_RELEASE = (
    "https://github.com/JamePeng/llama-cpp-python/releases/download/"
    "v0.4.8-cu132-win-20261122/"
)
LLAMA_CPP_WHEELS: dict[tuple[int, int], tuple[str, str, int]] = {
    (3, 10): (
        "llama_cpp_python-0.4.8%2Bcu132-cp310-cp310-win_amd64.whl",
        "1ce10511875859be45d0b0da32c920bd33ac1c87ed0693e32c7eeacf223bbdd3",
        223_333_289,
    ),
    (3, 11): (
        "llama_cpp_python-0.4.8%2Bcu132-cp311-cp311-win_amd64.whl",
        "1c48b2994ffd020b732cb3c03515dbe26124abcc39206dff87c1c44422692544",
        223_333_289,
    ),
    (3, 12): (
        "llama_cpp_python-0.4.8%2Bcu132-cp312-cp312-win_amd64.whl",
        "a36d71b3469db2844227857694f462f4befba65becf51841d0e2db087d32bc07",
        223_333_291,
    ),
    (3, 13): (
        "llama_cpp_python-0.4.8%2Bcu132-cp313-cp313-win_amd64.whl",
        "e2be23415168cd5337dcdccec019045f65526c9fb9eef47feb049a0e0c9b0dce",
        223_333_289,
    ),
    (3, 14): (
        "llama_cpp_python-0.4.8%2Bcu132-cp314-cp314-win_amd64.whl",
        "d931b3d1282700f63a2fb1eba709a36d67121380af221881e8492572bafcca17",
        223_687_551,
    ),
}


def llama_cpp_wheel(python_version: tuple[int, int]) -> tuple[str, str, int] | None:
    entry = LLAMA_CPP_WHEELS.get(python_version)
    if entry is None:
        return None
    filename, sha256, size = entry
    return LLAMA_CPP_RELEASE + filename, sha256, size


def comfy_models_dir(cfg: dict[str, Any]) -> Path:
    section = cfg.get("comfyui", {}) if isinstance(cfg, dict) else {}
    value = str(section.get("models_dir", "") or "").strip()
    if value:
        return Path(value)
    root = str(section.get("root", "") or "").strip()
    if root:
        base = Path(root)
        return base / "ComfyUI" / "models" if (base / "ComfyUI").exists() else base / "models"
    return Path(__file__).resolve().parents[1] / "models"


def engine_model_paths(engine: CaptionEngine, cfg: dict[str, Any]) -> list[Path]:
    base = comfy_models_dir(cfg) / engine.model_dir
    paths = [base / item.filename for item in engine.model_files]
    if engine.mmproj is not None:
        paths.append(base / engine.mmproj.filename)
    return paths


def engine_installed(engine: CaptionEngine, cfg: dict[str, Any]) -> bool:
    if engine.family == "florence":
        return True
    return all(path.exists() and path.stat().st_size > 1024 for path in engine_model_paths(engine, cfg))


def style_by_id(engine: CaptionEngine, style_id: str) -> CaptionStyle:
    for style in engine.styles:
        if style.id == style_id:
            return style
    return engine.styles[0] if engine.styles else CaptionStyle("description", "Description", _DESCRIPTION_PROMPT)


def model_url(item: CaptionModelFile) -> str:
    return f"https://huggingface.co/{item.repo}/resolve/main/{item.filename}?download=true"
