#!/usr/bin/env bash
# Обновление приложения на сервере.
set -euo pipefail

cd "$(dirname "$0")/../.."

git pull --ff-only
docker compose build app
docker compose up -d app
docker compose exec nginx nginx -s reload || true
docker image prune -f
echo "Deploy done."
