@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
python -m ah.gui.app --config "%CD%\config\default.toml"
endlocal
