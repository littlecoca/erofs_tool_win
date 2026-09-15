@echo off
rem SPDX-License-Identifier: 0BSD
rem ============================================================
rem  IMG Extractor (EROFS) - GUI launcher
rem  Drag .img files into the window to extract them.
rem  NOTE: keep this file ASCII-only. cmd.exe re-reads .bat files
rem        by byte offset, so multi-byte (UTF-8) text makes the
rem        parser lose sync on non-UTF8 code pages.
rem ============================================================
setlocal enabledelayedexpansion
set "HERE=%~dp0"
set "PYW="

rem 1) pythonw.exe on PATH
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"

rem 2) derive pythonw.exe from python.exe on PATH
if not defined PYW for /f "delims=" %%i in ('where python 2^>nul') do (
  if not defined PYW (
    set "CAND=%%i"
    set "CAND=!CAND:python.exe=pythonw.exe!"
    if exist "!CAND!" set "PYW=!CAND!"
  )
)

rem 3) common install locations
if not defined PYW for %%p in (
  "%USERPROFILE%\anaconda3\pythonw.exe"
  "%USERPROFILE%\miniconda3\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python38\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python39\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
  "C:\Python38\pythonw.exe"
  "D:\software\anaconda\pythonw.exe"
) do if not defined PYW if exist "%%~p" set "PYW=%%~p"

if not defined PYW (
  echo.
  echo   [ERROR] pythonw.exe not found.
  echo   Install Python 3.7+ with "Add Python to PATH", or edit this
  echo   file and set PYW to the full path of pythonw.exe.
  echo.
  pause
  exit /b 1
)

start "" "%PYW%" "%HERE%imgtool_gui.pyw"
exit /b 0
