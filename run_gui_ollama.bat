@echo off
setlocal
cd /d "%~dp0"
set "AH_CONFIG=%CD%\config\ollama.toml"
call "%CD%\run_gui.bat"
endlocal
