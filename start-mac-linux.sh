#!/usr/bin/env bash
# Запуск магазина ПОЛКА:  bash start-mac-linux.sh
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 не найден. Установите: https://python.org/downloads"
  exit 1
fi

[ -f .env ] || cp .env.example .env
mkdir -p data

echo ""
echo "  Запускаю магазин ПОЛКА..."
echo "  Витрина:  http://localhost:8000"
echo "  Админка:  http://localhost:8000/admin   (пароль в файле .env)"
echo "  Остановить: Ctrl+C"
echo ""

( sleep 1.5
  if command -v open >/dev/null 2>&1; then open http://localhost:8000
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:8000
  fi ) &

python3 app.py
