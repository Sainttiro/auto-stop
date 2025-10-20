# Быстрый старт Auto-Stop

Краткое руководство для быстрого развертывания системы на вашем сервере.

## Предварительные требования

- ✅ Сервер с Ubuntu 24.04 (у вас уже есть)
- ✅ Docker установлен (у вас уже есть)
- ✅ Tinkoff Invest токен
- ✅ Telegram бот токен (опционально)

## Шаг 1: На сервере

```bash
# Подключение к серверу
ssh user@your-server-ip -p 22

# Создание директории
sudo mkdir -p /opt/projects/auto-stop
sudo chown $USER:$USER /opt/projects/auto-stop
cd /opt/projects/auto-stop

# Клонирование репозитория (после push в GitHub)
git clone https://github.com/yourusername/auto-stop.git .

# Создание .env файла
nano .env
```

Содержимое `.env`:
```env
TINKOFF_TOKEN=your_token
ACCOUNT_ID=your_account_id
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
GITHUB_REPOSITORY=yourusername/auto-stop
VERSION=latest
LOG_LEVEL=INFO
```

```bash
# Создание директорий
mkdir -p data logs

# Первый запуск (локально)
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d

# Проверка
docker compose logs -f
```

## Шаг 2: Настройка GitHub

1. Создайте репозиторий `auto-stop` на GitHub (публичный)
2. Добавьте Secrets:
   - `SERVER_HOST`: IP вашего сервера (или Tailscale IP)
   - `SERVER_USER`: имя пользователя
   - `SERVER_PORT`: SSH порт (обычно 22 или 2222)
   - `SERVER_SSH_KEY`: ваш приватный SSH ключ

## Шаг 3: Деплой

```bash
# На вашем компьютере
cd /path/to/auto-stop
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/auto-stop.git
git push -u origin main

# Создание релиза
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions автоматически задеплоит на сервер!

## Управление через Telegram

После запуска отправьте боту:
- `/start` - начало работы
- `/status` - статус системы
- `/positions` - текущие позиции

## Полезные команды

```bash
# Логи
./scripts/logs.sh

# Обновление
./scripts/update.sh

# Бэкап
./scripts/backup.sh

# Статус
docker compose ps
```

## Готово! 🎉

Система работает и автоматически выставляет SL/TP на ваши позиции.
