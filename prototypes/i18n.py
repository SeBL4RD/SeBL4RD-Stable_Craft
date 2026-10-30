"""Tiny French/English UI translation layer.

French strings are used as source keys so the diff stays readable. Missing
entries fall back to the source string.
"""

from __future__ import annotations

LANG = "en"

EN: dict[str, str] = {
    # Header / status
    "Langue": "Language",
    "Le lasso de Stable.art, dans PhotoCraft, avec ComfyUI.": (
        "Stable.art's lasso, inside PhotoCraft, powered by ComfyUI."
    ),
    "par {author} · {repo}": "by {author} · {repo}",
    "PhotoCraft : connexion…": "PhotoCraft: connecting…",
    "ComfyUI : connexion…": "ComfyUI: connecting…",
    "Document : —": "Document: —",
    "Sélection : —": "Selection: —",
    "Modèles : vérification…": "Models: checking…",
    "Modèles : OK": "Models: OK",
    "Modèles : vérification impossible ({error})": "Models: verification failed ({error})",
    "Modèles manquants : {names} — cliquer pour gérer": (
        "Missing models: {names} — click to manage"
    ),
    "PhotoCraft : déconnecté": "PhotoCraft: disconnected",
    "PhotoCraft : connecté": "PhotoCraft: connected",
    "PhotoCraft : connecté (aucun document)": "PhotoCraft: connected (no document)",
    "PhotoCraft : {error}": "PhotoCraft: {error}",
    "ComfyUI : déconnecté": "ComfyUI: disconnected",
    "ComfyUI : {error}": "ComfyUI: {error}",
    "ComfyUI : {version} · {gpu} · {vram} Go libres": (
        "ComfyUI: {version} · {gpu} · {vram} GB free"
    ),
    "Document : {name} · {width}×{height} · {mode}/{depth} bits": (
        "Document: {name} · {width}×{height} · {mode}/{depth} bits"
    ),
    "Sélection : {width}×{height} à ({x},{y})": (
        "Selection: {width}×{height} at ({x},{y})"
    ),
    "Sélection : aucune — galerie disponible": (
        "Selection: none — gallery available"
    ),
    "Sélection : aucune — fais un lasso": "Selection: none — draw a lasso",
    "Document : aucun": "Document: none",
    "Mise à jour disponible : v{version} — ouvrir la page Releases": (
        "Update available: v{version} — open the Releases page"
    ),
    "Nœud Krea 2 absent — installer v{version} (cliquer ici)": (
        "Krea 2 node missing — install v{version} (click here)"
    ),
    "Nœud Krea 2 : v{installed} installé, v{latest} disponible — mettre à jour (cliquer ici)": (
        "Krea 2 node: v{installed} installed, v{latest} available — update (click here)"
    ),
    # Sections and static controls
    "PROMPT": "PROMPT",
    "IMAGE DE RÉFÉRENCE": "REFERENCE IMAGE",
    "PROFIL": "PROFILE",
    "RÉGLAGES": "SETTINGS",
    "GALERIE": "GALLERY",
    "APERÇU": "PREVIEW",
    "JOURNAL": "LOG",
    "MODE": "MODE",
    "Guide": "Guide",
    "Negative prompt": "Negative prompt",
    "Utiliser une image de référence": "Use a reference image",
    "Aucune image": "No image",
    "Clique ou dépose une image ici.": "Click or drop an image here.",
    "Retirer": "Remove",
    " — bientôt": " — coming soon",
    "Contexte (px)": "Context (px)",
    "Feather (px)": "Feather (px)",
    "Seed (-1 = aléatoire)": "Seed (-1 = random)",
    "Générer": "Generate",
    "Annuler": "Cancel",
    "Prêt.": "Ready.",
    "Aucune galerie": "No gallery",
    "Clique sur un calque StableCraft pour retrouver ses générations.": (
        "Click a StableCraft layer to open its generations."
    ),
    "Document": "Document",
    "Crop": "Crop",
    "Ouvrir": "Open",
    # Mode / profile
    "EDIT — selection": "EDIT — from selection",
    "T2I — texte to image": "T2I — texte to image",
    "T2I ignore la scène : le prompt génère une image au format du crop, puis PhotoCraft la masque avec la sélection. Utilise une sélection rectangulaire pour un résultat propre.": (
        "T2I ignores the scene: the prompt generates an image at the crop size, "
        "then PhotoCraft masks it with the selection. A rectangular selection "
        "gives cleaner results."
    ),
    "EDIT envoie le crop de la scène au modèle et conserve la scène d'origine, même après un passage en T2I.": (
        "EDIT sends the scene crop to the model and keeps the original scene, "
        "even after switching to T2I and back."
    ),
    " · recommandé": " · recommended",
    " · expérimental": " · experimental",
    " · non testé": " · untested",
    " · bientôt disponible": " · coming soon",
    "Quantification": "Quantization",
    "Personnalisé : {filename}": "Custom: {filename}",
    "Quantification : {filename}": "Quantization: {filename}",
    "{steps} steps · CFG {cfg}": "{steps} steps · CFG {cfg}",
    " · {weights} Go de poids": " · {weights} GB of weights",
    " · ~{vram} Go VRAM": " · ~{vram} GB VRAM",
    "Gérer les modèles": "Manage models",
    "Gérer": "Manage",
    "Fichiers du profil": "Profile files",
    "Appliquer": "Apply",
    "Parcourir…": "Browse…",
    "Modèle sélectionné : {filename}": "Selected model: {filename}",
    "ComfyUI hors ligne : Parcourir… permet de choisir un fichier local.": (
        "ComfyUI offline: Browse… lets you pick a local file."
    ),
    "Régénérer": "Regenerate",
    "Cette combinaison existe déjà (#{index}). Mets le seed à -1 ou change le prompt.": (
        "This combination already exists (#{index}). Set seed to -1 or change the prompt."
    ),
    "Vérifie les réglages (seed, steps, CFG…).": "Check the settings (seed, steps, CFG…).",
    "Fais un lasso, ou sélectionne un calque StableCraft pour régénérer.": (
        "Make a lasso selection, or select a StableCraft layer to regenerate."
    ),
    "Modèles manquants — Générer ouvrira le gestionnaire.": (
        "Missing models — Generate will open the manager."
    ),
    "Modèles manquants — le bouton ouvre le gestionnaire.": (
        "Missing models — the button opens the manager."
    ),
    # Reference
    "Disponible en mode EDIT uniquement.": "Available in EDIT mode only.",
    "1.0 = édition complète. En dessous, le résultat conserve davantage l'image source ; 0.8–1.0 recommandé avec FLUX.2 Klein.": (
        "1.0 = full edit. Below that, the result keeps more of the source image; "
        "0.8–1.0 recommended with FLUX.2 Klein."
    ),
    "Fixé à 1.0 : ce modèle part d'un latent vide ; un denoise partiel produirait des artefacts.": (
        "Fixed at 1.0: this model samples from an empty latent; partial denoise "
        "would produce artifacts."
    ),
    "Disponible sur Krea 2, FLUX.2 Klein 9B, FLUX.3 Klein et Qwen Image 2.1.": (
        "Available for Krea 2, FLUX.2 Klein 9B, FLUX.3 Klein and Qwen Image 2.1."
    ),
    "Krea 2 utilise la référence en EDIT ; en T2I, passe en EDIT pour une génération guidée par l'image.": (
        "Krea 2 uses references in EDIT; switch to EDIT for image-guided generation."
    ),
    "La référence guide la génération T2I.": (
        "The reference guides the T2I generation."
    ),
    "Image de référence pour le T2I. Décris ce que tu veux en reprendre.": (
        "T2I reference image. Describe what you want to take from it."
    ),
    "Image 2 = référence. Décris dans le prompt ce que tu veux en reprendre.": (
        "Image 2 = reference. Describe in the prompt what you want to take from it."
    ),
    "Image de référence": "Reference image",
    "Choisir une image de référence": "Choose a reference image",
    "Impossible de préparer l'image.\n\n{details}": "Could not prepare the image.\n\n{details}",
    "Image de référence retirée.": "Reference image removed.",
    "Référence : {error}": "Reference: {error}",
    "Référence : aperçu indisponible ({error})": "Reference: preview unavailable ({error})",
    "Image de référence : {path}": "Reference image: {path}",
    "Drag & drop Windows activé.": "Windows drag & drop enabled.",
    "Drag & drop indisponible : {error}": "Drag & drop unavailable: {error}",
    "Fichier ignoré (format image attendu) : {name}": "File ignored (image format expected): {name}",
    "Session {session} : {error}": "Session {session}: {error}",
    "Annulation demandée…": "Cancellation requested…",
    "Config : {path}": "Config: {path}",
    "Clique ou dépose": "Click or drop",
    # LoRA
    "Activer les LoRA": "Enable LoRA",
    "Gérer les LoRA…": "Manage LoRA…",
    "LoRA — {profile}": "LoRA — {profile}",
    "LoRA": "LoRA",
    "LoRA Manager": "LoRA Manager",
    "Sélectionner un LoRA": "Select a LoRA",
    "Détails": "Details",
    "Grille": "Grid",
    "Charger plus": "Load more",
    "Utiliser ce LoRA": "Use this LoRA",
    "Vérification des LoRA…": "Checking LoRA…",
    "{count}/{max} LoRA": "{count}/{max} LoRA",
    "Introuvable dans ComfyUI.": "Not visible to ComfyUI.",
    "Architecture {arch} — incompatible avec {profile}.": "Architecture {arch} — incompatible with {profile}.",
    "Contient un text encoder — seule la partie modèle est appliquée.": "Contains a text encoder — only the model part is applied.",
    "Maximum {max} LoRA par profil.": "Maximum {max} LoRA per profile.",
    "Chargement de la liste…": "Loading list…",
    "Chargement…": "Loading…",
    "Aucun LoRA trouvé.": "No LoRA found.",
    "Nom": "Name",
    "Dossier": "Folder",
    "incompatible": "incompatible",
    "text encoder ignoré": "text encoder ignored",
    "déjà utilisé": "already used",
    "Chargement des miniatures… {done}/{total}": "Loading thumbnails… {done}/{total}",
    "Sélectionne un LoRA.": "Select a LoRA.",
    "Ce LoRA est déjà dans la liste.": "This LoRA is already in the list.",
    "Ajouter un LoRA": "Add a LoRA",
    "Ouvrir la page LoRA Manager": "Open the LoRA Manager page",
    "Actualiser": "Refresh",
    "Choisir…": "Choose…",
    "ComfyUI/LoRA Manager indisponible : {error}": "ComfyUI/LoRA Manager unavailable: {error}",
    "LoRA Manager indisponible — liste ComfyUI, sans miniatures.": (
        "LoRA Manager unavailable — ComfyUI list, without thumbnails."
    ),
    "Erreur LoRA : {error}": "LoRA error: {error}",
    "Aperçu": "Preview",
    "Miniatures indisponibles : {error}": "Thumbnails unavailable: {error}",
    "Les LoRA sont lus depuis ComfyUI. Aucun fichier n'est copié : utilise la page LoRA Manager pour ajouter ou organiser tes fichiers.": (
        "LoRA are read from ComfyUI. Nothing is copied: use the LoRA Manager page "
        "to add or organize your files."
    ),
    "Force": "Strength",
    "Liste ComfyUI chargée : {count} LoRA visibles. La génération validera chaque nom.": (
        "ComfyUI list loaded: {count} visible LoRA. Generation will validate each name."
    ),
    "Profil actuel : {profile}": "Current profile: {profile}",
    "La liste et les miniatures viennent de ComfyUI LoRA Manager. Aucun fichier n'est copié.": (
        "The list and thumbnails come from ComfyUI LoRA Manager. Nothing is copied."
    ),
    "Rechercher": "Search",
    "Page {page}/{pages} · {total} LoRA": "Page {page}/{pages} · {total} LoRA",
    "Aucun LoRA sélectionné. Clique sur « Ajouter un LoRA » pour en choisir un.": (
        "No LoRA selected. Click “Add a LoRA” to choose one."
    ),
    "LoRA désactivés ({count} configurés)": "LoRA disabled ({count} configured)",
    "LoRA activés.": "LoRA enabled.",
    "LoRA désactivés.": "LoRA disabled.",
    "Aucun LoRA — clique sur Gérer les LoRA…": "No LoRA — click Manage LoRA…",
    "LoRA : {error}": "LoRA: {error}",
    "Aucun LoRA actif — vérifie les cases dans Gérer…": (
        "No active LoRA — check the boxes in Manage…"
    ),
    "{count} LoRA actifs · {details}": "{count} active LoRA · {details}",
    "1 LoRA actif · {details}": "1 active LoRA · {details}",
    "⚠ {label} semble destiné à {arch}, pas à {profile}.": (
        "⚠ {label} looks intended for {arch}, not {profile}."
    ),
    "LoRA introuvable dans ComfyUI : {names}": "LoRA not visible to ComfyUI: {names}",
    " et {count} autre(s)": " and {count} more",
    # Prompt guide
    "Guide de prompt": "Prompt guide",
    "Guide de prompt — StableCraft": "Prompt guide — StableCraft",
    "En mode EDIT, StableCraft envoie au modèle le crop de ta scène (sélection + contexte), puis applique le résultat dans le lasso. En mode T2I, aucune scène n'est envoyée : le prompt décrit l'image à générer, puis PhotoCraft la masque avec la sélection.": (
        "In EDIT mode, StableCraft sends the scene crop (selection + context) to "
        "the model, then applies the result inside the lasso. In T2I mode, no "
        "scene is sent: the prompt describes the image to generate, then "
        "PhotoCraft masks it with the selection."
    ),
    "0. EDIT ou T2I ?": "0. EDIT or T2I?",
    "• EDIT : modifier une image existante. Décris le résultat final dans la scène.": (
        "• EDIT: modify an existing image. Describe the final result in the scene."
    ),
    "• T2I : créer une image sans image source. Décris la scène complète.": (
        "• T2I: create an image without a source image. Describe the full scene."
    ),
    "• En T2I, utilise une sélection rectangulaire : l'image est générée au format du crop puis masquée. Le lasso donne une forme irrégulière au masque.": (
        "• In T2I, use a rectangular selection: the image is generated at the "
        "crop size and then masked. A lasso gives the mask an irregular shape."
    ),
    "1. La bonne attitude, sans référence": "1. The right approach, without a reference",
    "• Écris en anglais : ces modèles répondent mieux aux prompts anglais.": (
        "• Write in English: these models respond better to English prompts."
    ),
    "• Décris l'état final : couleur, matière, objet, position.": (
        "• Describe the final state: color, material, object, position."
    ),
    "• Dis explicitement ce qui doit rester inchangé : pose, visage, peau, fond, lumière.": (
        "• Explicitly state what must stay unchanged: pose, face, skin, background, light."
    ),
    "• Sois concret plutôt que poétique. Évite les négations : à CFG 1, le negative prompt agit peu.": (
        "• Be concrete rather than poetic. Avoid negations: at CFG 1 the negative "
        "prompt has little effect."
    ),
    "• Sélectionne l'objet entier, avec un peu de contexte autour.": (
        "• Select the whole object, with a little context around it."
    ),
    "2. Avec une image de référence": "2. With a reference image",
    "Image 1 = la scène, c'est-à-dire ton image PhotoCraft.": (
        "Image 1 = the scene, i.e. your PhotoCraft image."
    ),
    "Image 2 = l'image de référence que tu as ajoutée.": (
        "Image 2 = the reference image you added."
    ),
    "Qwen Image 2.1 les appelle <image1> et <image2> dans son prompt.": (
        "Qwen Image 2.1 calls them <image1> and <image2> in its prompt."
    ),
    "En T2I, FLUX.2 Klein 9B, FLUX.3 Klein et Qwen Image 2.1 utilisent la référence comme image 1 pour guider une nouvelle image. Krea 2 utilise la référence en EDIT.": (
        "In T2I, FLUX.2 Klein 9B, FLUX.3 Klein and Qwen Image 2.1 use the "
        "reference as image 1 to guide a new image. Krea 2 uses references in EDIT."
    ),
    "La référence n'est active que si la case est cochée et qu'une image est chargée. Elle n'est jamais collée : elle sert d'inspiration au modèle.": (
        "The reference is active only when the box is checked and an image is "
        "loaded. It is never pasted: it inspires the model."
    ),
    "Dis ce que tu prends de l'image 2, et où tu l'appliques dans l'image 1.": (
        "Say what you take from image 2, and where you apply it in image 1."
    ),
    "3. Ce qui marche le mieux": "3. What works best",
    "• Un objet seul, détouré ou sur un fond simple, est plus facile à transférer.": (
        "• A single object, cut out or on a simple background, is easier to transfer."
    ),
    "• Une référence avec beaucoup de fond peut être confondue avec la scène.": (
        "• A reference with a lot of background can be confused with the scene."
    ),
    "• Pour un vêtement, demande la couleur/matière ; pour un accessoire, décris sa position.": (
        "• For clothing, ask for color/material; for an accessory, describe its position."
    ),
    "• Krea 2, FLUX.2 Klein 9B, FLUX.3 Klein et Qwen Image 2.1 acceptent la référence.": (
        "• Krea 2, FLUX.2 Klein 9B, FLUX.3 Klein and Qwen Image 2.1 accept references."
    ),
    "• Si le résultat copie trop la référence, précise « only » / « keep unchanged » dans le prompt.": (
        "• If the result copies the reference too much, add “only” / “keep unchanged” "
        "to the prompt."
    ),
    "4. Rappel": "4. Reminder",
    "La référence est propre au calque StableCraft courant. Si tu changes de calque, l'UI recharge la référence de ce calque ; une nouvelle sélection repart sans référence.": (
        "The reference belongs to the current StableCraft layer. When you change "
        "layers, the UI reloads that layer's reference; a new selection starts "
        "without one."
    ),
    # Gallery / actions
    "Galerie — StableCraft [{session}] · {count} génération(s)": (
        "Gallery — StableCraft [{session}] · {count} generation(s)"
    ),
    "Aucune génération dans cette session.": "No generation in this session.",
    "Clique sur une vignette pour appliquer cette génération.": (
        "Click a thumbnail to apply that generation."
    ),
    "Cette combinaison existe déjà dans la galerie (#{index}).\n\nMets le seed à -1 ou change le prompt pour régénérer.": (
        "This combination already exists in the gallery (#{index}).\n\n"
        "Set seed to -1 or change the prompt to regenerate."
    ),
    "Bientôt": "Coming soon",
    "Ce profil sera ajouté plus tard.": "This profile will be added later.",
    "Sélection vide": "Empty selection",
    "Fais un lasso autour de la zone à modifier, ou sélectionne un calque StableCraft pour régénérer avec sa sélection d'origine.": (
        "Draw a lasso around the area to edit, or select a StableCraft layer to "
        "regenerate with its original selection."
    ),
    "Déjà généré": "Already generated",
    "Référence vide": "Empty reference",
    "Ajoute une image de référence ou décoche la case « Utiliser une image de référence ».": (
        "Add a reference image or uncheck “Use a reference image”."
    ),
    "Prompt vide": "Empty prompt",
    "Décris l'image à générer.": "Describe the image to generate.",
    "Écris ce que tu veux changer.": "Describe what you want to change.",
    "Python ComfyUI introuvable": "ComfyUI Python not found",
    "Renseigne [comfyui] python dans config.toml avec le python_embeded de ComfyUI.": (
        "Set [comfyui] python in config.toml to ComfyUI's python_embeded path."
    ),
    "Bridge introuvable": "Bridge not found",
    "Lancement impossible": "Could not start",
    "Régénération en cours…": "Regenerating…",
    "Génération en cours…": "Generating…",
    "Application de la génération #{index}…": "Applying generation #{index}…",
    "Terminé — calque StableCraft prêt.": "Done — StableCraft layer ready.",
    "Erreur — voir le journal.": "Error — see the log.",
    "Annulation…": "Cancelling…",
    "Processus terminé (code {code}).": "Process finished (code {code}).",
    "Aucun aperçu.\nFais un lasso, écris un prompt, puis clique Générer.": (
        "No preview.\nMake a lasso selection, write a prompt, then click Generate."
    ),
    "Aperçu indisponible : {error}": "Preview unavailable: {error}",
    # Model manager
    "Modèles — {profile}": "Models — {profile}",
    "Nœud Krea 2 : vérification…": "Krea 2 node: checking…",
    "Installer / mettre à jour": "Install / update",
    "Vérifier": "Check",
    "Dossier des modèles": "Models folder",
    "Redémarrer ComfyUI": "Restart ComfyUI",
    "Démarrer ComfyUI": "Start ComfyUI",
    "Fermer": "Close",
    "Vérification impossible : {error}. ComfyUI doit être démarré.": (
        "Verification failed: {error}. ComfyUI must be running."
    ),
    "Tous les fichiers requis sont visibles par ComfyUI.": (
        "All required files are visible to ComfyUI."
    ),
    "{count} fichier(s) manquant(s). Tu peux localiser un fichier existant ou le télécharger avec ton accord.": (
        "{count} missing file(s). Locate an existing file or download it with your consent."
    ),
    "Localiser": "Locate",
    "Télécharger": "Download",
    "Fichier local uniquement": "Local file only",
    "Voir le nœud Krea 2 ci-dessus ou mettre à jour ComfyUI.": (
        "See the Krea 2 node above, or update ComfyUI."
    ),
    "Localiser {label}": "Locate {label}",
    "Modèles": "Models",
    "Tous les fichiers": "All files",
    "Doublon détecté": "Duplicate found",
    "Le fichier est déjà rangé ici :\n{destination}\n\nLa copie déjà rangée va être utilisée. Supprimer le doublon :\n{source} ?": (
        "The file is already stored here:\n{destination}\n\n"
        "The stored copy will be used. Delete the duplicate:\n{source}?"
    ),
    "Suppression impossible": "Could not delete",
    "{destination} existe déjà avec une autre taille.\n\nLe remplacer par ce fichier (déplacement, pas copie) ?": (
        "{destination} already exists with a different size.\n\n"
        "Replace it with this file (move, not copy)?"
    ),
    "Déplacer le modèle ?": "Move the model?",
    "Ce fichier est déjà dans le dossier des modèles mais pas dans le sous-dossier attendu.\n\nLe déplacer vers :\n{destination}\n\nAucune copie ne sera créée.": (
        "This file is already in the models folder but not in the expected "
        "subfolder.\n\nMove it to:\n{destination}\n\nNo copy will be created."
    ),
    "Déplacement de {filename}…": "Moving {filename}…",
    "Déplacé : {filename}": "Moved: {filename}",
    "{filename} est sélectionné. Redémarre ComfyUI pour qu'il le voie.": (
        "{filename} is selected. Restart ComfyUI so it can see it."
    ),
    "Nom libre : choisis ton fichier même s'il ne porte pas le nom attendu.": (
        "Free naming: pick your file even if it does not match the expected name."
    ),
    "Ce fichier est hors du dossier des modèles.\n\nLe copier dans :\n{destination}\n\nPuis ajouter le dossier aux chemins ComfyUI ?": (
        "This file is outside the models folder.\n\nCopy it to:\n{destination}\n\n"
        "Then add the folder to ComfyUI's model paths?"
    ),
    "Fichier introuvable": "File not found",
    "GGUF sans métadonnée": "GGUF without metadata",
    "Ce GGUF n'annonce pas general.architecture = qwen_image. ComfyUI ne pourra probablement pas le charger pour Qwen Image 2.1.\n\nLes GGUF Unsloth sont concernés : utilise la version Abiray ou un safetensors officiel.\n\nContinuer quand même ?": (
        "This GGUF does not declare general.architecture = qwen_image. "
        "ComfyUI will probably not load it for Qwen Image 2.1.\n\n"
        "This affects Unsloth GGUFs: use the Abiray version or the official "
        "safetensors file.\n\nContinue anyway?"
    ),
    "GGUF incompatible": "Incompatible GGUF",
    "Ce GGUF annonce l'architecture « {architecture} ». Qwen Image 2.1 attend « qwen_image ». Choisis le bon fichier.": (
        "This GGUF declares architecture “{architecture}”. Qwen Image 2.1 "
        "expects “qwen_image”. Choose the correct file."
    ),
    "Dossier de modèle incorrect": "Incorrect model folder",
    "Ce fichier est dans le dossier de ComfyUI, mais pas dans un sous-dossier utilisable pour {kind}.\n\nDéplace-le dans : {folders}\n\npuis relance Localiser.": (
        "This file is inside ComfyUI's models folder, but not in a subfolder "
        "usable for {kind}.\n\nMove it to: {folders}\n\nthen click Locate again."
    ),
    "ComfyUI injoignable": "ComfyUI unreachable",
    "Démarre ComfyUI avant de localiser un modèle, pour vérifier qu'il est bien visible.": (
        "Start ComfyUI before locating a model, so visibility can be verified."
    ),
    "{filename} est déjà visible par ComfyUI.": "{filename} is already visible to ComfyUI.",
    "Copier le modèle ?": "Copy the model?",
    "Ce fichier n'est pas visible par ComfyUI.\n\nLe copier dans :\n{destination}\n\nPuis ajouter le dossier aux chemins ComfyUI ?": (
        "This file is not visible to ComfyUI.\n\nCopy it to:\n{destination}\n\n"
        "Then add the folder to ComfyUI's model paths?"
    ),
    "Copie de {filename}…": "Copying {filename}…",
    "Copié : {filename}": "Copied: {filename}",
    "Téléchargement indisponible": "Download unavailable",
    "Téléchargements désactivés": "Downloads disabled",
    "Les téléchargements sont désactivés dans config.toml ([models] allow_downloads = false).": (
        "Downloads are disabled in config.toml ([models] allow_downloads = false)."
    ),
    "Aucune URL publique pour ce fichier.": "No public URL for this file.",
    "Télécharger le modèle ?": "Download the model?",
    "Télécharger {filename} ({size}) ?\n\nSource : {url}\n\nLe téléchargement ne démarre qu'après cette confirmation.": (
        "Download {filename} ({size})?\n\nSource: {url}\n\n"
        "The download starts only after this confirmation."
    ),
    "Fichier déjà présent": "File already present",
    "{filename} est déjà présent dans le dossier. L'utiliser sans le retélécharger ?": (
        "{filename} already exists in the folder. Use it without downloading again?"
    ),
    "Chemins ComfyUI": "ComfyUI paths",
    "Remplacer le fichier ?": "Replace the file?",
    "{filename} existe déjà. Le remplacer ?": "{filename} already exists. Replace it?",
    "Téléchargé : {filename}": "Downloaded: {filename}",
    "Téléchargement de {filename}…": "Downloading {filename}…",
    "Nœud Krea 2": "Krea 2 node",
    "Impossible de contacter GitHub pour trouver la dernière version.": (
        "Could not contact GitHub to find the latest version."
    ),
    "Mettre à jour": "Update",
    "Installer": "Install",
    "{action} comfyui-krea2edit {version} ?\n\nLe nœud sera installé dans ComfyUI/custom_nodes, puis ComfyUI devra être redémarré.": (
        "{action} comfyui-krea2edit {version}?\n\n"
        "The node will be installed in ComfyUI/custom_nodes, then ComfyUI must be restarted."
    ),
    "Nœud Krea 2 v{version} installé.": "Krea 2 node v{version} installed.",
    "Installation du nœud Krea 2…": "Installing the Krea 2 node…",
    "Nœud Krea 2 : absent. Version disponible : v{version}.": (
        "Krea 2 node: missing. Available version: v{version}."
    ),
    "Nœud Krea 2 : v{installed} installé, v{latest} disponible.": (
        "Krea 2 node: v{installed} installed, v{latest} available."
    ),
    "Nœud Krea 2 : v{version} installé.": "Krea 2 node: v{version} installed.",
    "Page Releases": "Releases page",
    "ComfyUI doit être redémarré pour voir les nouveaux fichiers ou nœuds.": (
        "ComfyUI must be restarted to see the new files or nodes."
    ),
    "Démarrer ComfyUI ?": "Start ComfyUI?",
    "Redémarrer ComfyUI ? Une génération en cours sera interrompue.": (
        "Restart ComfyUI? A running generation will be interrupted."
    ),
    "Les fichiers sont prêts. Redémarrer ComfyUI maintenant ? Une génération en cours sera interrompue.": (
        "Files are ready. Restart ComfyUI now? A running generation will be interrupted."
    ),
    "Les fichiers sont prêts. Démarrer ComfyUI maintenant ?": (
        "Files are ready. Start ComfyUI now?"
    ),
    "Redémarre ComfyUI plus tard pour voir les nouveaux fichiers.": (
        "Restart ComfyUI later to see the new files."
    ),
    "ComfyUI n'a pas redémarré dans les 4 minutes.": (
        "ComfyUI did not restart within 4 minutes."
    ),
    "Le redémarrage automatique n'est disponible que pour un ComfyUI local.": (
        "Automatic restart is only available for a local ComfyUI."
    ),
    "ComfyUI est prêt.": "ComfyUI is ready.",
    "Redémarrage de ComfyUI…": "Restarting ComfyUI…",
    "{done} / {total}": "{done} / {total}",
    "Erreur": "Error",
    "Vérification des modèles…": "Checking models…",
    "Toujours en cours. Vérifie que ComfyUI tourne, puis clique Vérifier.": (
        "Still checking. Make sure ComfyUI is running, then click Check."
    ),
}


def set_language(language: str | None) -> None:
    global LANG
    value = str(language or "en").lower()
    LANG = "fr" if value.startswith("fr") else "en"


def current_language() -> str:
    return LANG


def profile_text(profile: dict[str, object], field: str) -> str:
    if LANG == "fr":
        return str(profile.get(field, "") or "")
    return str(profile.get(f"{field}_en", profile.get(field, "")) or "")


def tr(text: str, **values: object) -> str:
    template = text if LANG == "fr" else EN.get(text, text)
    if not values:
        return template
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return template
