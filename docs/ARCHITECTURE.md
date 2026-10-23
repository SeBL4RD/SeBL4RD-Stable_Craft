# Architecture technique — StableCraft (fork natif PhotoCraft)

> Cette page décrit la voie recommandée : un fork de PhotoCraft avec un panneau IA
> natif et un client ComfyUI. Le prototype Python valide déjà le pipeline ; il reste à
> le porter dans le moteur Rust.

## 1. Arborescence du fork

```
StableCraft/
├─ photocraft/                 # upstream storytold/photocraft (remote `upstream`)
│  ├─ crates/
│  │  ├─ comfy/                # NOUVEAU : client + workflows ComfyUI
│  │  ├─ engine/src/ai_cmds.rs # NOUVEAU : commandes ai.*
│  │  └─ ui-egui/src/stablecraft.rs # NOUVEAU : panneau
│  └─ ...
├─ docs/                       # recherche, design, démos
├─ prototypes/                 # PoC Python
└─ workflows/                  # workflows API ComfyUI de référence
```

Le fork garde `upstream` comme remote :

```powershell
git clone https://github.com/storytold/photocraft.git photocraft
cd photocraft
git remote add upstream https://github.com/storytold/photocraft.git
git switch -c stablecraft
```

À chaque release upstream : `git fetch upstream && git rebase upstream/main`.
Les modifications doivent rester concentrées dans :

- `crates/comfy/` (nouveau crate) ;
- `crates/engine/src/ai_cmds.rs` (nouveau module) ;
- `crates/ui-egui/src/stablecraft.rs` (nouveau panneau) ;
- quelques lignes de registre : `engine/src/lib.rs`, `engine/src/commands.rs`,
  `ui-egui/src/lib.rs`, `ui-egui/src/dock.rs`, `ui-egui/src/panels.rs`,
  `ui-egui/src/panel_docking.rs`, `ui-egui/src/state.rs`, `engine/src/prefs.rs`,
  `Cargo.toml`, `xtask/src/layers.rs`.

## 2. Crate `photocraft-comfy`

### Position dans les couches

- **L4**, à côté de `io` et `plugins`, au-dessus de `doc`/`compose`/`codecs`.
- Compile pour `wasm32-unknown-unknown` (obligatoire pour L0–L6) : le module réseau
  est `#[cfg(not(target_arch = "wasm32"))]`, et les fonctions wasm renvoient
  `Err("ComfyUI is only available in the desktop build")`.
- Pas de dépendance UI ; pas de `egui`.
- Client HTTP : `ureq` avec `default-features = false` (HTTP loopback uniquement, pas
  de TLS) ou un client maison `std::net::TcpStream` inspiré de `photocraft-ipp`.
  Éviter `reqwest` + Tokio pour ne pas alourdir le build.

### Types principaux

```rust
pub struct ComfyConfig {
    pub endpoint: String,        // http://127.0.0.1:12452
    pub timeout: Duration,
}

pub struct ComfyStatus {
    pub version: String,
    pub gpu_name: String,
    pub vram_total: u64,
    pub vram_free: u64,
}

pub struct AvailableModels {
    pub diffusion: Vec<String>,  // UnetLoaderGGUF / UNETLoader
    pub text_encoders: Vec<String>,
    pub vaes: Vec<String>,
}

pub enum Profile {
    Flux3Klein,
    Flux2Klein9b,
    Krea2Turbo,
}

pub struct EditRequest {
    pub profile: Profile,
    pub prompt: String,
    pub negative: String,
    pub image_png: Vec<u8>,      // crop
    pub mask_png: Option<Vec<u8>>,
    pub width: u32,
    pub height: u32,
    pub steps: u32,
    pub cfg: f32,
    pub seed: u64,
    pub batch: u32,
}

pub struct EditResult {
    pub images: Vec<Vec<u8>>,    // PNG
    pub seed: u64,
    pub elapsed: Duration,
}
```

### Client

```rust
pub trait ComfyClient {
    fn status(&self) -> Result<ComfyStatus>;
    fn models(&self) -> Result<AvailableModels>;
    fn upload(&self, name: &str, png: &[u8]) -> Result<String>;
    fn queue(&self, workflow: &serde_json::Value) -> Result<String>; // prompt_id
    fn history(&self, prompt_id: &str) -> Result<HistoryEntry>;
    fn view(&self, image: &ImageRef) -> Result<Vec<u8>>;
    fn interrupt(&self) -> Result<()>;
    fn delete_queued(&self, prompt_id: &str) -> Result<()>;
}
```

Points d'attention :

- `/upload/image` est du `multipart/form-data` ; construire le corps à la main ou
  utiliser `ureq`'s multipart.
