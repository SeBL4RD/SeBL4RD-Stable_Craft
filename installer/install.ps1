<#
.SYNOPSIS
    Configure StableCraft dans le dossier courant.

.DESCRIPTION
    - utilise le dossier du dépôt/archive tel quel, sans copie dans AppData ni
      dans un autre dossier ;
    - détecte PhotoCraft et le Python embarqué de ComfyUI ;
    - crée user\, models\ et écrit config.toml si nécessaire ;
    - crée un raccourci StableCraft vers StableCraft.bat ;
    - ne télécharge aucun modèle.

.EXAMPLE
    Double-clique sur InstallStableCraft.bat à la racine du projet.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installer\install.ps1 `
      -PhotoCraft "D:\Programmes\photocraft-0.14.0-windows-x64-portable\photocraft.exe" `
      -ComfyPython "F:\ComfyUI_windows_portable\python_embeded\python.exe" `
      -ConfigFile .\config.toml -NoShortcuts
#>

[CmdletBinding()]
param(
    [string]$PhotoCraft = "",
    [string]$ComfyPython = "",
    [string]$ComfyEndpoint = "",
    [string]$ConfigFile = "",
    [switch]$NoShortcuts,
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$ExampleConfig = Join-Path $Root "config.example.toml"
$StableCraftBat = Join-Path $Root "StableCraft.bat"
$Launcher = Join-Path $Root "launcher.py"
$Prototypes = Join-Path $Root "prototypes"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "== $Text" -ForegroundColor Cyan
}

function Find-PhotoCraft {
    $candidates = @(
        "D:\Programmes\photocraft-0.14.0-windows-x64-portable\photocraft.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\PhotoCraft\photocraft.exe"),
        "C:\Program Files\PhotoCraft\photocraft.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
    }
    $found = Get-ChildItem -Path "D:\Programmes", (Join-Path $env:LOCALAPPDATA "Programs"), "C:\Program Files" `
        -Filter "photocraft.exe" -Recurse -Depth 3 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.FullName }
    return $null
}

function Find-ComfyPython {
    $candidates = @(
        "F:\ComfyUI_windows_portable\python_embeded\python.exe",
        "C:\ComfyUI_windows_portable\python_embeded\python.exe",
        "D:\ComfyUI_windows_portable\python_embeded\python.exe",
        "E:\ComfyUI_windows_portable\python_embeded\python.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
    }
    $roots = @("C:\", "D:\", "E:\", "F:\")
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $found = Get-ChildItem -Path $root -Filter "python.exe" -Recurse -Depth 3 -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "python_embeded" } | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

function Convert-ToTomlPath([string]$Path) {
    return ($Path -replace "\\", "/")
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Write-Utf8Bom([string]$Path, [string]$Text) {
    $encoding = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Set-ConfigPaths([string]$Text) {
    $text = $Text -replace '(?m)^\s*executable\s*=.*$', "executable = `"$script:PhotoToml`""
    $text = $text -replace '(?m)^\s*control_port\s*=\s*7878\s*$', 'control_port = 7990'
    $text = $text -replace '(?m)^\s*root\s*=.*$', "root = `"$script:ComfyRootToml`""
    $text = $text -replace '(?m)^\s*start_command\s*=.*$', "start_command = `"$script:StartToml`""
    $text = $text -replace '(?m)^\s*control_token_file\s*=.*$', "control_token_file = `"$script:TokenToml`""
    $text = $text -replace '(?m)^\s*automation_root\s*=.*$', "automation_root = `"$script:UserToml`""
    $text = $text -replace '(?m)^\s*python\s*=.*$', "python = `"$script:ComfyToml`""
    $text = $text -replace '(?m)^\s*endpoint\s*=.*$', "endpoint = `"$ComfyEndpoint`""
    $text = $text -replace '(?m)^\s*store_dir\s*=.*$', "store_dir = `"$script:ModelsToml`""
    if ($text -match '(?m)^\s*sessions_dir\s*=') {
        $text = $text -replace '(?m)^\s*sessions_dir\s*=.*$', "sessions_dir = `"$script:SessionsToml`""
    } else {
        $text = $text -replace '(?m)^(default_profile\s*=.*)$', ('$1' + "`r`nsessions_dir = `"$script:SessionsToml`"")
    }
    return $text
}

# ---------------------------------------------------------------------------
# Vérification du dossier courant
# ---------------------------------------------------------------------------

Write-Step "Dossier StableCraft"
if (-not (Test-Path $StableCraftBat)) {
    throw "StableCraft.bat introuvable dans $Root. Lance l'installateur depuis le dossier du projet."
}
if (-not (Test-Path $Launcher)) {
    throw "launcher.py introuvable dans $Root."
}
if (-not (Test-Path $Prototypes)) {
    throw "Dossier prototypes introuvable dans $Root."
}
if (-not (Test-Path $ExampleConfig)) {
    throw "config.example.toml introuvable dans $Root."
}
Write-Host "Installation dans : $Root" -ForegroundColor Green
Write-Host "Aucun fichier ne sera copié dans AppData ou dans un autre dossier." -ForegroundColor DarkGray

# ---------------------------------------------------------------------------
# Détection
# ---------------------------------------------------------------------------

Write-Step "Détection de PhotoCraft"
if (-not $PhotoCraft) { $PhotoCraft = Find-PhotoCraft }
if (-not $PhotoCraft) {
    $PhotoCraft = Read-Host "Chemin complet de photocraft.exe"
}
if (-not (Test-Path $PhotoCraft)) {
    throw "photocraft.exe introuvable : $PhotoCraft"
}
$PhotoCraft = (Resolve-Path $PhotoCraft).Path
Write-Host "PhotoCraft : $PhotoCraft" -ForegroundColor Green

Write-Step "Détection de ComfyUI"
if (-not $ComfyPython) { $ComfyPython = Find-ComfyPython }
if (-not $ComfyPython) {
    $ComfyPython = Read-Host "Chemin complet du python_embeded de ComfyUI"
}
if (-not (Test-Path $ComfyPython)) {
    throw "python_embeded introuvable : $ComfyPython"
}
$ComfyPython = (Resolve-Path $ComfyPython).Path
Write-Host "Python ComfyUI : $ComfyPython" -ForegroundColor Green

Write-Step "Vérification du Python de l'UI"
$uiPythonOk = $false
$uiPythonLabel = $null
$pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pyLauncher) {
    & $pyLauncher.Source -3 -c "import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $uiPythonOk = $true
        $uiPythonLabel = "$($pyLauncher.Source) -3"
    }
}
if (-not $uiPythonOk) {
    $pythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($pythonExe) {
        & $pythonExe -c "import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $uiPythonOk = $true
            $uiPythonLabel = $pythonExe
        }
    }
}
if (-not $uiPythonOk) {
    Write-Warning "Python 3.11+ avec Tkinter introuvable. L'UI ne pourra pas démarrer. Installe Python depuis python.org en cochant 'Add python.exe to PATH' et 'tcl/tk and IDLE'."
} else {
    Write-Host "Python UI : $uiPythonLabel" -ForegroundColor Green
}

