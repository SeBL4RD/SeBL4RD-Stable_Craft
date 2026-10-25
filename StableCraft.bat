@echo off
setlocal EnableExtensions
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title StableCraft

rem Prefer the Python launcher (py -3), then python from PATH. Both must have
rem Python 3.11+ and Tkinter. Keep the checks in one command so a Python
rem installation without Tkinter can fall back to the other executable.
set "STABLECRAFT_PYTHON="

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "STABLECRAFT_PYTHON=py -3"
)

if not defined STABLECRAFT_PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 set "STABLECRAFT_PYTHON=python"
    )
)

if not defined STABLECRAFT_PYTHON (
    echo.
    echo Python 3.11+ avec Tkinter est requis pour lancer StableCraft.
    echo.
    echo Installe Python depuis https://www.python.org/downloads/
    echo et coche "Add python.exe to PATH" ainsi que "tcl/tk and IDLE".
    echo.
    echo Si Python est deja installe, ouvre un terminal et verifie :
    echo     py -3 -c "import sys, tkinter; print(sys.version)"
    echo.
    timeout /t 25 >nul
    exit /b 1
)

%STABLECRAFT_PYTHON% launcher.py
if errorlevel 1 (
    echo.
    echo StableCraft n'a pas pu demarrer. Lis le message ci-dessus.
    echo Details : %~dp0user\logs\launcher.log
    echo.
    timeout /t 15 >nul
)

endlocal
