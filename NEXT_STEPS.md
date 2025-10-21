# Следующие шаги для завершения реализации

## ✅ Что уже реализовано (85%)

### Инфраструктура
- База данных (GlobalSettings, InstrumentSettings)
- SettingsManager с CRUD и валидацией
- Telegram меню (1200+ строк, 18 состояний)

### Функционал
- Глобальные настройки SL/TP
- Настройки инструментов SL/TP
- Multi-TP: включение/выключение, добавление уровней
- Валидация всех вводов
- Приоритет настроек

---

## 📋 Что осталось сделать (15%)

### 1. Дополнить Multi-TP функционал (2-3 часа)

#### Добавить в `src/bot/settings_menu.py`:

**Редактирование уровня:**
```python
async def edit_level_select(self, update, context):
    """Показать список уровней для редактирования"""
    # Получить уровни
    # Показать кнопки с уровнями
    # Callback: edit_level_{index}

async def edit_level_start(self, update, context, level_index):
    """Начать редактирование уровня"""
    # Показать текущие значения
    # Запросить новый level_pct

async def edit_level_price_save(self, update, context):
    """Сохранить новый level_pct"""
    # Валидация
    # Запросить volume_pct

async def edit_level_volume_save(self, update, context):
    """Сохранить новый volume_pct"""
    # Валидация
    # Обновить уровень
    # Проверить сумму = 100%
```

**Удаление уровня:**
```python
async def delete_level_select(self, update, context):
    """Показать список уровней для удаления"""
    # Получить уровни
    # Показать кнопки с уровнями
    # Callback: delete_level_{index}

async def delete_level_confirm(self, update, context, level_index):
    """Подтверждение удаления"""
    # Показать уровень
    # Кнопки: Да/Нет

async def delete_level_execute(self, update, context, level_index):
    """Удалить уровень"""
    # Удалить из списка
    # Сохранить
    # Показать обновленное меню
```

**Обновить обработчик callback:**
```python
# В handle_callback_full добавить:
elif data == "global_multi_tp":
    return await self.show_multi_tp_menu(update, context, is_global=True)

elif data.startswith("inst_multi_tp_"):
    ticker = data.replace("inst_multi_tp_", "")
    return await self.show_multi_tp_menu(update, context, is_global=False, ticker=ticker)

elif data == "toggle_global_multi_tp":
    return await self.toggle_multi_tp(update, context, is_global=True)

elif data.startswith("toggle_inst_multi_tp_"):
    ticker = data.replace("toggle_inst_multi_tp_", "")
    return await self.toggle_multi_tp(update, context, is_global=False, ticker=ticker)

elif data == "add_global_level":
    return await self.add_level_start(update, context)

elif data.startswith("add_inst_level_"):
    return await self.add_level_start(update, context)
```

---

### 2. Интеграция с RiskCalculator (3-4 часа)

#### Обновить `src/core/risk_calculator.py`:

```python
class RiskCalculator:
    def __init__(self, settings_manager: SettingsManager):
        self.settings_manager = settings_manager
    
    async def calculate_levels(
        self,
        account_id: str,
        ticker: str,
        avg_price: float,
        quantity: int,
        direction: str
    ):
        """Рассчитать уровни SL/TP"""
        
        # Получить эффективные настройки
        settings = await self.settings_manager.get_effective_settings(
            account_id,
            ticker
        )
        
        sl_pct = settings['stop_loss_pct']
        tp_pct = settings['take_profit_pct']
        multi_tp_enabled = settings['multi_tp_enabled']
        multi_tp_levels = settings['multi_tp_levels']
        
        if multi_tp_enabled and multi_tp_levels:
            # Рассчитать Multi-TP уровни
            return self._calculate_multi_tp(
                avg_price,
                quantity,
                direction,
                sl_pct,
                multi_tp_levels
            )
        else:
            # Обычный SL/TP
            return self._calculate_simple(
                avg_price,
                quantity,
                direction,
                sl_pct,
                tp_pct
            )
    
    def _calculate_multi_tp(self, avg_price, quantity, direction, sl_pct, levels):
        """Рассчитать Multi-TP уровни"""
        
        if direction == "LONG":
            sl_price = avg_price * (1 - sl_pct / 100)
            
            tp_orders = []
            for level in levels:
                tp_price = avg_price * (1 + level['level_pct'] / 100)
                tp_quantity = int(quantity * level['volume_pct'] / 100)
                
                tp_orders.append({
                    'price': tp_price,
                    'quantity': tp_quantity,
                    'level_pct': level['level_pct']
                })
            
            return {
                'sl_price': sl_price,
                'tp_orders': tp_orders
            }
        else:
            # SHORT
            sl_price = avg_price * (1 + sl_pct / 100)
            
            tp_orders = []
            for level in levels:
                tp_price = avg_price * (1 - level['level_pct'] / 100)
                tp_quantity = int(quantity * level['volume_pct'] / 100)
                
                tp_orders.append({
                    'price': tp_price,
                    'quantity': tp_quantity,
                    'level_pct': level['level_pct']
                })
            
            return {
                'sl_price': sl_price,
                'tp_orders': tp_orders
            }
```

