@echo off
chcp 65001 > nul
title LifeOS Cloud - Push to GitHub with Token
echo ============================================================
echo   Отправка файлов LifeOS Cloud в GitHub по токену
echo   Репозиторий: https://github.com/santhez/lifeos-cloud
echo ============================================================
echo.
echo Вставьте ваш GitHub Personal Access Token (начинается на ghp_)
echo и нажмите Enter:
echo.
set /p GH_TOKEN="Токен: "
if "%GH_TOKEN%"=="" (
    echo [!] Токен не введен. Отмена.
    pause
    exit /b 1
)

cd /d "%~dp0"
echo.
echo Отправляем файлы в GitHub...
git push https://santhez:%GH_TOKEN%@github.com/santhez/lifeos-cloud.git main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo   [OK] УСПЕШНО! Все файлы отправлены в GitHub!
    echo   Render автоматически запустит сборку и через 1 минуту
    echo   сайт будет работать по ссылке:
    echo   https://lifeos-cloud-d1tm.onrender.com
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo   [!] Ошибка при отправке (%ERRORLEVEL%).
    echo   Проверьте, что у токена отмечена галочка 'repo'.
    echo ============================================================
)
echo.
pause
