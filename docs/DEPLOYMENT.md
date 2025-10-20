# Руководство по развертыванию Auto-Stop

Это руководство поможет вам развернуть систему Auto-Stop на вашем сервере с использованием Docker и GitHub Actions.

## Содержание

1. [Требования](#требования)
2. [Подготовка сервера](#подготовка-сервера)
3. [Настройка GitHub](#настройка-github)
4. [Первое развертывание](#первое-развертывание)
5. [Обновление системы](#обновление-системы)
6. [Управление](#управление)
7. [Мониторинг](#мониторинг)
8. [Решение проблем](#решение-проблем)

## Требования

### Сервер
- Ubuntu 20.04+ (или другой Linux)
- Docker 20.10+
- Docker Compose 1.29+
- Git
- 1GB RAM минимум (рекомендуется 2GB)
- 5GB свободного места на диске

### Учетные записи
- GitHub аккаунт
- Tinkoff Invest аккаунт с API токеном
- Telegram бот (опционально, для управления)

## Подготовка сервера

### 1. Подключение к серверу

```bash
ssh user@your-server-ip -p 2222
```

### 2. Установка Docker (если не установлен)

```bash
# Обновление пакетов
sudo apt update
sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Добавление пользователя в группу docker
sudo usermod -aG docker $USER

# Перелогиниться для применения изменений
exit
# Подключиться снова
```

### 3. Создание директории проекта

```bash
sudo mkdir -p /opt/projects/auto-stop
sudo chown $USER:$USER /opt/projects/auto-stop
cd /opt/projects/auto-stop
```

### 4. Клонирование репозитория

```bash
git clone https://github.com/yourusername/auto-stop.git .
```

### 5. Создание .env файла

```bash
nano .env
```

Добавьте следующие переменные:

```env
# Tinkoff API
TINKOFF_TOKEN=your_tinkoff_token_here
ACCOUNT_ID=your_account_id_here

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# GitHub (для docker-compose)
GITHUB_REPOSITORY=yourusername/auto-stop
VERSION=latest

# Logging
LOG_LEVEL=INFO
```

Сохраните файл (Ctrl+O, Enter, Ctrl+X).

### 6. Создание необходимых директорий

```bash
mkdir -p data logs config
```

### 7. Копирование конфигурационных файлов

```bash
# Конфигурация уже должна быть в репозитории
# Проверьте наличие файлов
ls -la config/
```

## Настройка GitHub

См. [GITHUB_SETUP.md](GITHUB_SETUP.md) для подробных инструкций.

Краткая версия:

1. Создайте публичный репозиторий `auto-stop`
2. Добавьте Secrets в Settings → Secrets and variables → Actions:
   - `SERVER_HOST` - IP вашего сервера
   - `SERVER_USER` - имя пользователя
   - `SERVER_SSH_KEY` - приватный SSH ключ
   - `SERVER_PORT` - порт SSH (обычно 2222)

## Первое развертывание

### Вариант 1: Локальная сборка (для тестирования)

```bash
cd /opt/projects/auto-stop

# Сборка образа
docker compose -f docker-compose.dev.yml build

# Запуск
docker compose -f docker-compose.dev.yml up -d

# Просмотр логов
docker compose logs -f
```

### Вариант 2: Через GitHub Actions (рекомендуется)

```bash
# На вашем компьютере
cd /path/to/auto-stop
git add .
git commit -m "Initial commit"
git push origin main

# Создание релиза
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions автоматически:
1. Соберет Docker образ
2. Опубликует в GitHub Container Registry
3. Задеплоит на ваш сервер

## Обновление системы

### Автоматическое обновление (через релиз)

```bash
# На вашем компьютере
git tag v1.0.1
git push origin v1.0.1
```

### Ручное обновление

```bash
# На сервере
cd /opt/projects/auto-stop
./scripts/update.sh
```

## Управление

### Запуск системы

```bash
cd /opt/projects/auto-stop
docker compose up -d
```

### Остановка системы

```bash
docker compose down
```

### Перезапуск системы

```bash
docker compose restart
```

### Просмотр статуса

```bash
docker compose ps
```

### Просмотр логов

```bash
# Все логи
docker compose logs -f

# Последние 100 строк
docker compose logs --tail=100

# Или используйте скрипт
./scripts/logs.sh 100
```

### Резервное копирование

```bash
./scripts/backup.sh
```

Бэкапы сохраняются в `backups/` и автоматически удаляются через 30 дней.

## Мониторинг

### Проверка здоровья контейнера

```bash
docker inspect auto-stop | grep -A 10 Health
```

### Использование ресурсов

```bash
docker stats auto-stop
```

### Размер логов

```bash
du -sh logs/
```

## Telegram Bot

После запуска системы, бот автоматически отправит сообщение о готовности.

Доступные команды:
- `/start` - Приветствие и список команд
- `/status` - Статус системы
- `/positions` - Текущие позиции
- `/stats` - Статистика
- `/logs` - Последние логи
- `/help` - Справка

## Решение проблем

### Контейнер не запускается

```bash
# Проверьте логи
docker compose logs

# Проверьте .env файл
cat .env

# Проверьте права доступа
ls -la data/ logs/
```

### Ошибки подключения к API

```bash
# Проверьте токен
echo $TINKOFF_TOKEN

# Проверьте сетевое подключение
docker compose exec auto-stop ping -c 3 invest-public-api.tinkoff.ru
```

### Проблемы с памятью

```bash
# Увеличьте лимит памяти в docker-compose.yml
# memory: 2G
```

### Очистка старых образов

```bash
docker image prune -a
```

## Полезные команды

```bash
# Вход в контейнер
docker compose exec auto-stop /bin/bash

# Просмотр переменных окружения
docker compose exec auto-stop env

# Перезагрузка конфигурации
docker compose up -d --force-recreate

# Полная очистка и перезапуск
docker compose down -v
docker compose up -d
```

## Автоматический запуск при старте сервера

Docker Compose с `restart: unless-stopped` автоматически запустит контейнер при перезагрузке сервера.

Проверка:

```bash
sudo reboot
# После перезагрузки
docker compose ps
```

## Безопасность

1. **Не коммитьте .env файл в Git**
2. **Используйте сильные пароли**
3. **Регулярно обновляйте систему**
4. **Настройте firewall**
5. **Используйте SSH ключи вместо паролей**

## Дополнительная информация

- [GitHub Setup](GITHUB_SETUP.md) - Настройка GitHub Actions
- [Server Setup](SERVER_SETUP.md) - Подробная настройка сервера
- [Telegram Bot](TELEGRAM_BOT.md) - Настройка Telegram бота
- [Troubleshooting](TROUBLESHOOTING.md) - Решение проблем
