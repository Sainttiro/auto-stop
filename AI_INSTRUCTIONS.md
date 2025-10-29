# AI Instructions для Auto-Stop

## 🎯 О проекте

Auto-Stop v2.x.x - production-система автоматического управления стоп-лоссами и тейк-профитами для Tinkoff Invest API (gRPC).

**Статус:** Работает на сервере, обслуживает реальные торговые операции  
**Критичность:** ВЫСОКАЯ - ошибки могут привести к финансовым потерям  
**Текущая версия:** v2.2.1

### Основные возможности:
- ✅ Автоматическое выставление SL/TP после исполнения сделки
- ✅ Пересчет уровней при изменении средней цены позиции
- ✅ Поддержка разных методов расчета для акций и фьючерсов
- ✅ Многоуровневый тейк-профит с частичным закрытием позиции
- ✅ Мультиаккаунты с горячим переключением без перезапуска
- ✅ Интерактивное управление через Telegram бота
- ✅ Торговая статистика и аналитика

## 🏗️ Архитектура

### Модульная структура:
- `src/api/` - gRPC клиент для Tinkoff Invest API
- `src/core/` - ядро системы (потоки, ордера, позиции, риски)
- `src/strategies/` - торговые стратегии
- `src/storage/` - SQLite БД и модели
- `src/bot/` - Telegram бот и интерактивное меню настроек
- `src/analytics/` - статистика и отчеты
- `src/config/` - настройки (YAML + БД)
- `src/notifications/` - уведомления в Telegram
- `src/utils/` - утилиты (логирование, конвертеры)

### Ключевые принципы:
1. **Асинхронность** - все операции async/await
2. **Приоритет настроек** - БД → YAML → defaults
3. **Безопасность** - токены в .env, никогда в коде
4. **Логирование** - все важные события в логи
5. **Контейнеризация** - Docker для деплоя
6. **CI/CD** - GitHub Actions + Tailscale VPN

### Логика работы:
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

## 📐 Стандарты кодирования

### Python стиль:
- Python 3.10+ (используются новые возможности)
- PEP 8 compliance
- Type hints обязательны для всех функций
- Docstrings для всех публичных методов
- Async/await для всех I/O операций
- Обработка исключений для всех внешних вызовов

### Naming conventions:
- Классы: `PascalCase` (например, `RiskCalculator`)
- Функции/методы: `snake_case` (например, `calculate_levels`)
- Константы: `UPPER_SNAKE_CASE` (например, `MAX_RETRIES`)
- Приватные методы: `_leading_underscore`
- Переменные: `snake_case`

### Структура файлов:
```python
# Imports
import asyncio
from typing import Optional, Dict, List, Any

# Constants
MAX_RETRIES = 100

# Classes
class MyClass:
    """Docstring."""
    
    def __init__(self) -> None:
        """Initialize class."""
        self._private_var = None
    
    async def public_method(self, param: str) -> Dict[str, Any]:
        """
        Public method description.
        
        Args:
            param: Parameter description
            
        Returns:
            Dictionary with results
        """
        result = await self._private_method(param)
        return result
    
    async def _private_method(self, param: str) -> Dict[str, Any]:
        """Private method."""
        return {"result": param}
```

## 🔄 Рабочий процесс

### При добавлении новой функции:
1. Изучить затрагиваемые модули через `map.txt`
2. Проверить влияние на существующий функционал
3. Добавить/обновить модели БД (если нужно)
4. Реализовать функцию с type hints и docstrings
5. Добавить тесты
6. Обновить документацию
7. Обновить CHANGELOG.md с новой версией

### При исправлении ошибки:
1. Понять root cause
2. Проверить, не затронуты ли другие части
3. Исправить ошибку с минимальными изменениями
4. Добавить тест, предотвращающий регрессию
5. Обновить CRITICAL_FIXES.md (если критично)
6. Обновить CHANGELOG.md

### Версионирование:
- Major (v3.0.0) - breaking changes
- Minor (v2.1.0) - новые функции
- Patch (v2.0.1) - исправления ошибок

## ⚠️ Критические моменты

### НЕЛЬЗЯ:
- ❌ Изменять логику расчета SL/TP без тщательного тестирования
- ❌ Удалять/изменять поля в БД без миграции
- ❌ Коммитить токены или секреты
- ❌ Использовать синхронные операции в async контексте
- ❌ Игнорировать ошибки в потоках gRPC
- ❌ Использовать hardcoded значения вместо конфигурации
- ❌ Изменять формат хранения настроек без миграции