- `/prompt` renvoie `400` avec `node_errors` : remonter le message lisible
  (`required_input_missing`, `value_not_in_list`, etc.).
- `/history/{id}` peut être vide pendant l'exécution ; poller toutes les 500 ms.
- Les sorties sont dans `outputs.<node_id>.images[]` ; prendre le premier `SaveImage`.
- `/view` accepte `filename`, `subfolder`, `type`.
- Annulation : `POST /interrupt` interrompt l'exécution en cours ; pour la file,
  `POST /queue {"delete":[prompt_id]}`.
- Ne jamais bloquer le thread UI : tout passe par `jobs::run`.

### Constructeurs de workflows

Chaque profil est un `serde_json::Value` au format API ComfyUI. Les modèles sont
paramétrables (noms de fichiers) pour s'adapter aux installations.

**FLUX.3 Klein Edit** (validé) :

```json
{
  "1": {"class_type":"UnetLoaderGGUF","inputs":{"unet_name":"flux-3-image-klein-Q8_0.gguf"}},
  "2": {"class_type":"CLIPLoader","inputs":{"clip_name":"Qwen-3-VL-4B-Scaled-FP8-v2.safetensors","type":"flux3"}},
  "3": {"class_type":"VAELoader","inputs":{"vae_name":"flux2_vae.safetensors"}},
  "4": {"class_type":"CLIPTextEncode","inputs":{"clip":["2",0],"text":"PROMPT"}},
  "5": {"class_type":"CLIPTextEncode","inputs":{"clip":["2",0],"text":""}},
  "6": {"class_type":"LoadImage","inputs":{"image":"UPLOADED"}},
  "7": {"class_type":"ReferenceMultiLatent","inputs":{
        "positive":["4",0],"negative":["5",0],"vae":["3",0],
        "images.image0":["6",0],"resolution":"resize","resolution.megapixels":1.0}},
  "8": {"class_type":"KSampler","inputs":{
        "model":["1",0],"seed":0,"steps":16,"cfg":1,
        "sampler_name":"euler","scheduler":"simple",
        "positive":["7",0],"negative":["7",1],"latent_image":["7",2],"denoise":1}},
  "9": {"class_type":"VAEDecode","inputs":{"samples":["8",0],"vae":["3",0]}},
  "10":{"class_type":"SaveImage","inputs":{"images":["9",0],"filename_prefix":"StableCraft"}}
}
```

**FLUX.2 Klein 9B Edit** (validé) :

```
UnetLoaderGGUF(flux-2-klein-Distilled-9b-Q8_0.gguf)
CLIPLoaderGGUF(Qwen3-8B-Q4_K_M.gguf, type=flux2)
VAELoader(flux2_vae.safetensors)
LoadImage → ImageScaleToTotalPixels(1 MP) → VAEEncode
CLIPTextEncode(positive) → ReferenceLatent(latent)
ConditioningZeroOut(positive) → ReferenceLatent(latent)
KSampler(steps=6, cfg=1, euler/simple, latent=VAEEncode)
VAEDecode → SaveImage
```

**Krea 2 Edit** (phase 3) :

```
UnetLoaderGGUF(krea2_turbo_edit-Q4_K_M.gguf)  (ou Krea-2-Turbo + LoRA)
CLIPLoader(Qwen-3-VL-4B-Scaled-FP8-v2.safetensors, type=krea2)
VAELoader(qwen_image_vae.safetensors)
LoadImage → VAEEncode → Krea2EditModelPatch.source_latent
Krea2EditGroundedEncode(prompt, image) → positive
Krea2EditGroundedEncode("", image) → negative
EmptySD3LatentImage → KSampler.latent_image
Krea2EditModelPatch.model → KSampler.model
KSampler(8 steps, cfg=1) → VAEDecode → SaveImage
```

La variante Krea 2 est plus délicate : le nœud custom `comfyui-krea2edit` doit être
installé, et les LoRA/modèles doivent correspondre. À valider par un test réel avant
de l'exposer dans l'UI.

## 3. Commandes moteur

Fichier `crates/engine/src/ai_cmds.rs`, avec `pub fn specs() -> Vec<CommandSpec>` et
un `v.extend(crate::ai_cmds::specs())` dans `commands.rs`.

### `ai.comfy.status`

```rust
CommandSpec {
    id: "ai.comfy.status",
    label: "StableCraft: ComfyUI Status",
    menu: &[],
    shortcut: None,
    params: r##"{"endpoint":str?}"##,
    enabled: |_| Ok(()),
    run: |_s, p| {
        let endpoint = endpoint_from(p, &s.prefs().integrations);
        let status = ComfyClient::new(endpoint)?.status()?;
        Ok(json!(status))
    },
    journal: false,
}
```

