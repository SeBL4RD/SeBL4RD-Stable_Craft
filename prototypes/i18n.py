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
    "par {author}": "by {author}",
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
    "ComfyUI": "ComfyUI",
    "Page GitHub": "GitHub page",
    "Installer {name} ?": "Install {name}?",
    "Installer le nœud ComfyUI {name} depuis GitHub ?\n\nSes dépendances Python seront installées dans l'environnement de ComfyUI, puis un redémarrage sera nécessaire.": (
        "Install the ComfyUI node {name} from GitHub?\n\nIts Python dependencies "
        "will be installed in ComfyUI's environment, then a restart will be required."
    ),
    "Nœud {name} installé. Redémarre ComfyUI.": (
        "Node {name} installed. Restart ComfyUI."
    ),
    "Installation de {name}…": "Installing {name}…",
    "ComfyUI externe": "External ComfyUI",
    "ComfyUI est géré en externe. Redémarre-le depuis Desktop ou son propre lanceur.": (
        "ComfyUI is managed externally. Restart it from Desktop or its own launcher."
    ),
    "Duplication de session impossible : {error}": (
        "Could not separate the duplicated session: {error}"
    ),
    "Calque dupliqué séparé : {old} → {new}": (
        "Duplicated layer separated: {old} → {new}"
    ),
    "ComfyUI est géré en externe. Redémarre-le depuis Desktop ou son propre lanceur pour voir les nouveaux fichiers ou nœuds.": (
        "ComfyUI is managed externally. Restart it from Desktop or its own launcher "
        "to see the new files or nodes."
    ),
    "Python du venv StableCraft introuvable. Crée-le avec install.sh ou installe requests et Pillow.": (
        "StableCraft venv Python not found. Create it with install.sh or install "
        "requests and Pillow."
    ),
    "Fichiers du profil": "Profile files",
    "Appliquer": "Apply",
    "Parcourir…": "Browse…",
    "Choisir un fichier…": "Choose a file…",
    "Modèle sélectionné : {filename}": "Selected model: {filename}",
    "ComfyUI hors ligne : Parcourir… permet de choisir un fichier local.": (
        "ComfyUI offline: Browse… lets you pick a local file."
    ),
    "ComfyUI hors ligne : Choisir un fichier… permet de sélectionner un fichier local.": (
        "ComfyUI offline: Choose a file… lets you select a local file."
    ),
    "{count} fichier(s) téléchargé(s). Redémarre ComfyUI pour qu'il les voie.": (
        "{count} file(s) downloaded. Restart ComfyUI so it can see them."
    ),
    "{label} · {filename} — téléchargé, redémarrage requis": (
        "{label} · {filename} — downloaded, restart required"
    ),
    "Redémarre ComfyUI pour que ce fichier devienne visible.": (
        "Restart ComfyUI so this file becomes visible."
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
    "Flouter les LoRA NSFW": "Blur NSFW LoRA",
    "Flouter NSFW": "Blur NSFW",
    "MOSS-Image utilise la référence en EDIT ; en T2I, le modèle ne prend pas d'image.": (
        "MOSS-Image uses the reference in EDIT; in T2I the model takes no image."
    ),
    "Monter": "Up",
    "Dossiers": "Folders",
    "Racine": "Root",
    "Recherche dans tous les dossiers…": "Searching all folders…",
    "Aucun LoRA à ce niveau — ouvre un dossier.": (
        "No LoRA at this level — open a folder."
    ),
    "Détails": "Details",
    "Grille": "Grid",
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
    "Dossiers et miniatures viennent de ComfyUI LoRA Manager. Aucun fichier n'est copié.": (
        "Folders and thumbnails come from ComfyUI LoRA Manager. Nothing is copied."
    ),
    "Rechercher": "Search",
    "{total} LoRA": "{total} LoRA",
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
    "En T2I, FLUX.2 Klein 9B, FLUX.3 Klein, Krea 2 et Qwen Image 2.1 utilisent la référence pour guider une nouvelle image.": (
        "In T2I, FLUX.2 Klein 9B, FLUX.3 Klein, Krea 2 and Qwen Image 2.1 use the "
        "reference to guide a new image."
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
    "Galerie — StableCraft [{session}]": "Gallery — StableCraft [{session}]",
    "Copier le seed": "Copy the seed",
    "Remet le seed en random": "Reset the seed to random",
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
    "{speed}/s": "{speed}/s",
    "reste {time}": "{time} left",
    "Annulation…": "Cancelling…",
    "Téléchargement annulé.": "Download cancelled.",
    "Nœud natif de ComfyUI 0.45+ ; mets ComfyUI à jour.": (
        "Built into ComfyUI 0.45+; update ComfyUI."
    ),
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
    # Gallery / batch / progress / clipboard
    "Au premier plan": "Always on top",
    "Coller": "Paste",
    "Presse-papiers": "Clipboard",
    "Impossible de lire le presse-papiers.\n\n{details}": (
        "Could not read the clipboard.\n\n{details}"
    ),
    "Le presse-papiers ne contient pas d'image.": (
        "The clipboard does not contain an image."
    ),
    "Favori : {error}": "Favorite: {error}",
    "Supprimer la génération": "Delete generation",
    "Supprimer la génération #{index} ? Le fichier sera effacé du disque.": (
        "Delete generation #{index}? The file will be removed from disk."
    ),
    "Suppression : {error}": "Deletion: {error}",
    "Suppression impossible": "Deletion failed",
    "Génération #{index} supprimée.": "Generation #{index} deleted.",
    "Clique sur une vignette pour appliquer.": "Click a thumbnail to apply.",
    "Image {index}/{count}": "Image {index}/{count}",
    "Cellule {index}/{count}": "Cell {index}/{count}",
    "Progression indisponible…": "Progress unavailable…",
    "{count} images · seeds {seeds}": "{count} images · seeds {seeds}",
    "aléatoires": "random",
    # XYZ tool
    "XYZ Plot": "XYZ Plot",
    "StableCraft — XYZ Plot": "StableCraft — XYZ Plot",
    "Guide XYZ Plot": "XYZ Plot guide",
    "Seed XYZ": "XYZ seed",
    "Aléatoire": "Random",
    "Même seed fixe pour toutes les cellules.": (
        "Same fixed seed for every cell."
    ),
    "Aucun": "None",
    "Lancer": "Run",
    "Ouvrir le dossier": "Open folder",
    "Ouvrir l'image": "Open image",
    "Nouveau plot": "New plot",
    "Le résultat apparaîtra ici.": "The result will appear here.",
    "{profile} · {mode} · {selection}\nPrompt et réglages repris de la fenêtre principale.": (
        "{profile} · {mode} · {selection}\n"
        "Prompt and settings taken from the main window."
    ),
    "sélection actuelle": "current selection",
    "session sélectionnée": "selected session",
    "Axe désactivé.": "Axis disabled.",
    "Ex. euler, dpmpp_2m": "E.g. euler, dpmpp_2m",
    "Ex. simple, karras": "E.g. simple, karras",
    "Ex. 8, 12, 16, 20 — plages 5-15(+2) ou 5-15[5]": (
        "E.g. 8, 12, 16, 20 — ranges 5-15(+2) or 5-15[5]"
    ),
    "Ex. 0.4, 0.6, 0.8, 1.0": "E.g. 0.4, 0.6, 0.8, 1.0",
    "Forces : 0.25, 0.5, 0.75, 1.0": "Strengths: 0.25, 0.5, 0.75, 1.0",
    "Ex. 1.0, 2.0, 3.5": "E.g. 1.0, 2.0, 3.5",
    "1re valeur = texte recherché. Ex. chat, chien, loup": (
        "1st value = search text. E.g. cat, dog, wolf"
    ),
    "1re valeur = texte recherché (aussi 1er remplacement). Ex. chat, chien, loup": (
        "1st value = search text (also the 1st replacement). "
        "E.g. cat, dog, wolf"
    ),
    "1re valeur = texte recherché, dans le negative prompt. Ex. flou, net": (
        "1st value = search text, in the negative prompt. E.g. blurry, sharp"
    ),
    "Aucun LoRA visible dans ComfyUI.": "No LoRA visible in ComfyUI.",
    "Axe {axis} : aucune valeur.": "Axis {axis}: no value.",
    "Axe {axis} : Steps doit rester entre 1 et 100.": (
        "Axis {axis}: Steps must stay between 1 and 100."
    ),
    "Axe {axis} : Denoise doit rester entre 0 et 1.": (
        "Axis {axis}: Denoise must stay between 0 and 1."
    ),
    "L'axe Denoise n'est disponible qu'en EDIT avec FLUX.2 Klein 9B.": (
        "The Denoise axis is only available in EDIT with FLUX.2 Klein 9B."
    ),
    "Axe {axis} : CFG doit rester entre 0 et 20.": (
        "Axis {axis}: CFG must stay between 0 and 20."
    ),
    "Axe {axis} : choisis un LoRA.": "Axis {axis}: choose a LoRA.",
    "Choisir un LoRA…": "Choose a LoRA…",
    "Choisis un LoRA avec le bouton, puis les forces.": (
        "Choose a LoRA with the button, then the strengths."
    ),
    "Axe {axis} : force LoRA entre 0 et 1.": (
        "Axis {axis}: LoRA strength must stay between 0 and 1."
    ),
    "Axe {axis} : sampler inconnu {value}.": (
        "Axis {axis}: unknown sampler {value}."
    ),
    "Axe {axis} : scheduler inconnu {value}.": (
        "Axis {axis}: unknown scheduler {value}."
    ),
    "Axe {axis} : texte recherché vide.": "Axis {axis}: empty search text.",
    "Axe {axis} : « {search} » absent du negative prompt.": (
        "Axis {axis}: “{search}” is not in the negative prompt."
    ),
    "Axe {axis} : « {search} » absent du prompt et du negative prompt.": (
        "Axis {axis}: “{search}” is not in the prompt or the negative prompt."
    ),
    "Choisis au moins un axe.": "Choose at least one axis.",
    "— {error}": "— {error}",
    "{count} image(s) à générer": "{count} image(s) to generate",
    " — attention, cela peut être long.": " — this may take a while.",
    "ComfyUI déconnecté.": "ComfyUI disconnected.",
    "Une génération est déjà en cours.": "A generation is already running.",
    "Installe les modèles manquants avant de lancer.": (
        "Install the missing models before running."
    ),
    "Trop d'images : maximum 100 cellules pour un plot.": (
        "Too many images: maximum 100 cells per plot."
    ),
    "Le seed du XYZ plot doit être un entier positif fixe.": (
        "The XYZ seed must be a fixed positive integer."
    ),
    "Vérifie les réglages dans la fenêtre principale.": (
        "Check the settings in the main window."
    ),
    "Préparation…": "Preparing…",
    "Génération en cours…": "Generating…",
    "Application dans PhotoCraft…": "Applying in PhotoCraft…",
    "Annulé.": "Cancelled.",
    "Annulé — les cellules déjà générées sont conservées.": (
        "Cancelled — already generated cells are kept."
    ),
    "Erreur.": "Error.",
    "Terminé.": "Done.",
    "{count} cellule(s) générée(s).": "{count} cell(s) generated.",
    "Les cellules déjà générées sont conservées.": (
        "Already generated cells are kept."
    ),
    "Aucun aperçu.": "No preview.",
    "Un XYZ Plot est en cours. L'annuler et fermer ?": (
        "An XYZ Plot is running. Cancel it and close?"
    ),
    "XYZ Plot en cours…": "XYZ Plot running…",
    "XYZ LoRA : {error}": "XYZ LoRA: {error}",
    "PhotoCraft et ComfyUI doivent être connectés.": (
        "PhotoCraft and ComfyUI must be connected."
    ),
    "Écris le prompt à comparer dans la fenêtre principale.": (
        "Write the prompt to compare in the main window."
    ),
    "Fais un lasso, ou sélectionne un calque StableCraft pour utiliser sa sélection d'origine.": (
        "Draw a lasso, or select a StableCraft layer to use its original selection."
    ),
    "Sampler": "Sampler",
    "Scheduler": "Scheduler",
    "Steps": "Steps",
    "Denoise": "Denoise",
    "CFG scale": "CFG scale",
    "Prompt S/R": "Prompt S/R",
    "Negative prompt S/R": "Negative prompt S/R",
    "Chargement": "Loading",
    "Text Encoder": "Text Encoder",
    "VAE Decode": "VAE Decode",
    "VAE Encode": "VAE Encode",
    "Génération": "Generation",
    "Préparation": "Preparation",
    # Tools launcher
    "StableCraft — Outils": "StableCraft — Tools",
    "Outils": "Tools",
    "Outils…": "Tools…",
    "Des outils pour préparer et comparer tes générations, sans quitter StableCraft.": (
        "Tools to prepare and compare your generations without leaving StableCraft."
    ),
    "Planche X/Y/Z": "X/Y/Z sheet",
    "Compare un prompt sur plusieurs axes (sampler, steps, LoRA, CFG…) et génère une planche X/Y/Z avec les réglages de la fenêtre principale.": (
        "Compare a prompt across several axes (sampler, steps, LoRA, CFG…) and "
        "generate an X/Y/Z sheet with the main window settings."
    ),
    "Image → prompt": "Image → prompt",
    "Transforme n'importe quelle image en prompt adapté au modèle actif. Florence-2 PromptGen tourne en local, sans toucher au workflow de génération.": (
        "Turn any image into a prompt suited to the active model. Florence-2 "
        "PromptGen runs locally without touching the generation workflow."
    ),
    "D'autres outils pourront s'ajouter ici.": "More tools can be added here.",
    # Captioning tool
    "StableCraft — Captioning": "StableCraft — Captioning",
    "Captioning": "Captioning",
    "Transforme une image en prompt. Florence-2 tourne en local dans ComfyUI, sans modifier ton workflow de génération.": (
        "Turn an image into a prompt. Florence-2 runs locally in ComfyUI "
        "without changing your generation workflow."
    ),
    "IMAGE": "IMAGE",
    "Aucune image.\nChoisis un fichier ou colle une image.": (
        "No image.\nChoose a file or paste an image."
    ),
    "Aucune image.": "No image.",
    "Choisir une image…": "Choose an image…",
    "PNG, JPG, WebP, BMP, TIFF. L'image est réduite à 2048 px.": (
        "PNG, JPG, WebP, BMP, TIFF. The image is capped at 2048 px."
    ),
    "RÉSULTAT": "RESULT",
    "Modèle": "Model",
    "Recherche…": "Searching…",
    "Recharger": "Reload",
    "Type de prompt": "Prompt type",
    "Description — phrase complète": "Description — full sentence",
    "Prompt mixte — phrase + tags": "Mixed prompt — sentence + tags",
    "Tags — style booru": "Tags — booru style",
    "Une phrase naturelle et concise. Recommandé pour MiniMax, Qwen, FLUX et Krea : ces modèles préfèrent une description complète.": (
        "A concise natural sentence. Recommended for MiniMax, Qwen, FLUX and "
        "Krea: these models prefer a complete description."
    ),
    "Une phrase suivie de tags, comme un prompt Stable Diffusion. Plus long, utile quand le modèle aime les mots-clés.": (
        "A sentence followed by tags, like a Stable Diffusion prompt. Longer, "
        "useful when the model likes keywords."
    ),
    "Une liste de tags courte. Plusieurs essais sont faits pour écarter les sorties qui partent en prose.": (
        "A short tag list. Several attempts are made to discard outputs that "
        "drift into prose."
    ),
    "Florence-2 n'a pas produit de tags ; le texte reste une description.": (
        "Florence-2 produced no tags; the text remains a description."
    ),
    "Profil actif : {profile}. Le résultat est en anglais, comme les prompts des modèles.": (
        "Active profile: {profile}. The result is in English, like the model prompts."
    ),
    "Analyser l'image": "Analyse image",
    "Remplacer le prompt": "Replace prompt",
    "Ajouter au prompt": "Append to prompt",
    "Copier": "Copy",
    "Effacer": "Clear",
    "Le texte est modifiable avant de l'envoyer. Florence-2 est déchargé après l'analyse ; ton modèle de génération sera rechargé à la prochaine génération si ComfyUI a dû libérer de la VRAM.": (
        "The text can be edited before sending. Florence-2 is unloaded after "
        "the analysis; your generation model will be reloaded on the next run "
        "if ComfyUI had to free VRAM."
    ),
    "Recherche des modèles Florence-2…": "Looking for Florence-2 models…",
    "Le nœud comfyui-florence2 n'est pas installé. Installe-le puis redémarre ComfyUI.": (
        "The comfyui-florence2 node is not installed. Install it and restart ComfyUI."
    ),
    "Florence-2 indisponible : {error}": "Florence-2 unavailable: {error}",
    "Aucun modèle Florence-2 dans models/LLM. Place Florence-2-base-PromptGen-v2.0 dans le dossier LLM.": (
        "No Florence-2 model in models/LLM. Put "
        "Florence-2-base-PromptGen-v2.0 in the LLM folder."
    ),
    "Choisir une image à décrire": "Choose an image to describe",
    "Préparation de l'image…": "Preparing the image…",
    "Image invalide.": "Invalid image.",
    "{width} × {height} px": "{width} × {height} px",
    "Choisis d'abord une image.": "Choose an image first.",
    "Aucun modèle Florence-2 disponible dans ComfyUI.": (
        "No Florence-2 model available in ComfyUI."
    ),
    "Choisis un modèle Florence-2.": "Choose a Florence-2 model.",
    "Ce modèle Florence-2 ne gère que la description. Choisis un PromptGen pour les tags et le prompt mixte.": (
        "This Florence-2 model only supports descriptions. Choose a PromptGen "
        "build for tags and mixed prompts."
    ),
    "ComfyUI doit être connecté.": "ComfyUI must be connected.",
    "Analyse…": "Analysing…",
    "Analyse de l'image…": "Analysing the image…",
    "Captioning en cours…": "Captioning running…",
    "Analyse terminée en {seconds} s.": "Analysis finished in {seconds} s.",
    "Analyse terminée.": "Analysis finished.",
    "Florence-2 n'a renvoyé aucun texte.": "Florence-2 returned no text.",
    "{count} caractères": "{count} characters",
    "Prompt remplacé par le captioning.": "Prompt replaced by the caption.",
    "Captioning ajouté au prompt.": "Caption appended to the prompt.",
    "Résultat copié.": "Result copied.",
    "Une analyse est en cours. L'annuler et fermer ?": (
        "An analysis is running. Cancel it and close?"
    ),
    # Purge button
    "Libère la VRAM des modèles et rend la RAM de ComfyUI au système.": (
        "Frees model VRAM and returns ComfyUI's RAM to the system."
    ),
    "Purge…": "Purge…",
    "Purge de la mémoire ComfyUI…": "Purging ComfyUI memory…",
    "Mémoire ComfyUI libérée.": "ComfyUI memory freed.",
    "Purge impossible : {error}": "Purge failed: {error}",
    "Purge échouée": "Purge failed",
    # Caption engines
    "Florence-2 PromptGen (rapide, ancien)": "Florence-2 PromptGen (fast, legacy)",
    "CapRL-Qwen3VL-4B (captioning, recommandé)": (
        "CapRL-Qwen3VL-4B (captioning, recommended)"
    ),
    "Molmo2-4B (descriptions détaillées)": "Molmo2-4B (detailed descriptions)",
    "JoyCaption Beta One 8B (LoRA / tags / NSFW)": (
        "JoyCaption Beta One 8B (LoRA / tags / NSFW)"
    ),
    "Qwen3.5-9B (généraliste / OCR)": "Qwen3.5-9B (generalist / OCR)",
    "Le moteur historique : très rapide, 1 Go, mais des descriptions courtes. Utile comme secours.": (
        "The legacy engine: very fast, 1 GB, but short descriptions. Useful as a fallback."
    ),
    "Spécialisé captioning, 4B, ~3,2 Go. Détail, structure et fidélité, avec moins d'hallucinations.": (
        "Captioning-specialised, 4B, ~3.2 GB. Detail, structure and fidelity "
        "with fewer hallucinations."
    ),
    "4B open-data, très bon en descriptions détaillées, comptage et scènes chargées. Passe par Transformers (pas de GGUF officiel).": (
        "4B open-data model, strong on detailed descriptions, counting and busy "
        "scenes. Runs through Transformers (no official GGUF)."
    ),
    "8B spécialement entraîné pour les captions de diffusion : descriptif, tags, technique, artistique, NSFW. ~5,4 Go.": (
        "8B trained specifically for diffusion captions: descriptive, tags, "
        "technical, artistic, NSFW. ~5.4 GB."
    ),
    "9B généraliste : excellente compréhension de scène, OCR, analyse. Plus lourd (~6,6 Go) et plus lent qu'un captioner.": (
        "9B generalist: excellent scene understanding, OCR and analysis. "
        "Heavier (~6.6 GB) and slower than a dedicated captioner."
    ),
    "Description": "Description",
    "Prompt mixte": "Mixed prompt",
    "Tags": "Tags",
    "Description détaillée": "Detailed description",
    "Description concise": "Concise description",
    "Description + tags": "Description + tags",
    "Descriptif (formel)": "Descriptive (formal)",
    "Descriptif (décontracté)": "Descriptive (casual)",
    "Factuel": "Straightforward",
    "Tags (booru)": "Tags (booru)",
    "Technique (photo)": "Technical (photo)",
    "Artistique": "Artistic",
    "Analyse de scène": "Scene analysis",
    "Texte / OCR": "Text / OCR",
    "Florence-2 · ComfyUI · ~1 Go": "Florence-2 · ComfyUI · ~1 GB",
    "Florence-2 : vérification…": "Florence-2: checking…",
    "Florence-2 indisponible : voir le journal.": (
        "Florence-2 unavailable: see the log."
    ),
    "Installé · {size} Go": "Installed · {size} GB",
    "Manquant · {size} Go": "Missing · {size} GB",
    "Style : {style}.": "Style: {style}.",
    "GPU (auto)": "GPU (auto)",
    "CPU": "CPU",
    "CPU = plus lent, zéro VRAM.": "CPU = slower, zero VRAM.",
    "Modèle Florence": "Florence model",
    "Calcul": "Compute",
    "Moteur": "Engine",
    "Style": "Style",
    "Modèle manquant : {label}. Télécharge-le dans {path}.": (
        "Missing model: {label}. Download it into {path}."
    ),
    "Le moteur tourne dans un processus séparé. GPU = rapide, mais peut déplacer le modèle de ComfyUI ; CPU = plus lent, zéro VRAM. Le premier chargement peut prendre une minute.": (
        "The engine runs in a separate process. GPU = fast but may evict the "
        "ComfyUI model; CPU = slower, zero VRAM. The first load can take a minute."
    ),
    "Florence-2 est chargé dans ComfyUI puis déchargé après l'analyse. Résultat rapide, descriptions plus courtes.": (
        "Florence-2 is loaded in ComfyUI and unloaded after the analysis. Fast "
        "result, shorter descriptions."
    ),
    "Erreur : {error}": "Error: {error}",
    "Captioning : {error}": "Captioning: {error}",
    "Le moteur de captioning s'est arrêté.": "The captioning engine stopped.",
    "Chargement du moteur… (peut prendre une minute)": (
        "Loading the engine… (may take a minute)"
    ),
    "Transforme une image en prompt. Choisis le moteur selon le résultat voulu : captioning pur, tags/LoRA, ou analyse généraliste. Le pipeline ComfyUI n'est pas modifié.": (
        "Turn an image into a prompt. Choose the engine for the result you "
        "want: pure captioning, tags/LoRA, or general analysis. The ComfyUI "
        "pipeline is untouched."
    ),
    # Caption manager
    "StableCraft — Moteurs de captioning": "StableCraft — Caption engines",
    "Moteurs de captioning": "Caption engines",
    "Les moteurs sont optionnels et installés à la demande. Rien n'est ajouté par le setup : le node, le backend vision et les modèles sont téléchargés seulement quand tu cliques.": (
        "Caption engines are optional and installed on demand. The setup adds "
        "nothing: the node, vision backend and models are downloaded only "
        "when you click."
    ),
    "Gérer les moteurs…": "Manage engines…",
    "Inclus": "Included",
    "inclus": "included",
    "{size} Go": "{size} GB",
    "Inclus avec ComfyUI · aucun téléchargement": (
        "Included with ComfyUI · no download"
    ),
    "Node : OK": "Node: OK",
    "Node : installé, redémarrage requis": "Node: installed, restart required",
    "Node : manquant": "Node: missing",
    "Backend vision : OK": "Vision backend: OK",
    "Backend vision : manquant": "Vision backend: missing",
    "Modèle : OK": "Model: OK",
    "Modèle : manquant": "Model: missing",
    "Installation de {label}…": "Installing {label}…",
    "{label} va installer :": "{label} will install:",
    "• le node {node}": "• the node {node}",
    "• le backend vision llama.cpp (223 Mo, une fois)": (
        "• the llama.cpp vision backend (223 MB, once)"
    ),
    "• le modèle {size} Go": "• the model ({size} GB)",
    "ComfyUI sera redémarré. Continuer ?": "ComfyUI will be restarted. Continue?",
    "{label} est déjà prêt. Réinstaller le node, le backend et le modèle ?": (
        "{label} is already ready. Reinstall the node, backend and model?"
    ),
    "Réinstaller": "Reinstall",
    "Une génération est en cours. Attends la fin avant d'installer.": (
        "A generation is running. Wait for it to finish before installing."
    ),
    "Une génération est en cours. Attends la fin avant de redémarrer.": (
        "A generation is running. Wait for it to finish before restarting."
    ),
    "Une installation est en cours. L'annuler et fermer ?": (
        "An installation is running. Cancel it and close?"
    ),
    "Annulation.": "Cancelling.",
    "Installation annulée.": "Installation cancelled.",
    "Moteur installé et prêt.": "Engine installed and ready.",
    "Installation terminée. Redémarre ComfyUI.": (
        "Installation complete. Restart ComfyUI."
    ),
    "Node et modèle installés. Redémarre ComfyUI pour le charger.": (
        "Node and model installed. Restart ComfyUI to load them."
    ),
    "Prêt · node, backend vision et modèle installés": (
        "Ready · node, vision backend and model installed"
    ),
    "ComfyUI déconnecté · ": "ComfyUI disconnected · ",
    "node manquant": "node missing",
    "redémarrage de ComfyUI requis": "ComfyUI restart required",
    "backend vision manquant": "vision backend missing",
    "modèle manquant ({size} Go)": "model missing ({size} GB)",
    "Le node et le modèle sont installés à la demande depuis « Gérer les moteurs… ». Ils tournent dans ComfyUI ; aucun serveur séparé. Le premier chargement peut être long.": (
        "The node and model are installed on demand from “Manage engines…”. "
        "They run inside ComfyUI; no separate server. The first load can be long."
    ),
    "Florence-2 est chargé dans ComfyUI puis déchargé après l'analyse. Aucun téléchargement supplémentaire.": (
        "Florence-2 is loaded in ComfyUI and unloaded after the analysis. No "
        "extra download."
    ),
    "Florence-2 · ComfyUI · prêt": "Florence-2 · ComfyUI · ready",
    "Moteur non installé": "Engine not installed",
    "{label} nécessite encore : {details}.\n\nOuvrir le gestionnaire pour l'installer ?": (
        "{label} still needs: {details}.\n\nOpen the manager to install it?"
    ),
    "Le modèle n'a pas produit de tags ; le texte reste une description.": (
        "The model produced no tags; the text remains a description."
    ),
    "Le moteur n'a renvoyé aucun texte.": "The engine returned no text.",
    "Transforme une image en prompt. Choisis le moteur selon le résultat voulu : captioning pur, tags/LoRA, ou analyse généraliste. Tout passe par ComfyUI.": (
        "Turn an image into a prompt. Choose the engine for the result you "
        "want: pure captioning, tags/LoRA, or general analysis. Everything "
        "runs through ComfyUI."
    ),
    # Caption engine labels and styles
    "CapRL-Qwen3VL-4B (captioning)": "CapRL-Qwen3VL-4B (captioning)",
    "Le moteur historique : très rapide, déjà installé avec comfyui-florence2, mais des descriptions plus courtes.": (
        "The legacy engine: very fast, already installed with "
        "comfyui-florence2, but shorter descriptions."
    ),
    "Captioning spécialisé, 4B, ~3,2 Go. Détail, structure et fidélité, avec moins d'hallucinations. Passe par le node ComfyUI-QwenVL.": (
        "Captioning-specialised, 4B, ~3.2 GB. Detail, structure and fidelity "
        "with fewer hallucinations. Runs through the ComfyUI-QwenVL node."
    ),
    "9B généraliste : excellente compréhension de scène, OCR et analyse. Plus lourd (~6,6 Go) et plus lent qu'un captioner. Passe par le node ComfyUI-QwenVL.": (
        "9B generalist: excellent scene understanding, OCR and analysis. "
        "Heavier (~6.6 GB) and slower than a captioner. Runs through the "
        "ComfyUI-QwenVL node."
    ),
    "8B spécialement entraîné pour les captions de diffusion : descriptif, tags, prompt SD, critique d'art, NSFW. ~5,4 Go. Passe par le node ComfyUI-JoyCaption.": (
        "8B trained specifically for diffusion captions: descriptive, tags, "
        "SD prompt, art critic, NSFW. ~5.4 GB. Runs through the "
        "ComfyUI-JoyCaption node."
    ),
    "Prompt génératif": "Generation prompt",
    "Prompt cinématique": "Cinematic prompt",
    "Descriptif": "Descriptive",
    "Prompt Stable Diffusion": "Stable Diffusion prompt",
    "Critique d'art": "Art critic",
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
