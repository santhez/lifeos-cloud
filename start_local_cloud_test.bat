@echo off
title LifeOS Cloud Server (Local Test)
echo ============================================================
echo   Starting LifeOS Cloud Server on http://localhost:8080
echo   Opening browser at http://localhost:8080 ...
echo ============================================================
start "" http://localhost:8080
python server.py
pause
