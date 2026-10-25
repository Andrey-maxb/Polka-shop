@echo off
chcp 65001 >nul
title ПОЛКА — интернет-магазин
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo [ОШИБКА] Python не найден.
  echo Скачайте с https://python.org/downloads  и при установке отметьте "Add python.exe to PATH".
  echo.
  pause
  exit /b
)

if not exist ".env" copy ".env.example" ".env" >nul
if not exist "data" mkdir data

echo.
echo   Запускаю магазин ПОЛКА...
echo   Витрина:  http://localhost:8000
echo   Админка:  http://localhost:8000/admin   (пароль в файле .env)
echo.
echo   Чтобы остановить — закройте это окно или нажмите Ctrl+C.
echo.

start "" http://localhost:8000
python app.py
pause
