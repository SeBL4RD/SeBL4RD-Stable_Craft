# Compatibilité avec PhotoCraft

## Principe

StableCraft ne vérifie pas seulement un numéro de version : il vérifie les **capacités**
du control channel. Un build peut avoir le même numéro et des commandes différentes, ou
un numéro différent et les mêmes commandes.

Au démarrage :

1. connexion au control channel avec le token ;
2. `engine.commands` → liste des IDs disponibles ;
3. vérification des commandes requises ;
4. `ui.inspect` → champs utilisés ;
5. self-test optionnel dans un document temporaire.

## Commandes requises

```
app.open
app.save
document.inspect
document.activate
channel.duplicate
file.close
layer.copyToDocument
layer.layerMask.revealSelection
layer.select
select.saveSelection
select.loadSelection
edit.undo
```

Si une commande manque, l'application affiche un message explicite et propose :

- mettre à jour StableCraft ;
- utiliser une build PhotoCraft testée ;
- désactiver la fonctionnalité concernée (si elle est optionnelle).

## Matrice testée

Fichier `compat.toml` à la racine du repo :

```toml
[[tested]]
stablecraft = "0.1.x"
photocraft = "0.14.0"
os = "windows-x64"
status = "tested"
notes = "Lasso, app.save, select.saveSelection, channel.duplicate, layer.copyToDocument, layerMask.revealSelection/edit, select.loadSelection, app.open. Voir prototypes/bridge_cli.py."

[[tested]]
stablecraft = "0.1.x"
photocraft = "0.13.x"
os = "windows-x64"
status = "untested"
notes = "À vérifier."
```

## Versionnement

- `StableCraft 0.1.0` : première version publique.
- Build metadata : `0.1.0+pc0.14.0` (testé avec PhotoCraft 0.14.0).
- L'installateur affiche la version testée et un avertissement pour les builds non
  testées.
- Le numéro de version de PhotoCraft peut être lu depuis l'exécutable (ressource
  Windows) ou le help/system info ; s'il n'est pas exposé, la détection de commandes
  reste la source de vérité.

## Ce qui casse le plus probablement

| Commande | Risque |
|---|---|
| `layer.copyToDocument` | signature des params (`offset`, `at`, `source`) |
| `layer.layerMask.revealSelection` | comportement de la sélection après activation |
| `channel.duplicate` | forme du retour (`document` index) |
| `app.save` | options de format/couleur |
| `document.inspect` | champs `selectionBounds`, `selectedLayers` |

Le self-test vérifie ces points sur un document synthétique avant d'activer le bouton
« Générer ».

## Connexion inactive

PhotoCraft peut fermer une connexion de contrôle restée inactive pendant le sampling
ComfyUI (~30 s). Le bridge doit se reconnecter avant la phase d'application, puis
retrouver le document original par son nom/chemin et réactiver sa sélection
(`select.loadSelection`). C'est ce que fait `prototypes/bridge_cli.py`.
