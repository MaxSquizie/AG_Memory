@echo off
setlocal
cd /d "%~dp0"
python -m pytest -q tests/test_ellipsis_invariants_02513.py tests/test_ellipsis_canonical_02513.py tests/test_ellipsis_recovery_0257.py
set "FORMALIZATION_TEST_EXIT=%ERRORLEVEL%"
echo.
echo Formalization tests exit code: %FORMALIZATION_TEST_EXIT%
pause
exit /b %FORMALIZATION_TEST_EXIT%
