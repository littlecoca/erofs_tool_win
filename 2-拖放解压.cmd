@echo off
rem SPDX-License-Identifier: 0BSD
rem ============================================================
rem  Drag one or more .img files onto this file:
rem  each image is extracted into a folder with the same name,
rem  right next to the image.
rem  NOTE: keep this file ASCII-only (see 1-...bat for why).
rem ============================================================
setlocal enabledelayedexpansion
set "HERE=%~dp0"
set "PY="

for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY set "PY=%%i"
if not defined PY for %%p in (
  "%USERPROFILE%\anaconda3\python.exe"
  "%USERPROFILE%\miniconda3\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python38\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "C:\Python38\python.exe"
  "D:\software\anaconda\python.exe"
) do if not defined PY if exist "%%~p" set "PY=%%~p"

if not defined PY (
  echo   [ERROR] python.exe not found. Install Python 3.7+ and add it to PATH.
  pause
  exit /b 1
)

if "%~1"=="" (
  echo.
  echo   Drag .img files onto this file to extract them into a folder
  echo   with the same name. Or type the full path of an image here:
  echo.
  set /p "MANUAL=   Path: "
  if "!MANUAL!"=="" exit /b 0
  "%PY%" "%HERE%imgtool_cli.py" "!MANUAL!"
) else (
  "%PY%" "%HERE%imgtool_cli.py" %*
)

echo.
echo   ---- finished ----
pause
exit /b 0
