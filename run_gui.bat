@echo off
setlocal
cd /d "%~dp0"
set "CONFIG=%AH_CONFIG%"
if not defined CONFIG set "CONFIG=%CD%\config\ollama.toml"
if exist ".venv\Scripts\ah-gui.exe" (
  ".venv\Scripts\ah-gui.exe" --config "%CONFIG%"
) else (
  where ah-gui >nul 2>&1 && (
    ah-gui --config "%CONFIG%"
  ) || (
    python -m ah.gui.app --config "%CONFIG%"
  )
)
endlocal
