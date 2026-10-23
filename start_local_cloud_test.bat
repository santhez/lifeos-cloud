@echo off
chcp 65001 > nul
title LifeOS Cloud Server (Local Test)
echo ============================================================
echo   Запуск LifeOS Cloud на http://localhost:8080
echo ============================================================
python server.py
pause
