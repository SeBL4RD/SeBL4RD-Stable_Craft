<#
.SYNOPSIS
    Installe StableCraft à côté d'une installation PhotoCraft existante.

.DESCRIPTION
    - copie l'UI et le bridge dans %LOCALAPPDATA%\Programs\StableCraft ;
    - détecte PhotoCraft et le Python embarqué de ComfyUI ;
    - écrit config.toml (token, dossier temporaire, endpoint, Python) ;
    - crée un lanceur unique StableCraft.bat et des raccourcis ;
    - ne télécharge aucun modèle.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installer\install.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installer\install.ps1 `
      -InstallDir C:\DEV\StableCraft `
      -PhotoCraft "D:\Programmes\photocraft-0.14.0-windows-x64-portable\photocraft.exe" `
      -ComfyPython "F:\ComfyUI_windows_portable\python_embeded\python.exe" `
      -ConfigFile .\config.toml -NoShortcuts
#>

[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\StableCraft"),
    [string]$PhotoCraft = "",
    [string]$ComfyPython = "",
    [string]$ComfyEndpoint = "http://127.0.0.1:12452",
    [string]$ConfigFile = "",
    [switch]$NoShortcuts,
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$UiSource = Join-Path $Root "prototypes"
$ExampleConfig = Join-Path $Root "config.example.toml"

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
$systemPython = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $systemPython) {
    Write-Warning "python.exe introuvable. L'UI Tkinter ne pourra pas démarrer. Installe Python 3.11+."
    $systemPythonw = $null
} else {
    & $systemPython -c "import tkinter" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Tkinter est absent de $systemPython. L'UI ne pourra pas démarrer."
    }
    $candidateW = Join-Path (Split-Path $systemPython) "pythonw.exe"
    if (Test-Path $candidateW) { $systemPythonw = $candidateW } else { $systemPythonw = $systemPython }
    Write-Host "Python UI : $systemPython" -ForegroundColor Green
}

& $ComfyPython -c "import requests, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Le Python ComfyUI n'a pas requests/Pillow. Le bridge échouera."
}

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

Write-Step "Installation dans $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$InstallDir = (Resolve-Path $InstallDir).Path
$tmp = Join-Path $InstallDir "tmp"
$models = Join-Path $InstallDir "models"
$token = Join-Path $InstallDir "control.token"
New-Item -ItemType Directory -Force -Path $tmp, $models | Out-Null

New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "prototypes") | Out-Null
Copy-Item (Join-Path $UiSource "*.py") (Join-Path $InstallDir "prototypes") -Force
Copy-Item (Join-Path $UiSource "requirements.txt") (Join-Path $InstallDir "prototypes") -Force
Copy-Item (Join-Path $Root "models.json") $InstallDir -Force
Copy-Item (Join-Path $Root "compat.toml") $InstallDir -Force
Copy-Item $ExampleConfig $InstallDir -Force
Copy-Item (Join-Path $Root "StableCraft.bat") $InstallDir -Force
Copy-Item (Join-Path $Root "launcher.py") $InstallDir -Force
if (Test-Path (Join-Path $Root "docs")) {
    Copy-Item (Join-Path $Root "docs") $InstallDir -Recurse -Force
}
Write-Host "Fichiers copiés." -ForegroundColor Green

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

Write-Step "Écriture de config.toml"
$configTarget = Join-Path $InstallDir "config.toml"
$tokenToml = Convert-ToTomlPath $token
$tmpToml = Convert-ToTomlPath $tmp
$modelsToml = Convert-ToTomlPath $models
$comfyToml = Convert-ToTomlPath $ComfyPython
$photoToml = Convert-ToTomlPath $PhotoCraft
$comfyRoot = Split-Path (Split-Path $ComfyPython)
$comfyRootToml = Convert-ToTomlPath $comfyRoot
$startCommand = Join-Path $comfyRoot "run_nvidia_gpu.bat"
$startToml = Convert-ToTomlPath $startCommand