& $ComfyPython -c "import requests, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Le Python ComfyUI n'a pas requests/Pillow. Le bridge échouera."
}

# ---------------------------------------------------------------------------
# Dossiers et config
# ---------------------------------------------------------------------------

Write-Step "Préparation des données"
$userDir = Join-Path $Root "user"
$sessions = Join-Path $userDir "sessions"
$models = Join-Path $Root "models"
$token = Join-Path $userDir "control.token"
New-Item -ItemType Directory -Force -Path $userDir, $sessions, $models | Out-Null

# Reprend les sessions d'une ancienne installation dans tmp/, sans les supprimer.
$legacySessions = Join-Path $Root "tmp\stablecraft\sessions"
if (Test-Path $legacySessions) {
    Get-ChildItem $legacySessions -Directory | ForEach-Object {
        $destination = Join-Path $sessions $_.Name
        if (-not (Test-Path $destination)) {
            Copy-Item $_.FullName $destination -Recurse -Force
        }
    }
    Write-Host "Sessions existantes copiées vers user\sessions." -ForegroundColor Green
}

$configTarget = Join-Path $Root "config.toml"
$comfyRoot = Split-Path (Split-Path $ComfyPython)
$startCommand = Join-Path $comfyRoot "run_nvidia_gpu.bat"

if (-not $ComfyEndpoint) {
    $ComfyEndpoint = "http://127.0.0.1:8188"
    $sourceConfig = $null
    if ($ConfigFile -and (Test-Path $ConfigFile)) {
        $sourceConfig = $ConfigFile
    } elseif (Test-Path $configTarget) {
        $sourceConfig = $configTarget
    }
    if ($sourceConfig) {
        $existingText = Get-Content $sourceConfig -Raw -Encoding UTF8
        $endpointMatch = [regex]::Match($existingText, '(?m)^\s*endpoint\s*=\s*"([^"]+)"')
        if ($endpointMatch.Success) {
            $ComfyEndpoint = $endpointMatch.Groups[1].Value
        }
    }
}

$script:TokenToml = Convert-ToTomlPath $token
$script:UserToml = Convert-ToTomlPath $userDir
$script:SessionsToml = Convert-ToTomlPath $sessions
$script:ModelsToml = Convert-ToTomlPath $models
$script:ComfyToml = Convert-ToTomlPath $ComfyPython
$script:PhotoToml = Convert-ToTomlPath $PhotoCraft
$script:ComfyRootToml = Convert-ToTomlPath $comfyRoot
$script:StartToml = Convert-ToTomlPath $startCommand

