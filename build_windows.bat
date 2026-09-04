@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] uv was not found. Install it from https://docs.astral.sh/uv/
    exit /b 1
)

uv sync --dev
if errorlevel 1 exit /b %errorlevel%

uv run pyinstaller --noconfirm --clean fdsBuilder.spec
if errorlevel 1 exit /b %errorlevel%

echo.
echo Build completed: %CD%\dist\fdsBuilder.exe
endlocal
