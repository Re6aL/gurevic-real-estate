@echo off
rem Puts the Telegram bot token (REALESTATE_BOT_TOKEN from the encrypted Automation
rem secrets) into the Cloudflare Worker secret TELEGRAM_BOT_TOKEN. The token is never
rem shown on screen. Run by double-click as the normal user (NOT "as administrator").
rem Optional args (for testing): %1 = source secret name, %2 = worker secret name.
setlocal
set "SRC=%~1"
if "%SRC%"=="" set "SRC=REALESTATE_BOT_TOKEN"
set "DST=%~2"
if "%DST%"=="" set "DST=TELEGRAM_BOT_TOKEN"
cd /d "%~dp0"
python -c "import sys; sys.path.insert(0, r'C:\Users\rotnu\Dropbox\Automation'); from automation_runtime import secret; sys.stdout.write(str(secret('%SRC%')))" | npx --yes wrangler@4 secret put %DST%
echo.
if "%~1"=="" pause
