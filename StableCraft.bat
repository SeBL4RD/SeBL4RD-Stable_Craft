@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title StableCraft

where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo Python 3.11+ est requis pour lancer StableCraft.
    echo Installe-le depuis https://www.python.org/downloads/ en cochant "Add to PATH".
    echo.
    timeout /t 20 >nul
    exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Python 3.11 ou plus recent est requis.
    echo.
    timeout /t 20 >nul
    exit /b 1
)

python launcher.py
if errorlevel 1 (
    echo.
    echo StableCraft n'a pas pu demarrer. Lis le message ci-dessus.
    echo.
    timeout /t 10 >nul
)

endlocal
