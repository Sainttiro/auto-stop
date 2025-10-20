#!/bin/bash

# Скрипт резервного копирования данных
# Использование: ./scripts/backup.sh

set -e

cd /opt/projects/auto-stop

BACKUP_DIR="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.tar.gz"

echo "📦 Создание резервной копии..."

# Создание директории для бэкапов
mkdir -p $BACKUP_DIR

# Создание архива
tar -czf $BACKUP_FILE \
    data/ \
    logs/ \
    config/ \
    .env \
    docker-compose.yml

echo "✅ Резервная копия создана: $BACKUP_FILE"

# Удаление старых бэкапов (старше 30 дней)
find $BACKUP_DIR -name "backup_*.tar.gz" -mtime +30 -delete

echo "🧹 Старые бэкапы удалены"
ls -lh $BACKUP_DIR