Write-Step "Configuration"
if ($ConfigFile) {
    if (-not (Test-Path $ConfigFile)) {
        throw "ConfigFile introuvable : $ConfigFile"
    }
    $ConfigFile = (Resolve-Path $ConfigFile).Path
    $text = Get-Content $ConfigFile -Raw -Encoding UTF8
    $text = Set-ConfigPaths $text
    Write-Utf8NoBom $configTarget $text
    Write-Host "Config importée depuis $ConfigFile." -ForegroundColor Green
} elseif (Test-Path $configTarget) {
    $text = Get-Content $configTarget -Raw -Encoding UTF8
    $text = Set-ConfigPaths $text
    Write-Utf8NoBom $configTarget $text
    Write-Host "config.toml existant mis à jour avec les chemins détectés." -ForegroundColor Green
} else {
    $text = Get-Content $ExampleConfig -Raw -Encoding UTF8
    $text = Set-ConfigPaths $text
    Write-Utf8NoBom $configTarget $text
    Write-Host "config.toml créé depuis config.example.toml." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Désinstalleur
# ---------------------------------------------------------------------------

$uninstaller = Join-Path $Root "uninstall.ps1"
$uninstallText = @"
`$ErrorActionPreference = "SilentlyContinue"
`$root = Split-Path -Parent `$MyInvocation.MyCommand.Path
`$startMenu = Join-Path `$env:APPDATA "Microsoft\Windows\Start Menu\Programs\StableCraft"
Remove-Item `$startMenu -Recurse -Force
Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "StableCraft.lnk") -Force
`$removeData = Read-Host "Supprimer aussi user\, models\ et config.toml ? (o/N)"
if (`$removeData -eq "o") {
    Remove-Item (Join-Path `$root "user") -Recurse -Force
    Remove-Item (Join-Path `$root "models") -Recurse -Force
    Remove-Item (Join-Path `$root "config.toml") -Force
    Write-Host "Données et configuration supprimées."
} else {
    Write-Host "Le code, user\, models\ et config.toml sont conservés."
}
Remove-Item (Join-Path `$root "uninstall.ps1") -Force
"@
Write-Utf8Bom $uninstaller $uninstallText

# ---------------------------------------------------------------------------
# Raccourcis
# ---------------------------------------------------------------------------

if (-not $NoShortcuts) {
    Write-Step "Création des raccourcis"
    $shell = New-Object -ComObject WScript.Shell
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\StableCraft"
    New-Item -ItemType Directory -Force -Path $startMenu | Out-Null

    $mainShortcut = $shell.CreateShortcut((Join-Path $startMenu "StableCraft.lnk"))
    $mainShortcut.TargetPath = $StableCraftBat
    $mainShortcut.WorkingDirectory = $Root
    $mainShortcut.IconLocation = "$PhotoCraft,0"
    $mainShortcut.Description = "Lancer ComfyUI, PhotoCraft et StableCraft"
    $mainShortcut.Save()

    $uninstallShortcut = $shell.CreateShortcut((Join-Path $startMenu "Désinstaller StableCraft.lnk"))
    $uninstallShortcut.TargetPath = "powershell.exe"
    $uninstallShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$uninstaller`""
    $uninstallShortcut.WorkingDirectory = $Root
    $uninstallShortcut.Save()

    if (-not $NoDesktopShortcut) {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $desktopShortcut = $shell.CreateShortcut((Join-Path $desktop "StableCraft.lnk"))
        $desktopShortcut.TargetPath = $StableCraftBat
        $desktopShortcut.WorkingDirectory = $Root
        $desktopShortcut.IconLocation = "$PhotoCraft,0"
        $desktopShortcut.Save()
    }
    Write-Host "Raccourcis créés dans $startMenu" -ForegroundColor Green
} else {
    Write-Host "Raccourcis ignorés (-NoShortcuts)." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Résumé
# ---------------------------------------------------------------------------

Write-Step "Terminé"
Write-Host "StableCraft       : $Root"
Write-Host "Données           : $userDir"
Write-Host "Modèles           : $models"
Write-Host "PhotoCraft        : $PhotoCraft"
Write-Host "Python ComfyUI    : $ComfyPython"
Write-Host "Endpoint ComfyUI  : $ComfyEndpoint"
Write-Host "Config            : $configTarget"
Write-Host "Lanceur           : $StableCraftBat"
Write-Host ""
Write-Host "Aucun modèle n'a été téléchargé." -ForegroundColor Yellow
Write-Host "Les modèles doivent être visibles par ComfyUI (voir README.md)." -ForegroundColor Yellow
Write-Host "Pour lancer : double-clique sur StableCraft.bat (ou le raccourci StableCraft)." -ForegroundColor Cyan
