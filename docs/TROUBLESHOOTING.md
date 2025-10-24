# 🔧 Решение проблем

Руководство по диагностике и решению проблем в системе Auto-Stop.

## 📋 Содержание

- [Быстрая диагностика](#быстрая-диагностика)
- [Проблемы с запуском](#проблемы-с-запуском)
- [Проблемы с ордерами](#проблемы-с-ордерами)
- [Проблемы с позициями](#проблемы-с-позициями)
- [Проблемы с API](#проблемы-с-api)
- [Проблемы с Telegram](#проблемы-с-telegram)
- [Проблемы с Docker](#проблемы-с-docker)
- [Логи и диагностика](#логи-и-диагностика)
- [Аварийное восстановление](#аварийное-восстановление)

---

## 🚀 Быстрая диагностика

### Проверка статуса системы

```bash
# Статус контейнера
docker compose ps

# Последние логи
docker compose logs --tail=50

# Логи в реальном времени
docker compose logs -f
```

### Проверка через Telegram

```
/status    - Статус системы
/positions - Текущие позиции
/logs      - Последние логи
```

### Признаки нормальной работы

✅ Контейнер в статусе `Up`
✅ В логах нет ошибок `ERROR` или `CRITICAL`
✅ Telegram бот отвечает на команды
✅ После сделок выставляются SL/TP

---

## 🔴 Проблемы с запуском

### Контейнер не запускается

**Симптомы:**
```bash
docker compose ps
# auto-stop   Exit 1
```

**Диагностика:**
```bash
# Проверить логи
docker compose logs

# Проверить .env файл
cat .env

# Проверить конфигурацию
cat config/config.yaml
```

**Возможные причины:**

#### 1. Отсутствует токен API

**Ошибка в логах:**
```
ValueError: TINKOFF_TOKEN not found in environment
```

**Решение:**
```bash
# Проверить .env
nano .env

# Должна быть строка:
TINKOFF_TOKEN=your_token_here

# Перезапустить
docker compose restart
```

#### 2. Неправильный формат конфигурации

**Ошибка в логах:**
```
yaml.scanner.ScannerError: mapping values are not allowed here
```

**Решение:**
```bash
# Проверить синтаксис YAML
cat config/config.yaml

# Убедиться в правильных отступах (2 пробела)
# Перезапустить
docker compose restart
```

#### 3. Проблемы с правами доступа

**Ошибка в логах:**
```
PermissionError: [Errno 13] Permission denied: '/app/data/database.db'
```

**Решение:**
```bash
# Установить правильные права
sudo chown -R $USER:$USER data/ logs/
chmod -R 755 data/ logs/

# Перезапустить
docker compose restart
```

---

## 📝 Проблемы с ордерами

### SL/TP не выставляются

**Симптомы:**
- Сделка исполнена
- В логах нет записей о выставлении ордеров
- В Telegram нет уведомлений об ордерах

**Диагностика:**

```bash
# Проверить логи на наличие ошибок
docker compose logs | grep -i "error\|critical"

# Проверить обработку сделок
docker compose logs | grep -i "trade"
```

**Возможные причины:**

#### 1. Система на старой версии (< v2.0.10)

**Проверка:**
```bash
git describe --tags
```

**Решение:**
```bash
# Обновиться до последней версии
git pull origin main
git checkout v2.0.10
docker compose down
docker compose up -d
```

#### 2. Ошибка конвертации в лоты

**Ошибка в логах:**
```
ERROR: Failed to get lot size for FIGI
```

**Решение:**
```bash
# Очистить кэш инструментов
docker compose exec auto-stop rm -f /app/data/instrument_cache.db

# Перезапустить
docker compose restart
```

#### 3. Недостаточно средств

**Ошибка в логах:**
```
NOT_ENOUGH_BALANCE
```

**Решение:**
- Проверить баланс в приложении Tinkoff
- Убедиться, что достаточно средств для маржинальных требований
- Уменьшить размер позиций

### Ордера выставляются на неправильное количество

**Симптомы:**
- Позиция: 10 акций
- SL ордер: 100 акций

**Причина:**
Используется версия < v2.0.0 с багом конвертации лотов

**Решение:**
```bash
# СРОЧНО обновиться до v2.0.10+
git checkout v2.0.10
docker compose down
docker compose up -d

# Отменить все активные ордера вручную в приложении Tinkoff
# Дождаться новых сделок для корректного выставления
```

### Старые ордера не отменяются

**Симптомы:**
- Позиция уменьшилась
- Старые SL/TP остались активными

**Причина:**
Версия < v1.2.0 без отслеживания изменений позиции

**Решение:**
```bash
# Обновиться до v2.0.10+
git checkout v2.0.10
docker compose restart

# Вручную отменить старые ордера в приложении Tinkoff
```

---

## 📊 Проблемы с позициями

### Ручные позиции без SL/TP

**Симптомы:**
- Вы открыли позицию вручную через приложение Tinkoff
- SL/TP не выставились автоматически
- В логах нет записей о новой позиции
- Команда `/positions` показывает позицию, но без SL/TP

**Диагностика:**
```bash
# Проверить логи на наличие записей о позиции
docker compose logs | grep -i "позиция\|position"

# Проверить версию системы
git describe --tags
```

**Возможные причины:**

#### 1. Используется версия < v2.1.6

**Решение:**
```bash
# Обновиться до v2.1.6+
git pull origin main
git checkout v2.1.6
docker compose down
docker compose up -d
```

#### 2. Временная проблема с API

**Решение:**
```bash
# Перезапустить систему
docker compose restart

# Проверить работу:
# 1. Открыть новую позицию вручную
# 2. Подождать 5-10 секунд
# 3. Проверить логи и наличие SL/TP
```

#### 3. Для существующих позиций без SL/TP

**Решение:**
- Закрыть позицию вручную
- Открыть заново после обновления системы до v2.1.6+
- Проверить, что SL/TP выставились автоматически

### Появились незапланированные SHORT позиции

**Симптомы:**
- В портфеле SHORT позиции, которые не открывались вручную
- Большие убытки

**Причина:**
Критический баг в версиях < v2.0.0

**СРОЧНЫЕ действия:**

1. **Остановить систему:**
```bash
docker compose down
```

2. **Закрыть SHORT позиции вручную:**
- Открыть приложение Tinkoff
- Найти SHORT позиции
- Закрыть рыночными ордерами

3. **Обновить систему:**
```bash
git checkout v2.0.10
docker compose up -d
```

4. **Проверить логи:**
```bash
docker compose logs | grep -i "short\|reversal"
```

### Позиции не отслеживаются

**Симптомы:**
- `/positions` показывает пустой список
- Позиции есть в приложении Tinkoff

**Причина:**
Система отслеживает только позиции, открытые ПОСЛЕ запуска

**Решение:**
```bash
# Это нормальное поведение!
# Система НЕ подхватывает старые позиции

# Для защиты старых позиций:
# 1. Закрыть их вручную
# 2. Открыть заново после запуска системы
```

### Средняя цена рассчитывается неправильно

**Симптомы:**
- Средняя цена в системе отличается от Tinkoff
- SL/TP на неправильных уровнях

**Диагностика:**
```bash
# Проверить логи расчета средней цены
docker compose logs | grep -i "average price"
```

**Возможные причины:**

#### 1. Частичное исполнение не обрабатывается

**Версия:** < v2.0.9

**Решение:**
```bash
git checkout v2.0.10
docker compose restart
```

#### 2. Позиция открыта до запуска системы

**Решение:**
- Закрыть позицию
- Открыть заново после запуска системы

---

## 🌐 Проблемы с API

### Ошибки подключения к API

**Ошибка в логах:**
```
UNAVAILABLE: Socket closed
```

**Причина:**
Временный разрыв соединения с API Tinkoff

**Решение:**
```bash
# Система автоматически переподключится
# Проверить логи переподключения
docker compose logs | grep -i "reconnect"

# Если не переподключается > 5 минут:
docker compose restart
```

### Rate limit exceeded

**Ошибка в логах:**
```
RESOURCE_EXHAUSTED: Rate limit exceeded
```

**Причина:**
Слишком много запросов к API

**Решение:**
```bash
# Подождать 1 минуту
# Система автоматически возобновит работу

# Если проблема повторяется:
# Уменьшить частоту запросов в конфигурации
```

### Неправильный токен

**Ошибка в логах:**
```
UNAUTHENTICATED: Invalid token
```

**Решение:**
```bash
# Проверить токен в .env
cat .env | grep TINKOFF_TOKEN

# Получить новый токен:
# 1. Открыть https://www.tinkoff.ru/invest/settings/api/
# 2. Создать новый токен
# 3. Обновить .env
nano .env

# Перезапустить
docker compose restart
```

---

## 💬 Проблемы с Telegram

### Бот не отвечает

**Диагностика:**
```bash
# Проверить логи бота
docker compose logs | grep -i "telegram"

# Проверить токен бота
cat .env | grep TELEGRAM_BOT_TOKEN
```

**Возможные причины:**

#### 1. Неправильный токен бота

**Решение:**
```bash
# Получить токен от @BotFather
# Обновить .env
nano .env
# TELEGRAM_BOT_TOKEN=your_bot_token

docker compose restart
```

#### 2. Неправильный chat_id

**Решение:**
```bash
# Получить chat_id:
# 1. Написать боту /start
# 2. Открыть https://api.telegram.org/bot<TOKEN>/getUpdates
# 3. Найти "chat":{"id":123456789}

# Обновить .env
nano .env
# TELEGRAM_CHAT_ID=123456789

docker compose restart
```

### Команды не работают

**Симптомы:**
- Бот отвечает на /start
- Другие команды не работают

**Решение:**
```bash
# Проверить версию
git describe --tags

# Обновиться до v2.0.10+
git checkout v2.0.10
docker compose restart
```

### Уведомления не приходят

**Проверка конфигурации:**
```bash
cat config/config.yaml | grep -A 10 "notifications"
```

**Решение:**
```yaml
# В config/config.yaml должно быть:
telegram:
  notifications:
    - system_start
    - trade_executed
    - order_placed
    - errors
```

---

## 🐳 Проблемы с Docker

### Образ не скачивается

**Ошибка:**
```
Error response from daemon: manifest unknown
```

**Решение:**
```bash
# Проверить имя образа в docker-compose.yml
cat docker-compose.yml | grep image

# Должно быть:
# image: ghcr.io/sainttiro/auto-stop:latest

# Пересобрать локально
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d
```

### Старый образ используется после перезапуска

**Симптомы:**
- Система работала нормально
- После перезагрузки сервера или Docker перестали работать некоторые функции
- Команды в Telegram боте не отвечают (например, `/settings`)
- Код был обновлен, но изменения не применились

**Причина:**
Docker использует локальный кэш образов при перезапуске и не проверяет наличие новых версий.

**Решение:**
```bash
# Добавить pull_policy: always в docker-compose.yml
services:
  auto-stop:
    image: ghcr.io/${GITHUB_REPOSITORY}:${VERSION:-latest}
    pull_policy: always  # Всегда проверять наличие новой версии

# Применить изменения
docker compose up -d

# Или использовать скрипт обновления
./scripts/update.sh
```

**Профилактика:**
- Всегда используйте `pull_policy: always` в продакшен-окружении
- Создавайте теги для важных изменений: `git tag v2.x.x && git push origin v2.x.x`
- Используйте скрипт `./scripts/update.sh` для обновления

### Контейнер постоянно перезапускается

**Диагностика:**
```bash
docker compose ps
# auto-stop   Restarting

docker compose logs --tail=100
```

**Причина:**
Критическая ошибка при запуске

**Решение:**
```bash
# Остановить автоперезапуск
docker compose down

# Запустить без автоперезапуска для диагностики
docker compose run --rm auto-stop

# Исправить ошибку
# Запустить нормально
docker compose up -d
```

### Нет места на диске

**Ошибка:**
```
no space left on device
```

**Решение:**
```bash
# Очистить старые образы
docker image prune -a

# Очистить старые логи
find logs/ -name "*.log" -mtime +30 -delete

# Очистить старые бэкапы
find backups/ -name "*.tar.gz" -mtime +30 -delete
```

---

## 📋 Логи и диагностика

### Просмотр логов

```bash
# Последние 100 строк
docker compose logs --tail=100

# В реальном времени
docker compose logs -f

# Только ошибки
docker compose logs | grep -i "error\|critical"

# Сохранить в файл
docker compose logs > debug.log
```

### Уровни логирования

```yaml
# В config/config.yaml
logging:
  level: "DEBUG"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

**Рекомендации:**
- **DEBUG**: Для диагностики проблем
- **INFO**: Для нормальной работы
- **WARNING**: Для продакшена

### Важные события в логах

```bash
# Исполнение сделок
docker compose logs | grep "Получено исполнение сделки"

# Выставление ордеров
docker compose logs | grep "Выставлены ордера"

# Ошибки API
docker compose logs | grep "UNAVAILABLE\|UNAUTHENTICATED"

# Переподключения
docker compose logs | grep "Повторное подключение"
```

---

## 🆘 Аварийное восстановление

### Система полностью не работает

**Шаги:**

1. **Остановить систему:**
```bash
docker compose down
```

2. **Сохранить логи:**
```bash
docker compose logs > emergency_logs.txt
```

3. **Проверить позиции вручную:**
- Открыть приложение Tinkoff
- Проверить все позиции
- Отменить подозрительные ордера

4. **Откатиться на стабильную версию:**
```bash
git checkout v2.0.10
docker compose up -d
```

5. **Проверить работу:**
```bash
docker compose logs -f
```

### Потеря данных БД

**Симптомы:**
```
sqlite3.OperationalError: no such table: positions
```

**Решение:**
```bash
# Остановить систему
docker compose down

# Удалить поврежденную БД
rm data/database.db

# Запустить систему (создаст новую БД)
docker compose up -d

# Система начнет отслеживать новые позиции
```

### Откат к предыдущей версии

```bash
# Посмотреть доступные версии
git tag

# Откатиться на конкретную версию
git checkout v2.0.9

# Пересобрать
docker compose down
docker compose up -d

# Проверить
docker compose logs -f
```

---

## 📞 Получение помощи

### Перед обращением

Подготовьте:

1. **Версию системы:**
```bash
git describe --tags
```

2. **Логи:**
```bash
docker compose logs --tail=200 > logs.txt
# Удалите токены из logs.txt!
```

3. **Конфигурацию:**
```bash
cat config/config.yaml > config.txt
# Удалите чувствительные данные!
```

4. **Описание проблемы:**
- Что делали
- Что ожидали
- Что произошло
- Когда началось

### Куда обращаться

1. **GitHub Issues:**
   - https://github.com/Sainttiro/auto-stop/issues
   - Приложите логи и конфигурацию
   - Опишите шаги для воспроизведения

2. **Telegram бот:**
   - `/reportbug` - отправить отчет об ошибке
   - Опишите проблему детально

3. **Документация:**
   - [CRITICAL_FIXES.md](CRITICAL_FIXES.md) - критические баги
   - [CHANGELOG.md](../CHANGELOG.md) - история изменений
   - [README.md](../README.md) - общая информация

---

## ✅ Чеклист здоровья системы

Регулярно проверяйте:

- [ ] Контейнер в статусе `Up`
- [ ] Нет ошибок в логах
- [ ] Telegram бот отвечает
- [ ] SL/TP выставляются после сделок
- [ ] Количество в ордерах совпадает с позицией
- [ ] Нет незапланированных SHORT позиций
- [ ] Версия системы v2.0.10+
- [ ] Достаточно места на диске
- [ ] Логи не превышают 100MB

---

Последнее обновление: 24.10.2025