### `ai.edit`

Paramètres :

```json
{
  "profile": "flux3Klein|flux2Klein9b|krea2",
  "prompt": "string",
  "negative": "string?",
  "mode": "edit|generate",
  "source": "composite|activeLayer",
  "padding": 96,
  "feather": 10,
  "steps": 16,
  "cfg": 1,
  "seed": 0,
  "batch": 1,
  "output": "newLayer|newLayerMasked|replace"
}
```

Algorithme :

1. Vérifier qu'un document est actif.
2. Choisir la zone :
   - `edit` : `doc.selection.content_bounds()` ; erreur si pas de sélection.
   - `generate` : bbox de sélection ou canvas entier.
3. Construire le crop :
   - `bbox` + `padding`, clamp au canvas ;
   - aligner largeur/hauteur sur 16 (ou 32 pour Krea 2) ;
   - si le crop dépasse le canvas, étendre avec des pixels transparents (pour
     l'outpaint) ou clamper (MVP).
4. Extraire le composite du crop :
   - `photocraft_io::export(&doc, "png", &opts)` pour un PNG sRGB 8 bits ;
   - décoder le PNG (`photocraft_codecs::decode`) et cropper ;
   - alternative : `photocraft_compose::render(&doc, crop).to_rgba8()` +
     `photocraft_cms` pour la conversion.
5. Extraire le masque : `algo::selection::mask_from_surface(Some(sel), crop)`,
   feather gaussien, inversion si demandé. Encoder en PNG grayscale.
6. Uploader image + masque (si le workflow en a besoin).
7. Lancer le job (`jobs::run`) :
   - work : queue + poll + download ;
   - apply : pour chaque image, décoder, redimensionner au crop, créer un calque
     raster, appliquer le masque de calque, insérer au-dessus du calque actif.
8. Retourner `{job, promptId, seed, previews:[base64…]}`.

Pour le MVP, `batch=1` et `output=newLayerMasked`. Le mode batch et les vignettes
viendront ensuite.

### Application du résultat

```rust
fn apply_edit(
    s: &mut Session,
    crop: Rect,
    png: &[u8],
    selection: Option<Surface>,
    name: &str,
) -> Result<LayerId> {
    let img = photocraft_codecs::decode(png)?;
    let img = img.convert(ChannelLayout::Rgba, SampleType::U8);
    let (w, h) = img.dimensions();
    let fmt = s.active().ok_or(EngineError::NoDocument)?.doc.pixel_format();

    // Construire une Surface au format du document, positionnée à crop.x0/y0.
    let surface = rgba_to_surface(img.data(), w, h, crop.x0, crop.y0, fmt)?;

    s.edit("StableCraft Edit", |doc, active| {
        let mut layer = Layer::raster(name, doc.pixel_format());
        *layer.surface_mut().ok_or(...)? = surface;
        let id = doc.insert_above(*active, layer);
        if let Some(sel) = selection {
            let mask = LayerMask { surface: sel, ..LayerMask::reveal_all() };
            doc.layer_mut(id).ok_or(...)?.mask = Some(mask_at_depth(mask, doc.depth)?);
        }
        *active = Some(id);
        Ok(id)
    })
}
```

Notes :

- Le résultat doit être **exactement** de la taille du crop. Sinon, resize Lanczos
  avant insertion.
- Le masque de calque est la sélection d'origine (pas le masque feather envoyé au
  modèle), pour rester éditable.
- Si `output=replace`, remplacer le contenu du calque actif au lieu d'insérer.
- Si le document est en CMYK/Lab, convertir le PNG sRGB vers le profil du document
  via `photocraft-cms` avant d'écrire la Surface.

## 4. Panneau UI

Fichier `crates/ui-egui/src/stablecraft.rs`.

### Enregistrement

Le plus simple pour le MVP : un onglet dans le groupe `History` (comme `Actions`),
puis un groupe dédié plus tard.

```rust
// dock.rs
Group::History => &["History", "Actions", "Layer Comps", "StableCraft"],

// panels.rs
(Group::History, 0) => history(app, ui),
(Group::History, 1) => crate::actions::panel(app, ui),
(Group::History, 2) => crate::comps_ui::panel(app, ui),
(Group::History, 3) => crate::stablecraft::panel(app, ui),

// panel_docking.rs
("stablecraft", "StableCraft", Group::History),

// lib.rs
pub mod stablecraft;
```

Pour un groupe dédié, ajouter `Group::StableCraft` et les entrées `Panels`/`DockTabs`.

### État

