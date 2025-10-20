# Auto-Stop: Система автоматического управления стоп-лоссами и тейк-профитами

Система для автоматического выставления и пересчета стоп-лоссов и тейк-профитов после исполнения сделок через Tinkoff Invest API (gRPC).

## Возможности

- Автоматическое выставление SL/TP после исполнения сделки
- Пересчет уровней при изменении средней цены позиции
- Поддержка разных методов расчета для акций и фьючерсов
- Многоуровневый тейк-профит с частичным закрытием позиции
- Гибкая настройка параметров через YAML-конфигурацию
- Уведомления через Telegram
- Сохранение состояния в SQLite базе данных
- Асинхронная работа с gRPC-потоками

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

## Лицензия

MIT
