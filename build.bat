@echo off
setlocal EnableDelayedExpansion
chcp 65001 > nul
title OmniClone Universal Pro — Build Script

echo.
echo ════════════════════════════════════════════════════════════
echo   OmniClone Universal Pro — PyInstaller Build Script
echo ════════════════════════════════════════════════════════════
echo.

:: ── Check we're in the right directory ────────────────────
if not exist "src\main.py" (
    echo [ERROR] Run this script from the omniclone\ directory.
    echo         Example:  cd C:\OmniClone\omniclone ^&^& build.bat
    pause
    exit /b 1
)

:: ── Check Python ──────────────────────────────────────────
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ and add to PATH.
    pause
    exit /b 1
)

echo [1/5] Installing dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo       Done.

:: ── Create required directories ───────────────────────────
echo [2/5] Creating required directories...
if not exist "boot"      mkdir boot
if not exist "resources" mkdir resources
if not exist "dist"      mkdir dist
echo       Done.

:: ── Check for WinPE boot files ────────────────────────────
echo [3/5] Checking WinPE boot files...
if not exist "boot\pxelinux.0" (
    echo.
    echo [WARNING] WinPE boot files not found in boot\
    echo.
    echo   To generate them, you need Windows ADK + WinPE add-on:
    echo   1. Install Windows ADK from Microsoft
    echo   2. Run: copype amd64 C:\WinPE_amd64
    echo   3. Copy C:\WinPE_amd64\media\Boot\pxeboot.n12 → boot\pxelinux.0
    echo   4. Copy C:\WinPE_amd64\media\sources\boot.wim  → boot\boot.wim
    echo   5. Copy C:\WinPE_amd64\media\Boot\BCD           → boot\BCD
    echo   6. Copy OmniClone_Agent.exe into a WinPE mounted image and add
    echo      it as a startup script in Winpeshl.ini
    echo.
    echo   The EXE will build without boot files but TFTP will have
    echo   nothing to serve until you add them.
    echo.
    echo [CREATING PLACEHOLDER] boot\README.txt
    echo Place WinPE boot files here. See build.bat for instructions. > boot\README.txt
)

:: ── Build Agent EXE first ─────────────────────────────────
echo [4/5] Building OmniClone_Agent.exe (target WinPE agent)...
python -m PyInstaller OmniClone_Agent.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] Agent build failed. See above for details.
    pause
    exit /b 1
)
if exist "dist\OmniClone_Agent.exe" (
    copy /Y "dist\OmniClone_Agent.exe" "OmniClone_Agent.exe" > nul
    echo       Agent EXE: dist\OmniClone_Agent.exe
) else (
    echo [ERROR] dist\OmniClone_Agent.exe not found after build.
    pause
    exit /b 1
)

:: ── Build Source EXE ─────────────────────────────────────
echo [5/5] Building OmniClone_Universal_Pro.exe (source machine GUI)...
::
:: Uncomment the line below in OmniClone_Source.spec to bundle the agent:
::   ('OmniClone_Agent.exe', '.'),
::
python -m PyInstaller OmniClone_Source.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] Source EXE build failed. See above for details.
    pause
    exit /b 1
)

:: ── Summary ───────────────────────────────────────────────
echo.
echo ════════════════════════════════════════════════════════════
echo   BUILD COMPLETE
echo ════════════════════════════════════════════════════════════
echo.
if exist "dist\OmniClone_Universal_Pro.exe" (
    for %%F in ("dist\OmniClone_Universal_Pro.exe") do (
        set SIZE=%%~zF
        set /a SIZE_MB=!SIZE! / 1048576
    )
    echo   Source GUI:  dist\OmniClone_Universal_Pro.exe  (!SIZE_MB! MB)
) else (
    echo   [WARNING] OmniClone_Universal_Pro.exe not found.
)
if exist "dist\OmniClone_Agent.exe" (
    for %%F in ("dist\OmniClone_Agent.exe") do (
        set SIZE=%%~zF
        set /a SIZE_MB=!SIZE! / 1048576
    )
    echo   Agent:       dist\OmniClone_Agent.exe           (!SIZE_MB! MB)
)
echo.
echo   Next steps:
echo   1. Copy OmniClone_Universal_Pro.exe to the SOURCE machine ^(run as Admin^)
echo   2. Integrate OmniClone_Agent.exe into your WinPE boot image
echo   3. Add boot files to boot\ directory for PXE serving
echo   4. Connect source and target via Ethernet — done!
echo.
pause
