@echo off
REM ------------------------------------------------------------
REM  LexiClicker Pro v2 — Build script (Windows, --onefile)
REM ------------------------------------------------------------

echo [LexiClicker] Installing / upgrading dependencies...
py -m pip install --upgrade pyautogui keyboard flask flask-cors pynput flaskwebgui pystray pillow pyinstaller

echo.
echo [LexiClicker] Killing any running LexiClicker.exe...
taskkill /f /im LexiClicker.exe >nul 2>&1
timeout /t 1 /nobreak >nul

echo.
echo [LexiClicker] Cleaning previous build...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist

echo.
echo [LexiClicker] Running PyInstaller...
py -m PyInstaller ^
  --onedir ^
  --noconsole ^
  --name LexiClicker ^
  --icon=AutoClicker.ico ^
  --add-data "auto-clicker-controller.html;." ^
  --add-data "AutoClicker.ico;." ^
  --add-data "AutoClicker.png;." ^
  --add-data "sounds;sounds" ^
  --hidden-import pystray ^
  --hidden-import pystray._win32 ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageDraw ^
  --hidden-import pynput.mouse ^
  --hidden-import pynput.keyboard ^
  --hidden-import flaskwebgui ^
  --hidden-import flask_cors ^
  LexiClicker.py

echo.
if exist dist\LexiClicker\LexiClicker.exe (
  echo [LexiClicker] SUCCESS: dist\LexiClicker\LexiClicker.exe
) else (
  echo [LexiClicker] BUILD FAILED - check output above
)
pause