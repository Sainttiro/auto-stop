#!/bin/bash

# Скрипт обновления контейнера
# Использование: ./scripts/update.sh

set -e

cd /opt/projects/auto-stop

echo "🔄 Обновление контейнера..."

# Pull latest changes from git
git pull origin main

# Pull latest image
docker compose pull

# Restart container
docker compose up -d

echo "✅ Обновление завершено!"
docker compose ps