### ОБЯЗАТЕЛЬНО:
- ✅ Тестировать на минимальных суммах
- ✅ Логировать все важные операции
- ✅ Обрабатывать все исключения
- ✅ Валидировать входные данные
- ✅ Документировать изменения
- ✅ Обновлять CHANGELOG.md
- ✅ Следовать приоритету настроек: БД → YAML → defaults

## 🗺️ Навигация по проекту

### Где искать:
- **Расчет SL/TP** → `src/core/risk_calculator.py`
- **Выставление ордеров** → `src/core/order_executor.py`
- **Обработка потоков** → `src/core/stream_handler.py`
- **Управление позициями** → `src/core/position_manager.py`
- **Telegram команды** → `src/bot/bot.py`
- **Настройки через бот** → `src/bot/settings_menu.py`
- **Модели БД** → `src/storage/models.py`
- **Работа с БД** → `src/storage/database.py`
- **Статистика** → `src/analytics/statistics.py`
- **Отчеты** → `src/analytics/reports.py`

### Важные файлы:
- `map.txt` - полная карта проекта
- `plan.txt` - исходный промпт разработки
- `CHANGELOG.md` - история изменений
- `docs/CRITICAL_FIXES.md` - критические баги
- `docs/TROUBLESHOOTING.md` - решение проблем
- `docs/DEPLOYMENT.md` - инструкции по деплою
- `docs/MULTI_ACCOUNTS.md` - работа с мультиаккаунтами

## 📚 Ресурсы и документация

### Официальная документация:
- **Tinkoff Invest API:** https://developer.tbank.ru/invest/api
  - Полное описание всех методов API
  - gRPC спецификация и protobuf схемы
  - Примеры запросов и ответов

- **Python SDK (invest-python):** https://developer.tbank.ru/invest/sdk/python_sdk/faq_python
  - Официальная библиотека для работы с API
  - FAQ и решение типичных проблем
  - Best practices и примеры кода

### MCP Server Context7:
- **Context7 для invest-python:** https://context7.com/russianinvestments/invest-python
  - Контекстная документация для ИИ агентов
  - Актуальные примеры использования API
  - Помощь в понимании методов и параметров

### Использование Context7:
При работе с Tinkoff Invest API используй MCP сервер Context7 для:
- Получения актуальной документации по методам
- Примеров использования конкретных функций
- Понимания параметров и возвращаемых значений

## 🔌 Работа с MCP серверами

### Context7 для invest-python:
MCP сервер Context7 предоставляет контекстную документацию для библиотеки invest-python.

**Как использовать:**
1. Подключи MCP сервер Context7 в настройках Cline
2. При работе с API методами запрашивай документацию через Context7
3. Используй примеры кода из Context7 как референс

**Примеры запросов к Context7:**
- "Покажи пример использования OrdersService.PostOrder"
- "Как правильно подписаться на поток исполнений?"
- "Какие параметры принимает метод GetInstrumentByTicker?"

**Преимущества:**
- Актуальная документация всегда под рукой
- Примеры кода для конкретных задач
- Понимание параметров и возвращаемых значений

## 🧪 Тестирование

### Обязательные тесты:
- Unit тесты для новых функций
- Integration тесты для критичных изменений
- Тесты на граничные случаи
- Тесты на обработку ошибок

### Запуск тестов:
```bash
pytest tests/ -v --cov=src
```

## 📚 Документация

### Обновлять при изменениях:
- `CHANGELOG.md` - всегда
- `README.md` - если изменился функционал
- `docs/CRITICAL_FIXES.md` - если критичный баг
- `docs/TROUBLESHOOTING.md` - если новая проблема
- `map.txt` - если новые файлы

## 🚀 Деплой

### Процесс:
1. Commit изменений
2. Создать tag версии: `git tag v2.x.x`
3. Push: `git push origin v2.x.x`
4. GitHub Actions автоматически задеплоит

### Проверка:
```bash
# Логи
docker compose logs -f

# Статус
docker compose ps

# Перезапуск
docker compose restart
```

## 💡 Best Practices

1. **Всегда читай map.txt** перед началом работы
2. **Проверяй CRITICAL_FIXES.md** - там важная информация
3. **Используй type hints** - это помогает избежать ошибок
4. **Логируй важные события** - это упрощает отладку
5. **Тестируй на dev окружении** перед production
6. **Документируй сложную логику** - будущий ты скажет спасибо
7. **Используй async/await** - все I/O операции должны быть асинхронными
8. **Обрабатывай исключения** - особенно в gRPC потоках
9. **Валидируй входные данные** - особенно от пользователя
10. **Следуй приоритету настроек** - БД → YAML → defaults
11. **Используй Context7** - для получения актуальной документации по API

