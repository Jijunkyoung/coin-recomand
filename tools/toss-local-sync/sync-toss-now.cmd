@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\CoinRecomand\Sync-TossPortfolio.ps1"
pause