```rust
#[derive(Clone, Serialize, Deserialize)]
pub struct StableCraftState {
    pub prompt: String,
    pub negative: String,
    pub profile: ProfileId,
    pub mode: EditMode,
    pub padding: u32,
    pub feather: u32,
    pub steps: u32,
    pub cfg: f32,
    pub seed: i64,
    pub batch: u32,
    pub output: OutputMode,
    pub previews: Vec<Preview>,
    pub status: String,
    pub progress: f32,
    pub last_error: Option<String>,
}
```

À placer dans `UiState` (persisté) et non dans le document.

### Interaction

- `Générer` : lit l'état, appelle `app.run("ai.edit", params)` ; si un job démarre,
  suivre `jobs.list` et mettre à jour la barre.
- `Annuler` : `app.run("ai.cancel", {})`.
- Vignette cliquée : `ai.applyResult {resultId}` ou remplace le calque de prévisualisation.
- Si pas de sélection : proposer « Générer dans tout le canvas » ou demander une
  sélection.
- Afficher le nom du profil, les fichiers manquants, et un bouton « Tester la connexion ».

### Design

Respecter `docs/ui-design.md` : tokens `Tokens::get(ctx)`, pas de couleurs en dur,
typo 11–12 px, panneau compact, scroll interne si nécessaire. Réutiliser les widgets
existants (boutons, sliders, combo) pour rester cohérent.

## 5. Préférences

Dans `crates/engine/src/prefs.rs`, étendre `Integrations` :

```rust
pub struct Integrations {
    pub allow_agent_control: bool,
    pub control_port: u32,
    pub comfy_endpoint: String,       // "http://127.0.0.1:12452"
    pub comfy_profile: String,        // "flux3Klein"
    pub comfy_allow_remote: bool,     // false
    pub comfy_context_padding: u32,   // 96
    pub comfy_feather: u32,           // 10
}
```

Validation :

- URL `http://` ou `https://`, sinon erreur.
- Si l'hôte n'est pas loopback et `comfy_allow_remote` est faux, refuser.
- Normaliser sans slash final.
- `prefs.set` doit accepter ces clés (mais `plugIns`/`colorSettings` restent
  interdits au control channel).

## 6. Tests

### Unitaires

- `workflow_flux3_edit_has_expected_nodes` : IDs, class_type, entrées.
- `crop_geometry` : bbox + padding + clamp + alignement 16, cas bords/très petit.
- `mask_from_selection` : couverture, feather, inversion.
- `result_resize_and_offset` : le PNG 1024×1024 est bien placé à `crop.x0/y0`.
- `endpoint_validation` : loopback autorisé, distant refusé sans opt-in.

### Intégration

- `#[ignore]` ou feature `comfy_test` : nécessite ComfyUI + modèles.
- Test réel : image de test + lasso synthétique, vérifier que le PNG sort et que le
  calque est créé avec un masque.
- Ne pas mettre d'images personnelles dans le repo ; utiliser des images de test
  publiques ou synthétiques.

### Non-régression

- `cargo test -p photocraft-comfy`
- `cargo test -p photocraft-engine --test panic_hunt -- --ignored` (nouvelle commande
  → pas de panic sur paramètres adverses)
- `cargo clippy -p photocraft-comfy -p photocraft-engine --all-targets -- -D warnings`
- `cargo xtask layers`
- `cargo xtask wasm` (le crate doit compiler en wasm, même s'il renvoie une erreur)
- `cargo xtask parity` si le menu ajoute une commande.

## 7. Build Windows

Prérequis :

- Rust stable MSVC (`rustup default stable-x86_64-pc-windows-msvc`) ;
- Visual Studio 2022 Build Tools + Windows SDK (déjà présents sur la machine) ;
- pas de dépendance native supplémentaire.

```powershell
rustup default stable-x86_64-pc-windows-msvc
cargo build --release -p photocraft
```

Le premier build est long (~20–40 min) et le dossier `target` peut atteindre ~10 Go.
Pour itérer : `cargo build -p photocraft-ui-egui --example snapshot` ou
`cargo run -p photocraft -- <image>`.

## 8. Découpage du travail

1. **Squelette** : crate `photocraft-comfy` + client HTTP + tests de workflow.
2. **Commande headless** : `ai.edit` sans UI, testée via `photocraft-cli` ou un
   exemple, sur une image et une sélection synthétique.
3. **Panneau** : UI minimale, connexion, génération, application.
4. **Intégration** : préférences, docking, raccourcis, messages d'erreur.
5. **Polish** : batch, vignettes, annulation, profils, docs.

Le prototype Python et les workflows JSON de `workflows/` servent de référence
d'exécution à chaque étape.