if ($ConfigFile -and (Test-Path $ConfigFile)) {
    $text = Get-Content $ConfigFile -Raw -Encoding UTF8
    $text = $text -replace '(?m)^\s*executable\s*=.*$', "executable = `"$photoToml`""
    $text = $text -replace '(?m)^\s*root\s*=.*$', "root = `"$comfyRootToml`""
    $text = $text -replace '(?m)^\s*start_command\s*=.*$', "start_command = `"$startToml`""
    $text = $text -replace '(?m)^\s*control_token_file\s*=.*$', "control_token_file = `"$tokenToml`""
    $text = $text -replace '(?m)^\s*automation_root\s*=.*$', "automation_root = `"$tmpToml`""
    $text = $text -replace '(?m)^\s*python\s*=.*$', "python = `"$comfyToml`""
    $text = $text -replace '(?m)^\s*endpoint\s*=.*$', "endpoint = `"$ComfyEndpoint`""
    $text = $text -replace '(?m)^\s*store_dir\s*=.*$', "store_dir = `"$modelsToml`""
    Write-Utf8NoBom $configTarget $text
    Write-Host "Config importée depuis $ConfigFile (chemins d'installation réécrits)." -ForegroundColor Green
} else {
    $config = @"
# StableCraft — configuration générée par l'installateur.
# Les chemins de modèles sont optionnels : renseigne-les seulement pour les
# profils que tu utilises, ou laisse ComfyUI les découvrir.

[app]
language = "fr"
theme = "dark"
default_profile = "flux3_klein"

[photocraft]
executable = "$photoToml"
control_host = "127.0.0.1"
control_port = 7878
control_token_file = "$tokenToml"
automation_root = "$tmpToml"

[comfyui]
endpoint = "$ComfyEndpoint"
root = "$comfyRootToml"
start_command = "$startToml"
python = "$comfyToml"
# models_dir = ""

[models]
store_dir = "$modelsToml"
allow_downloads = true
require_sha256 = true

[profiles.flux3_klein]
enabled = true
# unet = ""
# text_encoder = ""
# vae = ""
steps = 16
cfg = 1.0
sampler = "euler"
scheduler = "simple"
context_padding = 96
feather = 10

[profiles.flux2_klein_9b]
enabled = false
steps = 4
cfg = 1.0
sampler = "euler"
scheduler = "simple"

[profiles.krea2_edit]
enabled = false
steps = 8
cfg = 1.0
sampler = "euler"
scheduler = "simple"
ref_boost = 4.0
grounding_px = 768
"@
    Write-Utf8NoBom $configTarget $config
    Write-Host "Config minimale générée." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Lanceur
# ---------------------------------------------------------------------------

Write-Step "Lanceur"
$stablecraftBat = Join-Path $InstallDir "StableCraft.bat"
Write-Host "Lanceur : $stablecraftBat" -ForegroundColor Green
Write-Host "Il démarre ComfyUI, PhotoCraft et l'UI en un clic." -ForegroundColor Green

# ---------------------------------------------------------------------------
# Désinstalleur
# ---------------------------------------------------------------------------

$uninstaller = Join-Path $InstallDir "uninstall.ps1"
$uninstallText = @"
`$ErrorActionPreference = "SilentlyContinue"
`$install = Split-Path -Parent `$MyInvocation.MyCommand.Path
`$startMenu = Join-Path `$env:APPDATA "Microsoft\Windows\Start Menu\Programs\StableCraft"
Remove-Item `$startMenu -Recurse -Force
Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "StableCraft.lnk") -Force
Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "PhotoCraft + StableCraft.lnk") -Force
`$removeData = Read-Host "Supprimer aussi les modèles et la configuration ? (o/N)"
if (`$removeData -eq "o") {
    Remove-Item `$install -Recurse -Force
} else {
    Remove-Item (Join-Path `$install "prototypes") -Recurse -Force
    Remove-Item (Join-Path `$install "docs") -Recurse -Force
    Remove-Item (Join-Path `$install "StableCraft.bat") -Force
    Remove-Item (Join-Path `$install "launcher.py") -Force
    Remove-Item (Join-Path `$install "launch.cmd") -Force
    Remove-Item (Join-Path `$install "models.json") -Force
    Remove-Item (Join-Path `$install "compat.toml") -Force
    Remove-Item (Join-Path `$install "config.example.toml") -Force
    Remove-Item (Join-Path `$install "uninstall.ps1") -Force
    Write-Host "Les modèles et config.toml sont conservés dans `$install."
}
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
    $mainShortcut.TargetPath = $stablecraftBat
    $mainShortcut.WorkingDirectory = $InstallDir
    $mainShortcut.IconLocation = "$PhotoCraft,0"
    $mainShortcut.Description = "Lancer ComfyUI, PhotoCraft et StableCraft"
    $mainShortcut.Save()

    $uninstallShortcut = $shell.CreateShortcut((Join-Path $startMenu "Désinstaller StableCraft.lnk"))
    $uninstallShortcut.TargetPath = "powershell.exe"
    $uninstallShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$uninstaller`""
    $uninstallShortcut.WorkingDirectory = $InstallDir
    $uninstallShortcut.Save()

    if (-not $NoDesktopShortcut) {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $desktopShortcut = $shell.CreateShortcut((Join-Path $desktop "StableCraft.lnk"))
        $desktopShortcut.TargetPath = $stablecraftBat
        $desktopShortcut.WorkingDirectory = $InstallDir
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
Write-Host "StableCraft       : $InstallDir"
Write-Host "PhotoCraft        : $PhotoCraft"
Write-Host "Python ComfyUI    : $ComfyPython"
Write-Host "Endpoint ComfyUI  : $ComfyEndpoint"
Write-Host "Config            : $configTarget"
Write-Host "Lanceur           : $stablecraftBat"
Write-Host ""
Write-Host "Aucun modèle n'a été téléchargé." -ForegroundColor Yellow
Write-Host "Les modèles doivent être visibles par ComfyUI (voir docs/MODELS.md)." -ForegroundColor Yellow
Write-Host "Pour lancer : double-clique sur StableCraft.bat (ou le raccourci StableCraft)." -ForegroundColor Cyan
