@echo off
setlocal
cd /d "%~dp0"
python -m pytest -q
set "ALL_TEST_EXIT=%ERRORLEVEL%"
echo.
echo Full test suite exit code: %ALL_TEST_EXIT%
pause
exit /b %ALL_TEST_EXIT%
