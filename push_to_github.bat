@echo off
chcp 65001 > nul
echo ============================================================
echo   Отправка LifeOS Cloud на GitHub
echo ============================================================
echo.
set /p REPO_URL="Вставьте ссылку на репозиторий GitHub (например, https://github.com/ваш_логин/lifeos-cloud.git): "
if "%REPO_URL%"=="" (
    echo Ссылка не указана. Отмена.
    pause
    exit /b
)

git remote remove origin 2>nul
git remote add origin %REPO_URL%
git branch -M main
echo.
echo Отправляем файлы в GitHub...
git push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo   УСПЕШНО! Проект загружен на GitHub.
    echo   Теперь на Render.com подключите этот репозиторий в 2 клика.
    echo ============================================================
) else (
    echo.
    echo Ошибка при отправке. Проверьте права доступа или правильность ссылки.
)
echo.
pause
