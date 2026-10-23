@echo off
chcp 65001 > nul
title LifeOS Cloud - Push to GitHub
echo ============================================================
echo   LifeOS Cloud -> GitHub
echo   Репозиторий: https://github.com/santhez/lifeos-cloud.git
echo ============================================================
echo.
cd /d "%~dp0"

git remote remove origin 2>nul
git remote add origin https://github.com/santhez/lifeos-cloud.git
git branch -M main

echo Отправляем файлы в GitHub...
echo (Если появится окно входа в браузере - подтвердите вход в аккаунт santhez)
echo.
git push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo   УСПЕШНО! Все файлы загружены в GitHub (santhez/lifeos-cloud).
    echo   Теперь на Render.com выберите этот репозиторий и нажмите Deploy!
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo   Ошибка при отправке (%ERRORLEVEL%).
    echo   Если требуется токен, создайте Personal Access Token на GitHub
    echo   (Settings -> Developer Settings -> Personal Access Tokens -> Tokens classic)
    echo   с правами 'repo' и используйте его вместо пароля.
    echo ============================================================
)
echo.
pause