## 📞 Контакты и ресурсы

- **Репозиторий:** github.com/Sainttiro/auto-stop
- **Документация:** docs/
- **Карта проекта:** map.txt
- **Tinkoff API:** https://developer.tbank.ru/invest/api
- **Python SDK:** https://developer.tbank.ru/invest/sdk/python_sdk/faq_python
- **Context7 MCP:** https://context7.com/russianinvestments/invest-python

## 📋 Примеры кода

### Расчет SL/TP:
```python
async def calculate_levels(
    self,
    account_id: str,
    ticker: str,
    avg_price: float,
    quantity: int,
    direction: str
) -> Dict[str, Any]:
    """
    Рассчитать уровни SL/TP.
    
    Args:
        account_id: ID счета
        ticker: Тикер инструмента
        avg_price: Средняя цена позиции
        quantity: Количество лотов
        direction: Направление (LONG/SHORT)
    
    Returns:
        Словарь с уровнями SL/TP
    """
    # Получить настройки с приоритетом: БД → YAML → defaults
    settings = await self.settings_manager.get_effective_settings(
        account_id=account_id,
        ticker=ticker
    )
    
    sl_pct = settings["stop_loss_pct"]
    tp_pct = settings["take_profit_pct"]
    
    if direction == "LONG":
        sl_price = avg_price * (1 - sl_pct / 100)
        tp_price = avg_price * (1 + tp_pct / 100)
    else:  # SHORT
        sl_price = avg_price * (1 + sl_pct / 100)
        tp_price = avg_price * (1 - tp_pct / 100)
    
    return {
        "sl_price": sl_price,
        "tp_price": tp_price,
        "settings_used": settings
    }
```

### Обработка исключений:
```python
try:
    result = await self.api_client.post_order(
        figi=figi,
        quantity=quantity,
        price=price,
        direction=direction,
        order_type=OrderType.LIMIT
    )
    logger.info(f"Order placed: {result.order_id}")
    return result
except asyncio.CancelledError:
    logger.warning("Order placement cancelled")
    raise
except Exception as e:
    logger.error(f"Failed to place order: {e}")
    # Retry logic or fallback
    return None
```

### Работа с БД:
```python
async def save_position(self, position: Position) -> None:
    """
    Сохранить позицию в БД.
    
    Args:
        position: Объект позиции
    """
    try:
        async with self.session_maker() as session:
            async with session.begin():
                session.add(position)
                await session.commit()
        logger.info(f"Position saved: {position.ticker} {position.direction}")
    except Exception as e:
        logger.error(f"Failed to save position: {e}")
        raise
```

### Telegram бот:
```python
async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /status.
    
    Args:
        update: Telegram update
        context: Callback context
    """
    try:
        positions = await self.position_manager.get_open_positions()
        
        if not positions:
            await update.message.reply_text("📊 Нет открытых позиций")
            return
        
        message = "📊 <b>Текущие позиции:</b>\n\n"
        
        for pos in positions:
            message += (
                f"<b>{pos.ticker}</b>: {pos.direction} {pos.quantity} лотов\n"
                f"💰 Средняя цена: {pos.average_price:.2f}\n"
                f"🛑 Стоп-лосс: {pos.stop_loss_price:.2f}\n"
                f"🎯 Тейк-профит: {pos.take_profit_price:.2f}\n\n"
            )
        
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in status command: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
```

### Пример использования invest-python с Context7:
```python
from tinkoff.invest import Client, OrderDirection, OrderType
from tinkoff.invest.utils import quotation_to_decimal

async def place_order_example():
    """
    Пример выставления ордера с использованием invest-python.
    
    Документация: https://context7.com/russianinvestments/invest-python
    """
    async with Client(token=TOKEN) as client:
        # Получение информации об инструменте
        instrument = await client.instruments.get_instrument_by(
            id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_TICKER,
            class_code="TQBR",
            id="SBER"
        )
        
        # Выставление ордера
        order_response = await client.orders.post_order(
            instrument_id=instrument.instrument.uid,
            quantity=10,
            price=quotation_to_decimal(instrument.instrument.min_price_increment),
            direction=OrderDirection.ORDER_DIRECTION_BUY,
            account_id=ACCOUNT_ID,
            order_type=OrderType.ORDER_TYPE_LIMIT,
            order_id=str(uuid.uuid4())
        )
        
        return order_response
