#!/bin/bash

# Скрипт развертывания на сервере
# Использование: ./scripts/deploy.sh [version]

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для вывода сообщений
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка, что скрипт запущен на сервере
if [ ! -d "/opt/projects/auto-stop" ]; then
    log_error "Директория /opt/projects/auto-stop не найдена!"
    log_info "Создайте директорию: sudo mkdir -p /opt/projects/auto-stop"
    exit 1
fi

cd /opt/projects/auto-stop

# Получение версии из аргумента или использование latest
VERSION=${1:-latest}
log_info "Развертывание версии: $VERSION"

# Проверка наличия .env файла
if [ ! -f ".env" ]; then
    log_error "Файл .env не найден!"
    log_info "Создайте .env файл с необходимыми переменными окружения"
    exit 1
fi

# Проверка наличия docker-compose
if ! command -v docker &> /dev/null; then
    log_error "Docker не установлен!"
    exit 1
fi

# Создание необходимых директорий
log_info "Создание директорий..."
mkdir -p data logs config

# Остановка текущего контейнера (если запущен)
if docker ps -a | grep -q auto-stop; then
    log_info "Остановка текущего контейнера..."
    docker compose down
fi

# Установка переменных окружения
export VERSION=$VERSION
export GITHUB_REPOSITORY=${GITHUB_REPOSITORY:-yourusername/auto-stop}

# Загрузка нового образа
log_info "Загрузка Docker образа..."
docker compose pull

# Запуск контейнера
log_info "Запуск контейнера..."
docker compose up -d

# Ожидание запуска
log_info "Ожидание запуска контейнера..."
sleep 5

# Проверка статуса
if docker compose ps | grep -q "Up"; then
    log_info "✅ Контейнер успешно запущен!"
    docker compose ps
else
    log_error "❌ Ошибка при запуске контейнера!"
    docker compose logs --tail=50
    exit 1
fi

# Очистка старых образов
log_info "Очистка старых образов..."
docker image prune -f

log_info "🎉 Развертывание завершено успешно!"
log_info "Просмотр логов: docker compose logs -f"
