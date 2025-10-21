# Auto-Stop: Система автоматического управления стоп-лоссами и тейк-профитами

[![Version](https://img.shields.io/badge/version-v2.0.10-blue.svg)](https://github.com/Sainttiro/auto-stop/releases/tag/v2.0.10)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

Система для автоматического выставления и пересчета стоп-лоссов и тейк-профитов после исполнения сделок через Tinkoff Invest API (gRPC).

> **⚠️ ВАЖНО**: Используйте только версию **v2.0.10+**. Предыдущие версии содержат критические баги, которые могут привести к финансовым потерям. См. [Критические исправления](docs/CRITICAL_FIXES.md).

## 🎯 Возможности

### Основные функции
- ✅ Автоматическое выставление SL/TP после исполнения сделки
- ✅ Пересчет уровней при изменении средней цены позиции
- ✅ Поддержка разных методов расчета для акций и фьючерсов
- ✅ Многоуровневый тейк-профит с частичным закрытием позиции
- ✅ **Корректная обработка частично исполненных ордеров** (v2.0.9+)
- ✅ **Правильная конвертация акций в лоты** (v2.0.0+)
- ✅ **Защита от переворота позиций** (v1.2.0+)

### Управление
- ✅ **Мультиаккаунты с горячим переключением** 🔥 [Подробнее](docs/MULTI_ACCOUNTS.md)
- ✅ Гибкая настройка параметров через YAML-конфигурацию
- ✅ Интерактивный Telegram бот для управления
- ✅ Торговая статистика и аналитика (v2.0.1+)

### Надежность
- ✅ Сохранение состояния в SQLite базе данных
- ✅ Асинхронная работа с gRPC-потоками
- ✅ Автоматическое переподключение при разрывах (до 100 попыток)
- ✅ Уведомления через Telegram
- ✅ Docker контейнеризация с автоматическим деплоем

## Требования

- Python 3.10+
- Токен доступа к Tinkoff Invest API
- Опционально: токен Telegram бота для уведомлений

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/auto-stop.git
cd auto-stop
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` на основе `.env.example`:
```bash
cp .env.example .env
```

4. Отредактируйте `.env`, добавив токен Tinkoff API и опционально токен Telegram бота:
```
TINKOFF_TOKEN=your_tinkoff_token_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

5. Настройте параметры в файлах `config/config.yaml` и `config/instruments.yaml`

## Конфигурация

### Основная конфигурация (`config/config.yaml`)

```yaml
api:
  token_env: "TINKOFF_TOKEN"  # Имя переменной окружения с токеном API
  app_name: "AutoStopSystem"
  
default_settings:
  stocks:
    stop_loss_pct: 2.0        # 2% стоп-лосс
    take_profit_pct: 5.0      # 5% тейк-профит
  futures:
    stop_loss_pct: 2.0        # 2% стоп-лосс (новый подход - в процентах)
    take_profit_pct: 5.0      # 5% тейк-профит (новый подход - в процентах)
    stop_loss_steps: 10       # 10 шагов цены (для обратной совместимости)
    take_profit_steps: 30     # 30 шагов цены (для обратной совместимости)

multi_take_profit:
  enabled: false              # По умолчанию отключено
  levels:
    - level_pct: 1.0          # +1% от средней цены
      volume_pct: 25          # Закрыть 25% позиции
    - level_pct: 2.0          # +2% от средней цены
      volume_pct: 25          # Закрыть 25% позиции
    - level_pct: 3.0          # +3% от средней цены
      volume_pct: 50          # Закрыть 50% позиции

telegram:
  bot_token_env: "TELEGRAM_BOT_TOKEN"
  chat_id_env: "TELEGRAM_CHAT_ID"
  notifications:
    - trade_executed          # Уведомления об исполнении сделок
    - order_placed            # Уведомления о выставлении ордеров
    - stop_triggered          # Уведомления о срабатывании стопов
    - errors                  # Уведомления об ошибках

logging:
  level: "INFO"               # Уровень логирования
  file: "logs/system.log"     # Файл для логов
  max_bytes: 10485760         # 10MB максимальный размер файла
  backup_count: 5             # Количество файлов ротации

# ID счета в Tinkoff Invest
account_id: ""                # Заполнить своим ID счета
```

### Конфигурация инструментов (`config/instruments.yaml`)

```yaml
instruments:
  # Акции
  SBER:
    type: stock
    stop_loss_pct: 1.5        # Индивидуальный стоп-лосс 1.5%
    take_profit_pct: 4.0      # Индивидуальный тейк-профит 4%
    
  GAZP:
    type: stock
    stop_loss_pct: 2.5        # Индивидуальный стоп-лосс 2.5%
    take_profit_pct: 6.0      # Индивидуальный тейк-профит 6%
    
  # Фьючерсы
  SiH5:  # Фьючерс на USD/RUB
    type: futures
    stop_loss_pct: 1.0        # 1% стоп-лосс (новый подход - в процентах)
    take_profit_pct: 2.5      # 2.5% тейк-профит (новый подход - в процентах)
    multi_tp:                 # Индивидуальная настройка многоуровневого TP
      enabled: true
      levels:
        - level_pct: 0.5      # +0.5% от средней цены
          volume_pct: 30      # Закрыть 30% позиции
        - level_pct: 1.0      # +1% от средней цены
          volume_pct: 30      # Закрыть 30% позиции
        - level_pct: 1.5      # +1.5% от средней цены
          volume_pct: 40      # Закрыть 40% позиции
          
  BRJ5:  # Фьючерс на нефть Brent (старый подход для обратной совместимости)
    type: futures
    stop_loss_steps: 20       # 20 шагов цены
    take_profit_steps: 50     # 50 шагов цены
```

## Запуск

```bash
python -m src.main
```

С указанием путей к файлам конфигурации:

```bash
python -m src.main --config path/to/config.yaml --instruments path/to/instruments.yaml
```

## Архитектура

### Основные компоненты

- **API Client** - Обертка над AsyncClient из invest-python для работы с API
- **Stream Handler** - Обработка gRPC-потоков (исполнения сделок, изменения позиций)
- **Position Manager** - Управление позициями и расчет средней цены
- **Risk Calculator** - Расчет уровней SL/TP
- **Order Executor** - Выставление и отмена ордеров
- **Стратегии** - Реализация логики для разных типов инструментов
- **Database** - Хранение состояния в SQLite
- **Telegram Notifier** - Отправка уведомлений

### Логика работы

1. **Инициализация**
   - Загрузка конфигурации из YAML
   - Подключение к Tinkoff Invest API через gRPC
   - Инициализация SQLite базы данных
   - Восстановление состояния из БД

2. **Подписка на события**
   - Подписка на поток исполнений сделок (OrdersStreamService)
   - Подписка на изменения позиций (OperationsStreamService)
   - Асинхронная обработка событий

3. **Обработка исполнения сделки**
   ```
   Событие: Сделка исполнена
   ↓
   Position Manager: Обновить позицию и среднюю цену
   ↓
   Risk Calculator: Рассчитать новые уровни SL/TP
   ↓
   Order Executor: Отменить старые SL/TP (если есть)
   ↓
   Order Executor: Выставить новые SL/TP
   ↓
   Database: Сохранить состояние
   ↓
   Telegram: Отправить уведомление
   ```

4. **Многоуровневый тейк-профит**
   ```
   При достижении TP уровня 1:
   ↓
   Multi-TP Strategy: Рассчитать объем частичного закрытия
   ↓
   Order Executor: Выставить ордер на частичное закрытие
   ↓
   После исполнения:
   ↓
   Position Manager: Обновить количество лотов
   ↓
   Risk Calculator: Пересчитать оставшиеся уровни
   ↓
   Order Executor: Перевыставить SL и оставшиеся TP
   ```

## 📚 Документация

- [CHANGELOG.md](CHANGELOG.md) - История изменений
- [docs/CRITICAL_FIXES.md](docs/CRITICAL_FIXES.md) - **Критические исправления (ОБЯЗАТЕЛЬНО К ПРОЧТЕНИЮ)**
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - Решение проблем
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - Развертывание на сервере
- [docs/MULTI_ACCOUNTS.md](docs/MULTI_ACCOUNTS.md) - Работа с несколькими счетами
- [docs/QUICKSTART.md](docs/QUICKSTART.md) - Быстрый старт
- [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md) - Настройка GitHub Actions
- [docs/TAILSCALE_SETUP.md](docs/TAILSCALE_SETUP.md) - Настройка Tailscale VPN

## 🔴 Критические исправления

### v2.0.10 (Текущая версия)
- ✅ Исправлена ошибка datetime при обработке сделок
- ✅ Все критические баги исправлены

### v2.0.9
- ✅ Исправлена обработка частично исполненных ордеров
- ⚠️ Ранее: система защищала только первую часть ордера!

### v2.0.0
- ✅ Исправлена конвертация акций в лоты
- ⚠️ Ранее: ордера выставлялись на 10x-100x больше!

### v1.2.0
- ✅ Предотвращение переворота позиций
- ⚠️ Ранее: могли создаваться незапланированные SHORT позиции!

**Подробнее:** [docs/CRITICAL_FIXES.md](docs/CRITICAL_FIXES.md)

## ⚠️ Важные предупреждения

1. **Используйте только v2.0.10+** - предыдущие версии опасны!
2. **Система НЕ подхватывает старые позиции** - только новые после запуска
3. **Тестируйте на минимальных суммах** перед реальной торговлей
4. **Регулярно проверяйте логи** и состояние позиций
5. **Не оставляйте систему без присмотра** надолго

## 🚀 Быстрый старт

### Минимальные требования
- Docker и Docker Compose
- Tinkoff Invest токен
- Telegram бот (опционально)

### Установка

```bash
# Клонировать репозиторий
git clone https://github.com/Sainttiro/auto-stop.git
cd auto-stop

# Переключиться на стабильную версию
git checkout v2.0.10

# Создать .env файл
cp .env.example .env
nano .env  # Добавить токены

# Запустить
docker compose up -d

# Проверить логи
docker compose logs -f
```

Подробнее: [docs/QUICKSTART.md](docs/QUICKSTART.md)

## 📊 Telegram команды

### Основные
- `/start` - Начало работы
- `/status` - Статус системы
- `/positions` - Текущие позиции
- `/help` - Справка по командам

### Статистика (v2.0.1+)
- `/stats [период] [год]` - Торговая статистика
  - Примеры: `/stats`, `/stats week`, `/stats month 2024`
- `/stats_instrument <ticker> [период]` - Статистика по инструменту
  - Примеры: `/stats_instrument SBER`, `/stats_instrument GAZP week`

### Мультиаккаунты (v1.1.0+)
- `/accounts` - Список всех счетов
- `/current_account` - Текущий активный счет
- `/add_account <name> <token> <account_id> [описание]` - Добавить счет
- `/switch_account <name>` - Переключить счет (без перезапуска!)
- `/remove_account <name>` - Удалить счет

## 🛠 Управление системой

### Через Docker

```bash
# Запуск
docker compose up -d

# Остановка
docker compose down

# Перезапуск
docker compose restart

# Логи
docker compose logs -f

# Статус
docker compose ps
```

### Через скрипты

```bash
# Просмотр логов
./scripts/logs.sh [количество_строк]

# Обновление системы
./scripts/update.sh

# Резервное копирование
./scripts/backup.sh

# Деплой на сервер
./scripts/deploy.sh
```

## 🔒 Безопасность

- ✅ Токены хранятся в переменных окружения (.env)
- ✅ Токены мультиаккаунтов в БД
- ✅ .env не коммитится в Git (.gitignore)
- ✅ SSH ключи для GitHub Actions
- ✅ Tailscale VPN для безопасного доступа к серверу
- ⚠️ **Никогда не публикуйте токены в открытом доступе!**

## 🐛 Решение проблем

### Система не работает?

1. **Проверьте версию:**
   ```bash
   git describe --tags
   # Должно быть v2.0.10 или выше
   ```

2. **Проверьте логи:**
   ```bash
   docker compose logs --tail=100
   ```

3. **Проверьте статус:**
   ```bash
   docker compose ps
   # Должно быть: Up
   ```

4. **Обратитесь к документации:**
   - [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - Подробное руководство
   - [CRITICAL_FIXES.md](docs/CRITICAL_FIXES.md) - Известные проблемы

### Появились SHORT позиции?

**СРОЧНО:**
1. Остановите систему: `docker compose down`
2. Закройте SHORT позиции вручную в приложении Tinkoff
3. Обновитесь до v2.0.10: `git checkout v2.0.10`
4. Запустите систему: `docker compose up -d`

Подробнее: [docs/CRITICAL_FIXES.md](docs/CRITICAL_FIXES.md#v200---конвертация-акций-в-лоты)

## 📈 Производительность

- **Задержка обработки сделки:** < 1 секунда
- **Время выставления SL/TP:** 1-2 секунды
- **Переподключение при разрыве:** автоматическое, до 100 попыток
- **Переключение между счетами:** 5-10 секунд (без перезапуска)
- **Потребление памяти:** ~256MB (резервация), до 1GB (лимит)
- **Потребление CPU:** 0.5-2 ядра

## 🤝 Вклад в проект

Приветствуются:
- Отчеты об ошибках (GitHub Issues)
- Предложения по улучшению
- Pull requests с исправлениями
- Документация и примеры

## ⚖️ Отказ от ответственности

**ВАЖНО:**

- Эта система управляет реальными деньгами
- Разработчик НЕ несет ответственности за финансовые потери
- Используйте систему на свой страх и риск
- Всегда тестируйте на минимальных суммах
- Регулярно проверяйте работу системы
- Не оставляйте систему без присмотра

## 📄 Лицензия

MIT

---

**Текущая версия:** v2.0.10 (21.10.2025)

**Статус:** ✅ Стабильная (все критические баги исправлены)

**Поддержка:** [GitHub Issues](https://github.com/Sainttiro/auto-stop/issues)
