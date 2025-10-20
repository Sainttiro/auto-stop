# Быстрый старт с Tailscale

Пошаговая инструкция для развертывания Auto-Stop на домашнем сервере через Tailscale.

## Что вам понадобится

- ✅ Сервер с Ubuntu и Docker
- ✅ Tailscale установлен на сервере
- ✅ GitHub аккаунт
- ✅ Tinkoff Invest токен
- ✅ Telegram бот токен (опционально)

## Шаг 1: Получите Tailscale Auth Key

1. Откройте https://login.tailscale.com/admin/settings/keys
2. Нажмите **Generate auth key**
3. Включите:
   - ✅ Reusable
   - ✅ Ephemeral
4. Скопируйте ключ (начинается с `tskey-auth-...`)

## Шаг 2: Настройте GitHub

1. Создайте публичный репозиторий `auto-stop` на GitHub
2. Перейдите в Settings → Secrets and variables → Actions
3. Добавьте секреты:
   - `TAILSCALE_AUTH_KEY`: ваш auth key из шага 1
   - `SERVER_HOST`: ваш Tailscale IP (узнайте командой `tailscale ip -4` на сервере)
   - `SERVER_USER`: имя пользователя на сервере
   - `SERVER_PORT`: SSH порт (обычно 22 или 2222)
   - `SERVER_SSH_KEY`: ваш приватный SSH ключ

## Шаг 3: Подготовьте сервер

```bash
# Подключитесь к серверу
ssh user@your-server-ip -p 22

# Создайте директорию
sudo mkdir -p /opt/projects/auto-stop
sudo chown $USER:$USER /opt/projects/auto-stop
cd /opt/projects/auto-stop

# Клонируйте репозиторий (после push)
git clone https://github.com/yourusername/auto-stop.git .

# Создайте .env
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
# Создайте директории
mkdir -p data logs
```

## Шаг 4: Деплой

```bash
# На вашем компьютере
cd /path/to/auto-stop

# Commit и push
git add .
git commit -m "Add Tailscale deployment"
git push origin main

# Создайте релиз
git tag v1.0.1
git push origin v1.0.1
```

GitHub Actions автоматически:
1. Подключится к Tailscale
2. Соберет Docker образ
3. Задеплоит на ваш сервер через VPN

## Шаг 5: Проверка

1. Откройте GitHub → Actions
2. Дождитесь завершения workflow
3. На сервере проверьте:

```bash
docker compose ps
docker compose logs -f
```

## Готово! 🎉

Система работает и автоматически обновляется при создании новых релизов.

## Управление

```bash
# Логи
./scripts/logs.sh

# Статус
docker compose ps

# Перезапуск
docker compose restart
```

## Telegram Bot

Отправьте боту `/start` для начала работы.

## Дополнительная информация

- [Полная документация по Tailscale](TAILSCALE_SETUP.md)
- [Настройка GitHub](GITHUB_SETUP.md)
- [Развертывание](DEPLOYMENT.md)
