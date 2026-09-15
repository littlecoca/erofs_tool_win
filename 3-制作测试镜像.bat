@echo off
rem SPDX-License-Identifier: 0BSD
rem ============================================================
rem  Build EROFS test images with mkfs.erofs.
rem  Output: test\fixtures\fixture_*.img
rem  NOTE: keep this file ASCII-only (see 1-...bat for why).
rem ============================================================
setlocal
set "HERE=%~dp0"
set "PY="

for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY set "PY=%%i"
if not defined PY for %%p in (
  "%USERPROFILE%\anaconda3\python.exe"
  "%USERPROFILE%\miniconda3\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "C:\Python38\python.exe"
  "D:\software\anaconda\python.exe"
) do if not defined PY if exist "%%~p" set "PY=%%~p"

if not defined PY (
  echo   [ERROR] python.exe not found.
  pause
  exit /b 1
)

"%PY%" "%HERE%tests\make_fixtures.py" %*
echo.
pause
exit /b 0
