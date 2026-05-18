@echo off
chcp 65001 >nul
cd /d C:\Users\Habsir\Desktop\vibe\Clipboard_Master

git config --global user.name "Habsir"
git config --global user.email "habsirpu@outlook.com"

git init
git add .
git commit -m "feat: Clipboard Master v1.0 - clipboard history manager"

echo.
git log -1 --oneline
git status