#### Обновить `src/main.py`:

```python
# Создать SettingsManager
settings_manager = SettingsManager(database)

# Передать в RiskCalculator
risk_calculator = RiskCalculator(settings_manager)

# Передать в стратегии
strategy = FuturesSlTpStrategy(
    api_client=api_client,
    risk_calculator=risk_calculator,
    # ...
)
```

---

### 3. Команды бота (2-3 часа)

#### Добавить в `src/bot/bot.py`:

```python
from src.bot.settings_menu import SettingsMenu
from telegram.ext import ConversationHandler

class TradingBot:
    def __init__(self, ...):
        # ...
        self.settings_menu = SettingsMenu(
            settings_manager=settings_manager,
            database=database,
            chat_id=self.chat_id
        )
    
    def setup_handlers(self):
        # Существующие обработчики...
        
        # ConversationHandler для меню настроек
        settings_conv = ConversationHandler(
            entry_points=[
                CommandHandler('settings', self.settings_menu.show_main_menu)
            ],
            states={
                MAIN_MENU: [
                    CallbackQueryHandler(self.settings_menu.handle_callback_full)
                ],
                GLOBAL_SETTINGS: [
                    CallbackQueryHandler(self.settings_menu.handle_callback_full)
                ],
                EDIT_SL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, 
                                 self.settings_menu.save_global_sl),
                    CallbackQueryHandler(self.settings_menu.handle_callback_full)
                ],
                EDIT_TP: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND,
                                 self.settings_menu.save_global_tp),
                    CallbackQueryHandler(self.settings_menu.handle_callback_full)
                ],
                # ... остальные состояния
            },
            fallbacks=[
                CommandHandler('cancel', self.settings_menu.cancel),
                CallbackQueryHandler(self.settings_menu.cancel, pattern='^cancel')
            ]
        )
        
        self.application.add_handler(settings_conv)
        
        # Команда пересчета
        self.application.add_handler(
            CommandHandler('recalculate', self.cmd_recalculate)
        )
    
    async def cmd_recalculate(self, update, context):
        """Пересчитать ордера для всех позиций"""
        # Получить все открытые позиции
        positions = await self.database.get_open_positions()
        
        if not positions:
            await update.message.reply_text("📊 Нет открытых позиций")
            return
        
        await update.message.reply_text(
            f"🔄 Начинаю пересчет ордеров для {len(positions)} позиций..."
        )
        
        for position in positions:
            # Отменить старые ордера
            old_orders = await self.database.get_active_orders_by_position(position.id)
            for order in old_orders:
                await self.order_executor.cancel_order(order.order_id)
            
            # Рассчитать новые уровни
            levels = await self.risk_calculator.calculate_levels(
                position.account_id,
                position.ticker,
                position.average_price,
                position.quantity,
                position.direction
            )
            
            # Выставить новые ордера
            await self.order_executor.place_stop_orders(
                position=position,
                levels=levels
            )
        
        await update.message.reply_text(
            f"✅ Пересчет завершен для {len(positions)} позиций"
        )
```

---

### 4. Тестирование (1-2 часа)

#### Тесты для SettingsManager:

```python
# tests/test_settings_manager.py

async def test_get_effective_settings():
    """Тест приоритета настроек"""
    # Создать глобальные: SL=0.4%, TP=1.0%
    # Создать для SBER: SL=2.5%
    # Проверить: SBER использует SL=2.5%, TP=1.0% (глобальные)

async def test_multi_tp_validation():
    """Тест валидации Multi-TP"""
    # Сумма != 100% → ошибка
    # Уровни не по возрастанию → ошибка
    # Корректные уровни → OK
```

---

## 🚀 Порядок выполнения:

1. ✅ Завершить Multi-TP функционал (редактирование/удаление)
2. ✅ Интегрировать с RiskCalculator
3. ✅ Добавить команды в бот
4. ✅ Протестировать
5. ✅ Обновить документацию

**Осталось: ~8-12 часов работы**
