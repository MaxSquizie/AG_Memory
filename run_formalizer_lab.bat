@echo off
setlocal
cd /d "%~dp0"
set "LAB_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "LAB_PYTHON=%CD%\.venv\Scripts\python.exe"
set "LAB_CONFIG=%AH_CONFIG%"
if not defined LAB_CONFIG set "LAB_CONFIG=%CD%\config\lmstudio.toml"
set "LAB_SESSION=%CD%\artifacts\formalizer-lab"
if not exist "%LAB_SESSION%\gui.toml" (
  "%LAB_PYTHON%" tools\prepare_formalizer_v7_gui.py --config "%LAB_CONFIG%" --out "%LAB_SESSION%" --profile composition
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
"%LAB_PYTHON%" tools\prepare_formalizer_v7_gui.py --check-session "%LAB_SESSION%\gui.toml"
if errorlevel 1 (
  pause
  exit /b 1
)
echo TEST_ONLY composition session: %LAB_SESSION%
echo Memory and reports persist here. Backend settings: %LAB_SESSION%\gui.toml
"%LAB_PYTHON%" -m ah.gui.app --config "%LAB_SESSION%\gui.toml"
if errorlevel 1 pause
endlocal
