#!/bin/bash

# Скрипт просмотра логов
# Использование: ./scripts/logs.sh [lines]

cd /opt/projects/auto-stop

LINES=${1:-100}

echo "📋 Последние $LINES строк логов:"
echo "================================"

docker compose logs --tail=$LINES --follow
