@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Flow-Studio-Helper.ps1"
if errorlevel 1 (
  echo.
  echo Cai dat chua hoan tat. Vui long chup man hinh loi va gui cho Manager.
  pause
)
