# Быстрый старт Auto-Stop

Краткое руководство для быстрого развертывания системы на вашем сервере.

## Предварительные требования

- ✅ Сервер с Ubuntu (20.04/22.04/24.04)
- ✅ Docker и Docker Compose установлены
- ✅ Tinkoff Invest токен
- ✅ Telegram бот токен (опционально)
- ✅ GitHub аккаунт (для CI/CD)

## Варианты установки

Выберите один из двух вариантов установки:

### Вариант 1: Стандартная установка (SSH)

#### Шаг 1: Настройка GitHub

1. Создайте репозиторий `auto-stop` на GitHub (публичный)
2. Добавьте Secrets в Settings → Secrets and variables → Actions:
   - `SERVER_HOST`: IP вашего сервера
   - `SERVER_USER`: имя пользователя
   - `SERVER_PORT`: SSH порт (обычно 22 или 2222)
   - `SERVER_SSH_KEY`: ваш приватный SSH ключ

#### Шаг 2: Подготовка сервера

```bash
# Подключение к серверу
ssh user@your-server-ip -p 22

# Создание директории
sudo mkdir -p /opt/projects/auto-stop
sudo chown $USER:$USER /opt/projects/auto-stop
cd /opt/projects/auto-stop

# Клонирование репозитория (после push в GitHub)
git clone https://github.com/yourusername/auto-stop.git .
```

### Вариант 2: Установка с Tailscale VPN (рекомендуется)

Этот вариант обеспечивает безопасное подключение к серверу через VPN, даже если сервер находится за NAT или не имеет публичного IP.

#### Шаг 1: Настройка Tailscale

1. Установите Tailscale на сервер и ваш компьютер (https://tailscale.com/download)
2. Войдите в аккаунт Tailscale на обоих устройствах
3. Откройте https://login.tailscale.com/admin/settings/keys
4. Нажмите **Generate auth key**
5. Включите:
   - ✅ Reusable
   - ✅ Ephemeral
6. Скопируйте ключ (начинается с `tskey-auth-...`)
7. Узнайте Tailscale IP вашего сервера командой `tailscale ip -4`

#### Шаг 2: Настройка GitHub

1. Создайте репозиторий `auto-stop` на GitHub (публичный)
2. Добавьте Secrets в Settings → Secrets and variables → Actions:
   - `TAILSCALE_AUTH_KEY`: ваш auth key из шага 1
   - `SERVER_HOST`: ваш Tailscale IP (из команды `tailscale ip -4`)
   - `SERVER_USER`: имя пользователя на сервере
   - `SERVER_PORT`: SSH порт (обычно 22 или 2222)
   - `SERVER_SSH_KEY`: ваш приватный SSH ключ

#### Шаг 3: Подготовка сервера

```bash
# Подключитесь к серверу через Tailscale IP
ssh user@tailscale-ip -p 22

# Создайте директорию
sudo mkdir -p /opt/projects/auto-stop
sudo chown $USER:$USER /opt/projects/auto-stop
cd /opt/projects/auto-stop

# Клонируйте репозиторий (после push)
git clone https://github.com/yourusername/auto-stop.git .
```

## Общие шаги (для обоих вариантов)

### Шаг 1: Настройка окружения

```bash
# Создание .env файла
nano .env
```

Содержимое `.env`:
```env
TINKOFF_TOKEN=your_token_here
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
```

### Шаг 2: Деплой

```bash
# На вашем компьютере
cd /path/to/auto-stop

# Commit и push
git add .
git commit -m "Initial setup"
git push origin main

# Создание релиза
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions автоматически:
1. Соберет Docker образ
2. Задеплоит на ваш сервер через SSH (или Tailscale VPN)

### Шаг 3: Проверка

```bash
# На сервере
cd /opt/projects/auto-stop
docker compose ps
docker compose logs -f
```

### Шаг 4: Управление через Telegram

После запуска отправьте боту:
- `/start` - начало работы
- `/status` - статус системы
- `/positions` - текущие позиции
- `/settings` - настройки SL/TP
- `/accounts` - управление аккаунтами

### Шаг 5: Полезные команды

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

## Дополнительная информация

- [Настройка GitHub Actions](GITHUB_SETUP.md)
- [Подробное руководство по деплою](DEPLOYMENT.md)
- [Настройка Tailscale](TAILSCALE_SETUP.md)
- [Решение проблем](TROUBLESHOOTING.md)
- [Критические исправления](CRITICAL_FIXES.md)
