# Настройка Tailscale для GitHub Actions

Это руководство поможет настроить автоматический деплой через Tailscale VPN.

## Зачем нужен Tailscale?

Ваш сервер находится в локальной сети (192.168.0.144) и недоступен из интернета. Tailscale создает безопасный VPN туннель, позволяя GitHub Actions подключаться к вашему серверу.

## Шаг 1: Получение Tailscale Auth Key

### 1.1 Войдите в Tailscale Admin Console

Перейдите на: https://login.tailscale.com/admin/settings/keys

### 1.2 Создайте новый Auth Key

1. Нажмите **Generate auth key**
2. Настройте параметры:
   - ✅ **Reusable** - можно использовать многократно
   - ✅ **Ephemeral** - временные устройства
   - **Expiration**: 90 days
3. Нажмите **Generate key**
4. Скопируйте ключ (начинается с `tskey-auth-...`)

## Шаг 2: Добавление секретов в GitHub

1. Откройте ваш репозиторий на GitHub
2. Settings → Secrets and variables → Actions
3. Добавьте секреты:

### TAILSCALE_AUTH_KEY
- Name: `TAILSCALE_AUTH_KEY`
- Value: ваш auth key из шага 1

### SERVER_HOST (обновить)
- Name: `SERVER_HOST`
- Value: `100.x.x.x` (ваш Tailscale IP)

### Другие секреты (если еще не добавлены)
- `SERVER_USER`: `user`
- `SERVER_PORT`: `2222`
- `SERVER_SSH_KEY`: ваш приватный SSH ключ

## Шаг 3: Проверка

1. Commit и push изменений:
```bash
git add .
git commit -m "Add Tailscale support for deployment"
git push origin main
```

2. Создайте новый релиз:
```bash
git tag v1.0.1
git push origin v1.0.1
```

3. Проверьте GitHub Actions:
   - Перейдите в Actions
   - Найдите workflow "Build and Deploy Release"
   - Проверьте логи

## Что происходит при деплое

1. GitHub Actions подключается к Tailscale
2. Получает доступ к вашему серверу через VPN
3. Подключается по SSH к вашему серверу через Tailscale
4. Выполняет деплой

## Решение проблем

### Ошибка подключения к Tailscale
- Проверьте, что auth key правильный
- Убедитесь, что ключ не истек

### Ошибка SSH подключения
- Проверьте, что сервер доступен в Tailscale
- Проверьте SSH ключ в секретах

### Проверка Tailscale IP на сервере
```bash
tailscale ip -4
# Должен вывести ваш Tailscale IP (например: 100.x.x.x)
```

## Готово!

Теперь GitHub Actions может деплоить на ваш домашний сервер через Tailscale VPN.
