"""
Интерактивное меню настроек для Telegram бота
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import json

from src.config.settings_manager import SettingsManager
from src.storage.database import Database
from src.utils.logger import get_logger

logger = get_logger("bot.settings_menu")

# Состояния для ConversationHandler
(
    MAIN_MENU,
    GLOBAL_SETTINGS,
    INSTRUMENT_LIST,
    INSTRUMENT_SETTINGS,
    EDIT_SL,
    EDIT_TP,
    MULTI_TP_MENU,
    ADD_LEVEL,
    ADD_LEVEL_PRICE,
    ADD_LEVEL_VOLUME,
    EDIT_LEVEL,
    EDIT_LEVEL_PRICE,
    EDIT_LEVEL_VOLUME,
    DELETE_LEVEL,
    SL_STRATEGY,
    ADD_INSTRUMENT,
    EDIT_INSTRUMENT_SL,
    EDIT_INSTRUMENT_TP,
    EDIT_SL_ACTIVATION,
    EDIT_TP_ACTIVATION,
    EDIT_INSTRUMENT_SL_ACTIVATION,
    EDIT_INSTRUMENT_TP_ACTIVATION,
) = range(22)


class SettingsMenu:
    """
    Интерактивное меню настроек торговли
    """
    
    def __init__(
        self,
        settings_manager: SettingsManager,
        database: Database,
        chat_id: str
    ):
        """
        Инициализация меню настроек
        
        Args:
            settings_manager: Менеджер настроек
            database: База данных
            chat_id: ID чата для проверки авторизации
        """
        self.settings_manager = settings_manager
        self.db = database
        self.chat_id = chat_id
    
    def _check_auth(self, update: Update) -> bool:
        """Проверка авторизации пользователя"""
        return str(update.effective_chat.id) == self.chat_id
    
    # ==================== ГЛАВНОЕ МЕНЮ ====================
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать главное меню настроек"""
        if not self._check_auth(update):
            await update.message.reply_text("❌ Доступ запрещен")
            return ConversationHandler.END
        
        keyboard = [
            [InlineKeyboardButton("🌍 Глобальные настройки", callback_data="global_settings")],
            [InlineKeyboardButton("📈 Настройки инструментов", callback_data="instrument_list")],
            [InlineKeyboardButton("📋 Просмотр всех настроек", callback_data="view_all")],
            [InlineKeyboardButton("◀️ Закрыть", callback_data="close")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "⚙️ <b>НАСТРОЙКИ AUTO-STOP</b>\n\n"
            "Выберите раздел для настройки:"
        )
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        
        return MAIN_MENU
    
    # ==================== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ====================
    
    async def show_global_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать глобальные настройки"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text(
                "❌ Активный аккаунт не найден",
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        # Получить глобальные настройки
        settings = await self.settings_manager.get_global_settings(active_account.account_id)
        
        if not settings:
            # Создать настройки по умолчанию
            settings = await self.settings_manager.create_global_settings(active_account.account_id)
        
        # Парсинг Multi-TP уровней
        multi_tp_status = "✅ Включен" if settings.multi_tp_enabled else "❌ Выключен"
        multi_tp_levels_count = 0
        if settings.multi_tp_levels:
            try:
                levels = json.loads(settings.multi_tp_levels)
                multi_tp_levels_count = len(levels)
            except:
                pass
        
        # Статус активации
        sl_activation_status = "✅" if settings.sl_activation_pct is not None else "❌"
        tp_activation_status = "✅" if settings.tp_activation_pct is not None else "❌"
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить SL", callback_data="edit_global_sl")],
            [InlineKeyboardButton("✏️ Изменить TP", callback_data="edit_global_tp")],
            [InlineKeyboardButton("🔔 Активация SL", callback_data="edit_global_sl_activation")],
            [InlineKeyboardButton("🔔 Активация TP", callback_data="edit_global_tp_activation")],
            [InlineKeyboardButton("🎯 Настроить Multi-TP", callback_data="global_multi_tp")],
            [InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "🌍 <b>ГЛОБАЛЬНЫЕ НАСТРОЙКИ</b>\n"
            "<i>(применяются ко всем инструментам по умолчанию)</i>\n\n"
            "┌─────────────────────────┐\n"
            f"│ 🛑 Stop Loss: <b>{settings.stop_loss_pct}%</b>\n"
            f"│ 🎯 Take Profit: <b>{settings.take_profit_pct}%</b>\n"
            f"│ 🔔 Активация SL: {sl_activation_status} "
        )
        
        if settings.sl_activation_pct is not None:
            text += f"<b>{settings.sl_activation_pct}%</b>"
        
        text += f"\n│ 🔔 Активация TP: {tp_activation_status} "
        
        if settings.tp_activation_pct is not None:
            text += f"<b>{settings.tp_activation_pct}%</b>"
        
        text += f"\n│ 🎯 Multi-TP: {multi_tp_status}"
        
        if multi_tp_levels_count > 0:
            text += f" ({multi_tp_levels_count} ур.)"
        
        text += "\n└─────────────────────────┘"
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        return GLOBAL_SETTINGS
    
    # ==================== СПИСОК ИНСТРУМЕНТОВ ====================
    
    async def show_instrument_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список инструментов с настройками"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить все инструменты с настройками
        instruments = await self.settings_manager.get_all_instruments(active_account.account_id)
        
        keyboard = []
        
        if instruments:
            for inst in instruments:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📈 {inst.ticker}",
                        callback_data=f"instrument_{inst.ticker}"
                    )
                ])
        else:
            text_no_instruments = "\n<i>Нет инструментов с индивидуальными настройками</i>\n"
        
        keyboard.append([InlineKeyboardButton("➕ Добавить инструмент", callback_data="add_instrument")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "📈 <b>НАСТРОЙКИ ИНСТРУМЕНТОВ</b>\n\n"
            "Выберите инструмент для настройки:"
        )
        
        if not instruments:
            text += text_no_instruments
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        return INSTRUMENT_LIST
    
    # ==================== ПРОСМОТР ВСЕХ НАСТРОЕК ====================
    
    async def view_all_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все настройки (глобальные + инструменты)"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить глобальные настройки
        global_settings = await self.settings_manager.get_global_settings(active_account.account_id)
        
        text = "📋 <b>ВСЕ НАСТРОЙКИ</b>\n\n"
        
        # Глобальные настройки
        if global_settings:
            multi_tp_status = "включен" if global_settings.multi_tp_enabled else "выключен"
            text += (
                "🌍 <b>Глобальные (по умолчанию):</b>\n"
                f"  🛑 SL: {global_settings.stop_loss_pct}%\n"
                f"  🎯 TP: {global_settings.take_profit_pct}%\n"
                f"  🎯 Multi-TP: {multi_tp_status}\n\n"
            )
        else:
            text += (
                "🌍 <b>Глобальные (по умолчанию):</b>\n"
                "  🛑 SL: 0.4%\n"
                "  🎯 TP: 1.0%\n"
                "  🎯 Multi-TP: выключен\n\n"
            )
        
        # Инструменты с индивидуальными настройками
        instruments = await self.settings_manager.get_all_instruments(active_account.account_id)
        
        if instruments:
            text += "📈 <b>Инструменты с индивидуальными настройками:</b>\n\n"
            for inst in instruments:
                text += f"<b>{inst.ticker}</b>:\n"
                
                if inst.stop_loss_pct is not None:
                    text += f"  🛑 SL: {inst.stop_loss_pct}% ✏️\n"
                else:
                    text += "  🛑 SL: глобальные\n"
                
                if inst.take_profit_pct is not None:
                    text += f"  🎯 TP: {inst.take_profit_pct}% ✏️\n"
                else:
                    text += "  🎯 TP: глобальные\n"
                
                if inst.multi_tp_enabled is not None:
                    status = "включен ✏️" if inst.multi_tp_enabled else "выключен ✏️"
                    text += f"  🎯 Multi-TP: {status}\n"
                else:
                    text += "  🎯 Multi-TP: глобальные\n"
                
                text += "\n"
            
            text += "\n<i>Остальные инструменты используют глобальные настройки</i>"
        else:
            text += "<i>Все инструменты используют глобальные настройки</i>"
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        return MAIN_MENU
    
    # ==================== ОБРАБОТЧИКИ CALLBACK ====================
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        # Главное меню
        if data == "main_menu":
            return await self.show_main_menu(update, context)
        
        # Глобальные настройки
        elif data == "global_settings":
            return await self.show_global_settings(update, context)
        
        # Список инструментов
        elif data == "instrument_list":
            return await self.show_instrument_list(update, context)
        
        # Просмотр всех настроек
        elif data == "view_all":
            return await self.view_all_settings(update, context)
        
        # Закрыть меню
        elif data == "close":
            await query.edit_message_text("✅ Меню закрыто")
            return ConversationHandler.END
        
        return MAIN_MENU
    
    # ==================== РЕДАКТИРОВАНИЕ ГЛОБАЛЬНЫХ НАСТРОЕК ====================
    
    async def edit_global_sl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать редактирование глобального Stop Loss"""
        query = update.callback_query
        await query.answer()
        
        # Получить текущее значение
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        settings = await self.settings_manager.get_global_settings(active_account.account_id)
        current_sl = settings.stop_loss_pct if settings else 0.4
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="global_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "✏️ <b>Изменить глобальный Stop Loss</b>\n\n"
            f"Текущее значение: <b>{current_sl}%</b>\n\n"
            "Введите новое значение в процентах:\n"
            "Примеры: <code>0.5</code>, <code>1.0</code>, <code>2.5</code>\n\n"
            "Диапазон: 0.1% - 10%"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['editing'] = 'global_sl'
        
        return EDIT_SL
    
    async def save_global_sl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новое значение глобального Stop Loss"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 0.1 or value > 10:
                await update.message.reply_text(
                    "❌ Значение должно быть от 0.1% до 10%\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_SL
            
            # Получить активный аккаунт
            active_account = await self.db.get_active_account()
            if not active_account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return ConversationHandler.END
            
            # Обновить настройки
            await self.settings_manager.update_global_settings(
                active_account.account_id,
                stop_loss_pct=value
            )
            
            await update.message.reply_text(
                f"✅ Глобальный Stop Loss обновлен: <b>{value}%</b>\n\n"
                "Возвращаюсь в меню настроек...",
                parse_mode='HTML'
            )
            
            # Показать меню глобальных настроек
            # Создаем фейковый callback query для возврата в меню
            context.user_data['return_to'] = 'global_settings'
            
            # Отправляем новое сообщение с меню
            keyboard = [
                [InlineKeyboardButton("🌍 Глобальные настройки", callback_data="global_settings")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите действие:",
                reply_markup=reply_markup
            )
            
            return MAIN_MENU
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 1.5):"
            )
            return EDIT_SL
    
    async def edit_global_tp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать редактирование глобального Take Profit"""
        query = update.callback_query
        await query.answer()
        
        # Получить текущее значение
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        settings = await self.settings_manager.get_global_settings(active_account.account_id)
        current_tp = settings.take_profit_pct if settings else 1.0
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="global_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "✏️ <b>Изменить глобальный Take Profit</b>\n\n"
            f"Текущее значение: <b>{current_tp}%</b>\n\n"
            "Введите новое значение в процентах:\n"
            "Примеры: <code>1.0</code>, <code>2.5</code>, <code>5.0</code>\n\n"
            "Диапазон: 0.1% - 20%"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['editing'] = 'global_tp'
        
        return EDIT_TP
    
    async def save_global_tp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новое значение глобального Take Profit"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 0.1 or value > 20:
                await update.message.reply_text(
                    "❌ Значение должно быть от 0.1% до 20%\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_TP
            
            # Получить активный аккаунт
            active_account = await self.db.get_active_account()
            if not active_account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return ConversationHandler.END
            
            # Обновить настройки
            await self.settings_manager.update_global_settings(
                active_account.account_id,
                take_profit_pct=value
            )
            
            await update.message.reply_text(
                f"✅ Глобальный Take Profit обновлен: <b>{value}%</b>\n\n"
                "Возвращаюсь в меню настроек...",
                parse_mode='HTML'
            )
            
            # Отправляем новое сообщение с меню
            keyboard = [
                [InlineKeyboardButton("🌍 Глобальные настройки", callback_data="global_settings")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите действие:",
                reply_markup=reply_markup
            )
            
            return MAIN_MENU
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 2.5):"
            )
            return EDIT_TP
    
    # ==================== ОБНОВЛЕННЫЕ ОБРАБОТЧИКИ CALLBACK ====================
    
    async def handle_callback_extended(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Расширенный обработчик callback кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        # Главное меню
        if data == "main_menu":
            return await self.show_main_menu(update, context)
        
        # Глобальные настройки
        elif data == "global_settings":
            return await self.show_global_settings(update, context)
        
        # Редактирование глобальных настроек
        elif data == "edit_global_sl":
            return await self.edit_global_sl(update, context)
        
        elif data == "edit_global_tp":
            return await self.edit_global_tp(update, context)
        
        # Список инструментов
        elif data == "instrument_list":
            return await self.show_instrument_list(update, context)
        
        # Просмотр всех настроек
        elif data == "view_all":
            return await self.view_all_settings(update, context)
        
        # Закрыть меню
        elif data == "close":
            await query.edit_message_text("✅ Меню закрыто")
            return ConversationHandler.END
        
        return MAIN_MENU
    
    # ==================== НАСТРОЙКИ ИНСТРУМЕНТОВ ====================
    
    async def add_instrument_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать добавление нового инструмента"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="instrument_list")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "➕ <b>Добавить инструмент</b>\n\n"
            "Введите тикер инструмента:\n"
            "Примеры: <code>SBER</code>, <code>GAZP</code>, <code>YNDX</code>\n\n"
            "<i>После добавления вы сможете настроить для него индивидуальные SL/TP</i>"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        return ADD_INSTRUMENT
    
    async def add_instrument_save(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новый инструмент"""
        ticker = update.message.text.strip().upper()
        
        # Валидация тикера
        if not ticker or len(ticker) > 12:
            await update.message.reply_text(
                "❌ Неверный тикер. Введите корректный тикер (до 12 символов):"
            )
            return ADD_INSTRUMENT
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await update.message.reply_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Проверить, не существует ли уже
        existing = await self.settings_manager.get_instrument_settings(
            active_account.account_id,
            ticker
        )
        
        if existing:
            await update.message.reply_text(
                f"⚠️ Инструмент <b>{ticker}</b> уже добавлен\n\n"
                "Возвращаюсь в список...",
                parse_mode='HTML'
            )
        else:
            # Создать настройки (пока пустые, будут использоваться глобальные)
            await self.settings_manager.create_instrument_settings(
                active_account.account_id,
                ticker
            )
            
            await update.message.reply_text(
                f"✅ Инструмент <b>{ticker}</b> добавлен\n\n"
                "Сейчас он использует глобальные настройки.\n"
                "Вы можете настроить индивидуальные параметры.",
                parse_mode='HTML'
            )
        
        # Вернуться к списку инструментов
        keyboard = [
            [InlineKeyboardButton("📈 Настройки инструментов", callback_data="instrument_list")],
            [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚙️ Выберите действие:",
            reply_markup=reply_markup
        )
        
        return MAIN_MENU
    
    async def show_instrument_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Показать настройки конкретного инструмента"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить эффективные настройки
        effective = await self.settings_manager.get_effective_settings(
            active_account.account_id,
            ticker
        )
        
        # Получить настройки инструмента
        inst_settings = await self.settings_manager.get_instrument_settings(
            active_account.account_id,
            ticker
        )
        
        # Формирование текста
        sl_text = f"{effective['stop_loss_pct']}%"
        tp_text = f"{effective['take_profit_pct']}%"
        
        if inst_settings and inst_settings.stop_loss_pct is not None:
            sl_text += " ✏️"
            sl_source = "свои"
        else:
            sl_source = "глобальные"
        
        if inst_settings and inst_settings.take_profit_pct is not None:
            tp_text += " ✏️"
            tp_source = "свои"
        else:
            tp_source = "глобальные"
        
        # Статус активации
        sl_activation_text = "не задана"
        tp_activation_text = "не задана"
        sl_activation_source = "глобальные"
        tp_activation_source = "глобальные"
        
        if effective['sl_activation_pct'] is not None:
            sl_activation_text = f"{effective['sl_activation_pct']}%"
            if inst_settings and inst_settings.sl_activation_pct is not None:
                sl_activation_text += " ✏️"
                sl_activation_source = "свои"
        
        if effective['tp_activation_pct'] is not None:
            tp_activation_text = f"{effective['tp_activation_pct']}%"
            if inst_settings and inst_settings.tp_activation_pct is not None:
                tp_activation_text += " ✏️"
                tp_activation_source = "свои"
        
        multi_tp_status = "включен" if effective['multi_tp_enabled'] else "выключен"
        if inst_settings and inst_settings.multi_tp_enabled is not None:
            multi_tp_status += " ✏️"
            multi_tp_source = "свои"
        else:
            multi_tp_source = "глобальные"
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить SL", callback_data=f"edit_inst_sl_{ticker}")],
            [InlineKeyboardButton("✏️ Изменить TP", callback_data=f"edit_inst_tp_{ticker}")],
            [InlineKeyboardButton("🔔 Активация SL", callback_data=f"edit_inst_sl_activation_{ticker}")],
            [InlineKeyboardButton("🔔 Активация TP", callback_data=f"edit_inst_tp_activation_{ticker}")],
            [InlineKeyboardButton("🎯 Настроить Multi-TP", callback_data=f"inst_multi_tp_{ticker}")],
            [InlineKeyboardButton("🔄 Сбросить на глобальные", callback_data=f"reset_inst_{ticker}")],
            [InlineKeyboardButton("🗑️ Удалить инструмент", callback_data=f"delete_inst_{ticker}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="instrument_list")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"📈 <b>{ticker}</b>\n\n"
            "Используются настройки:\n"
            "┌─────────────────────────┐\n"
            f"│ 🛑 SL: <b>{sl_text}</b> ({sl_source})\n"
            f"│ 🎯 TP: <b>{tp_text}</b> ({tp_source})\n"
            f"│ 🔔 Активация SL: <b>{sl_activation_text}</b> ({sl_activation_source})\n"
            f"│ 🔔 Активация TP: <b>{tp_activation_text}</b> ({tp_activation_source})\n"
            f"│ 🎯 Multi-TP: {multi_tp_status} ({multi_tp_source})\n"
            "└─────────────────────────┘"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        return INSTRUMENT_SETTINGS
    
    async def reset_instrument_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Сбросить настройки инструмента на глобальные"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Обновить настройки (установить все в NULL)
        await self.settings_manager.update_instrument_settings(
            active_account.account_id,
            ticker,
            stop_loss_pct=None,
            take_profit_pct=None,
            multi_tp_enabled=None,
            multi_tp_levels=None,
            multi_tp_sl_strategy=None
        )
        
        await query.answer("✅ Настройки сброшены на глобальные", show_alert=True)
        
        # Показать обновленные настройки
        return await self.show_instrument_settings(update, context, ticker)
    
    async def delete_instrument(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Удалить инструмент из настроек"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Удалить настройки
        deleted = await self.settings_manager.delete_instrument_settings(
            active_account.account_id,
            ticker
        )
        
        if deleted:
            await query.answer(f"✅ Инструмент {ticker} удален", show_alert=True)
        else:
            await query.answer(f"⚠️ Инструмент {ticker} не найден", show_alert=True)
        
        # Вернуться к списку
        return await self.show_instrument_list(update, context)
    
    # ==================== РЕДАКТИРОВАНИЕ SL/TP ДЛЯ ИНСТРУМЕНТОВ ====================
    
    async def edit_instrument_sl(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Начать редактирование Stop Loss для инструмента"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить эффективные настройки
        effective = await self.settings_manager.get_effective_settings(
            active_account.account_id,
            ticker
        )
        
        current_sl = effective['stop_loss_pct']
        source = effective['source']
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data=f"instrument_{ticker}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"✏️ <b>Изменить Stop Loss для {ticker}</b>\n\n"
            f"Текущее значение: <b>{current_sl}%</b> ({source})\n\n"
            "Введите новое значение в процентах:\n"
            "Примеры: <code>0.5</code>, <code>1.0</code>, <code>2.5</code>\n\n"
            "Диапазон: 0.1% - 10%"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['editing'] = 'instrument_sl'
        context.user_data['ticker'] = ticker
        
        return EDIT_INSTRUMENT_SL
    
    async def save_instrument_sl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новое значение Stop Loss для инструмента"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 0.1 or value > 10:
                await update.message.reply_text(
                    "❌ Значение должно быть от 0.1% до 10%\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_INSTRUMENT_SL
            
            # Получить тикер из контекста
            ticker = context.user_data.get('ticker')
            if not ticker:
                await update.message.reply_text("❌ Ошибка: тикер не найден")
                return ConversationHandler.END
            
            # Получить активный аккаунт
            active_account = await self.db.get_active_account()
            if not active_account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return ConversationHandler.END
            
            # Обновить настройки
            await self.settings_manager.update_instrument_settings(
                active_account.account_id,
                ticker,
                stop_loss_pct=value
            )
            
            await update.message.reply_text(
                f"✅ Stop Loss для <b>{ticker}</b> обновлен: <b>{value}%</b>\n\n"
                "Возвращаюсь в меню настроек...",
                parse_mode='HTML'
            )
            
            # Отправляем новое сообщение с меню
            keyboard = [
                [InlineKeyboardButton(f"📈 {ticker}", callback_data=f"instrument_{ticker}")],
                [InlineKeyboardButton("📈 Настройки инструментов", callback_data="instrument_list")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите действие:",
                reply_markup=reply_markup
            )
            
            return MAIN_MENU
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 1.5):"
            )
            return EDIT_INSTRUMENT_SL
    
    async def edit_instrument_tp(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Начать редактирование Take Profit для инструмента"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить эффективные настройки
        effective = await self.settings_manager.get_effective_settings(
            active_account.account_id,
            ticker
        )
        
        current_tp = effective['take_profit_pct']
        source = effective['source']
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data=f"instrument_{ticker}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"✏️ <b>Изменить Take Profit для {ticker}</b>\n\n"
            f"Текущее значение: <b>{current_tp}%</b> ({source})\n\n"
            "Введите новое значение в процентах:\n"
            "Примеры: <code>1.0</code>, <code>2.5</code>, <code>5.0</code>\n\n"
            "Диапазон: 0.1% - 20%"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['editing'] = 'instrument_tp'
        context.user_data['ticker'] = ticker
        
        return EDIT_INSTRUMENT_TP
    
    async def save_instrument_tp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новое значение Take Profit для инструмента"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 0.1 or value > 20:
                await update.message.reply_text(
                    "❌ Значение должно быть от 0.1% до 20%\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_INSTRUMENT_TP
            
            # Получить тикер из контекста
            ticker = context.user_data.get('ticker')
            if not ticker:
                await update.message.reply_text("❌ Ошибка: тикер не найден")
                return ConversationHandler.END
            
            # Получить активный аккаунт
            active_account = await self.db.get_active_account()
            if not active_account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return ConversationHandler.END
            
            # Обновить настройки
            await self.settings_manager.update_instrument_settings(
                active_account.account_id,
                ticker,
                take_profit_pct=value
            )
            
            await update.message.reply_text(
                f"✅ Take Profit для <b>{ticker}</b> обновлен: <b>{value}%</b>\n\n"
                "Возвращаюсь в меню настроек...",
                parse_mode='HTML'
            )
            
            # Отправляем новое сообщение с меню
            keyboard = [
                [InlineKeyboardButton(f"📈 {ticker}", callback_data=f"instrument_{ticker}")],
                [InlineKeyboardButton("📈 Настройки инструментов", callback_data="instrument_list")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите действие:",
                reply_markup=reply_markup
            )
            
            return MAIN_MENU
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 2.5):"
            )
            return EDIT_INSTRUMENT_TP
    
    # ==================== РЕДАКТИРОВАНИЕ АКТИВАЦИИ SL/TP ====================
    
    async def edit_global_sl_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать редактирование глобальной активации Stop Loss"""
        query = update.callback_query
        await query.answer()
        
        # Получить текущее значение
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        settings = await self.settings_manager.get_global_settings(active_account.account_id)
        current_sl_activation = settings.sl_activation_pct if settings and settings.sl_activation_pct is not None else "не задана"
        
        # Формируем клавиатуру в зависимости от текущего состояния
        keyboard = []
        
        # Если активация уже задана, показываем кнопку отключения
        if settings and settings.sl_activation_pct is not None:
            keyboard.append([InlineKeyboardButton("❌ Отключить активацию", callback_data="disable_global_sl_activation")])
        
        # Добавляем кнопку отмены в любом случае
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="global_settings")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "🔔 <b>Изменить активацию Stop Loss</b>\n\n"
            f"Текущее значение: <b>{current_sl_activation}</b>\n\n"
            "Введите новое значение в процентах:\n"
            "Примеры: <code>0.2</code>, <code>0.3</code>\n\n"
            "Диапазон: 0.1% - 5%\n\n"
            "<i>Активация SL - это процент от средней цены, при достижении которого будет выставлен ордер SL.</i>\n"
            "<i>Например, если SL=0.4%, а активация=0.2%, то ордер SL будет выставлен только когда цена упадет на 0.2%.</i>"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['editing'] = 'global_sl_activation'
        
        return EDIT_SL_ACTIVATION
    
    async def disable_global_sl_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отключить глобальную активацию Stop Loss"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Обновить настройки
        await self.settings_manager.update_global_settings(
            active_account.account_id,
            sl_activation_pct=None
        )
        
        await query.answer("✅ Активация SL отключена", show_alert=True)
        
        # Вернуться в меню глобальных настроек
        return await self.show_global_settings(update, context)
    
    async def save_global_sl_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новое значение глобальной активации Stop Loss"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 0.1 or value > 5:
                await update.message.reply_text(
                    "❌ Значение должно быть от 0.1% до 5%\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_SL_ACTIVATION
            
            # Получить активный аккаунт
            active_account = await self.db.get_active_account()
            if not active_account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return ConversationHandler.END
            
            # Получить текущие настройки для валидации
            settings = await self.settings_manager.get_global_settings(active_account.account_id)
            sl_pct = settings.stop_loss_pct if settings else 0.4
            
            # Валидация с SL
            valid, error = self.settings_manager.validate_activation_settings(
                sl_pct=sl_pct,
                sl_activation_pct=value,
                tp_pct=0,
                tp_activation_pct=None
            )
            
            if not valid:
                await update.message.reply_text(
                    f"❌ Ошибка валидации: {error}\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_SL_ACTIVATION
            
            # Обновить настройки
            await self.settings_manager.update_global_settings(
                active_account.account_id,
                sl_activation_pct=value
            )
            
            await update.message.reply_text(
                f"✅ Глобальная активация Stop Loss обновлена: <b>{value}%</b>\n\n"
                "Возвращаюсь в меню настроек...",
                parse_mode='HTML'
            )
            
            # Отправляем новое сообщение с меню
            keyboard = [
                [InlineKeyboardButton("🌍 Глобальные настройки", callback_data="global_settings")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите действие:",
                reply_markup=reply_markup
            )
            
            return MAIN_MENU
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 0.2):"
            )
            return EDIT_SL_ACTIVATION
    
    async def edit_global_tp_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать редактирование глобальной активации Take Profit"""
        query = update.callback_query
        await query.answer()
        
        # Получить текущее значение
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        settings = await self.settings_manager.get_global_settings(active_account.account_id)
        current_tp_activation = settings.tp_activation_pct if settings and settings.tp_activation_pct is not None else "не задана"
        
        # Формируем клавиатуру в зависимости от текущего состояния
        keyboard = []
        
        # Если активация уже задана, показываем кнопку отключения
        if settings and settings.tp_activation_pct is not None:
            keyboard.append([InlineKeyboardButton("❌ Отключить активацию", callback_data="disable_global_tp_activation")])
        
        # Добавляем кнопку отмены в любом случае
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="global_settings")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "🔔 <b>Изменить активацию Take Profit</b>\n\n"
            f"Текущее значение: <b>{current_tp_activation}</b>\n\n"
            "Введите новое значение в процентах:\n"
            "Примеры: <code>0.5</code>, <code>0.7</code>\n\n"
            "Диапазон: 0.1% - 10%\n\n"
            "<i>Активация TP - это процент от средней цены, при достижении которого будет выставлен ордер TP.</i>\n"
            "<i>Например, если TP=1.0%, а активация=0.5%, то ордер TP будет выставлен только когда цена вырастет на 0.5%.</i>"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['editing'] = 'global_tp_activation'
        
        return EDIT_TP_ACTIVATION
    
    async def disable_global_tp_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отключить глобальную активацию Take Profit"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Обновить настройки
        await self.settings_manager.update_global_settings(
            active_account.account_id,
            tp_activation_pct=None
        )
        
        await query.answer("✅ Активация TP отключена", show_alert=True)
        
        # Вернуться в меню глобальных настроек
        return await self.show_global_settings(update, context)
    
    async def save_global_tp_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новое значение глобальной активации Take Profit"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 0.1 or value > 10:
                await update.message.reply_text(
                    "❌ Значение должно быть от 0.1% до 10%\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_TP_ACTIVATION
            
            # Получить активный аккаунт
            active_account = await self.db.get_active_account()
            if not active_account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return ConversationHandler.END
            
            # Получить текущие настройки для валидации
            settings = await self.settings_manager.get_global_settings(active_account.account_id)
            tp_pct = settings.take_profit_pct if settings else 1.0
            
            # Валидация с TP
            valid, error = self.settings_manager.validate_activation_settings(
                sl_pct=0,
                sl_activation_pct=None,
                tp_pct=tp_pct,
                tp_activation_pct=value
            )
            
            if not valid:
                await update.message.reply_text(
                    f"❌ Ошибка валидации: {error}\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_TP_ACTIVATION
            
            # Обновить настройки
            await self.settings_manager.update_global_settings(
                active_account.account_id,
                tp_activation_pct=value
            )
            
            await update.message.reply_text(
                f"✅ Глобальная активация Take Profit обновлена: <b>{value}%</b>\n\n"
                "Возвращаюсь в меню настроек...",
                parse_mode='HTML'
            )
            
            # Отправляем новое сообщение с меню
            keyboard = [
                [InlineKeyboardButton("🌍 Глобальные настройки", callback_data="global_settings")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите действие:",
                reply_markup=reply_markup
            )
            
            return MAIN_MENU
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 0.5):"
            )
            return EDIT_TP_ACTIVATION
    
    async def edit_instrument_sl_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Начать редактирование активации Stop Loss для инструмента"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить эффективные настройки
        effective = await self.settings_manager.get_effective_settings(
            active_account.account_id,
            ticker
        )
        
        # Получить настройки инструмента
        inst_settings = await self.settings_manager.get_instrument_settings(
            active_account.account_id,
            ticker
        )
        
        current_sl_activation = effective['sl_activation_pct']
        source = "свои" if inst_settings and inst_settings.sl_activation_pct is not None else "глобальные"
        
        # Формируем клавиатуру в зависимости от текущего состояния
        keyboard = []
        
        # Если активация уже задана для этого инструмента, показываем кнопку отключения
        if inst_settings and inst_settings.sl_activation_pct is not None:
            keyboard.append([InlineKeyboardButton("❌ Отключить активацию", callback_data=f"disable_inst_sl_activation_{ticker}")])
        
        # Всегда показываем кнопку сброса на глобальные настройки
        keyboard.append([InlineKeyboardButton("🔄 Сбросить на глобальные", callback_data=f"reset_inst_sl_activation_{ticker}")])
        
        # Добавляем кнопку отмены в любом случае
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=f"instrument_{ticker}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"🔔 <b>Изменить активацию Stop Loss для {ticker}</b>\n\n"
            f"Текущее значение: <b>{current_sl_activation if current_sl_activation is not None else 'не задана'}</b> ({source})\n\n"
            "Введите новое значение в процентах:\n"
            "Примеры: <code>0.2</code>, <code>0.3</code>\n\n"
            "Диапазон: 0.1% - 5%\n\n"
            "<i>Активация SL - это процент от средней цены, при достижении которого будет выставлен ордер SL.</i>\n"
            "<i>Например, если SL=0.4%, а активация=0.2%, то ордер SL будет выставлен только когда цена упадет на 0.2%.</i>"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['editing'] = 'instrument_sl_activation'
        context.user_data['ticker'] = ticker
        
        return EDIT_INSTRUMENT_SL_ACTIVATION
    
    async def disable_instrument_sl_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Отключить активацию Stop Loss для инструмента"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Обновить настройки
        await self.settings_manager.update_instrument_settings(
            active_account.account_id,
            ticker,
            sl_activation_pct=0  # Явно задаем 0, чтобы отличать от NULL (глобальные)
        )
        
        await query.answer("✅ Активация SL отключена для инструмента", show_alert=True)
        
        # Вернуться в меню настроек инструмента
        return await self.show_instrument_settings(update, context, ticker)
    
    async def reset_instrument_sl_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Сбросить активацию Stop Loss для инструмента на глобальные"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Обновить настройки
        await self.settings_manager.update_instrument_settings(
            active_account.account_id,
            ticker,
            sl_activation_pct=None  # NULL = использовать глобальные
        )
        
        await query.answer("✅ Активация SL сброшена на глобальные", show_alert=True)
        
        # Вернуться в меню настроек инструмента
        return await self.show_instrument_settings(update, context, ticker)
    
    async def save_instrument_sl_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новое значение активации Stop Loss для инструмента"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 0.1 or value > 5:
                await update.message.reply_text(
                    "❌ Значение должно быть от 0.1% до 5%\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_INSTRUMENT_SL_ACTIVATION
            
            # Получить тикер из контекста
            ticker = context.user_data.get('ticker')
            if not ticker:
                await update.message.reply_text("❌ Ошибка: тикер не найден")
                return ConversationHandler.END
            
            # Получить активный аккаунт
            active_account = await self.db.get_active_account()
            if not active_account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return ConversationHandler.END
            
            # Получить текущие настройки для валидации
            effective = await self.settings_manager.get_effective_settings(
                active_account.account_id,
                ticker
            )
            sl_pct = effective['stop_loss_pct']
            
            # Валидация с SL
            valid, error = self.settings_manager.validate_activation_settings(
                sl_pct=sl_pct,
                sl_activation_pct=value,
                tp_pct=0,
                tp_activation_pct=None
            )
            
            if not valid:
                await update.message.reply_text(
                    f"❌ Ошибка валидации: {error}\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_INSTRUMENT_SL_ACTIVATION
            
            # Обновить настройки
            await self.settings_manager.update_instrument_settings(
                active_account.account_id,
                ticker,
                sl_activation_pct=value
            )
            
            await update.message.reply_text(
                f"✅ Активация Stop Loss для <b>{ticker}</b> обновлена: <b>{value}%</b>\n\n"
                "Возвращаюсь в меню настроек...",
                parse_mode='HTML'
            )
            
            # Отправляем новое сообщение с меню
            keyboard = [
                [InlineKeyboardButton(f"📈 {ticker}", callback_data=f"instrument_{ticker}")],
                [InlineKeyboardButton("📈 Настройки инструментов", callback_data="instrument_list")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите действие:",
                reply_markup=reply_markup
            )
            
            return MAIN_MENU
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 0.2):"
            )
            return EDIT_INSTRUMENT_SL_ACTIVATION
    
    async def edit_instrument_tp_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Начать редактирование активации Take Profit для инструмента"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить эффективные настройки
        effective = await self.settings_manager.get_effective_settings(
            active_account.account_id,
            ticker
        )
        
        # Получить настройки инструмента
        inst_settings = await self.settings_manager.get_instrument_settings(
            active_account.account_id,
            ticker
        )
        
        current_tp_activation = effective['tp_activation_pct']
        source = "свои" if inst_settings and inst_settings.tp_activation_pct is not None else "глобальные"
        
        # Формируем клавиатуру в зависимости от текущего состояния
        keyboard = []
        
        # Если активация уже задана для этого инструмента, показываем кнопку отключения
        if inst_settings and inst_settings.tp_activation_pct is not None:
            keyboard.append([InlineKeyboardButton("❌ Отключить активацию", callback_data=f"disable_inst_tp_activation_{ticker}")])
        
        # Всегда показываем кнопку сброса на глобальные настройки
        keyboard.append([InlineKeyboardButton("🔄 Сбросить на глобальные", callback_data=f"reset_inst_tp_activation_{ticker}")])
        
        # Добавляем кнопку отмены в любом случае
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=f"instrument_{ticker}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"🔔 <b>Изменить активацию Take Profit для {ticker}</b>\n\n"
            f"Текущее значение: <b>{current_tp_activation if current_tp_activation is not None else 'не задана'}</b> ({source})\n\n"
            "Введите новое значение в процентах:\n"
            "Примеры: <code>0.5</code>, <code>0.7</code>\n\n"
            "Диапазон: 0.1% - 10%\n\n"
            "<i>Активация TP - это процент от средней цены, при достижении которого будет выставлен ордер TP.</i>\n"
            "<i>Например, если TP=1.0%, а активация=0.5%, то ордер TP будет выставлен только когда цена вырастет на 0.5%.</i>"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['editing'] = 'instrument_tp_activation'
        context.user_data['ticker'] = ticker
        
        return EDIT_INSTRUMENT_TP_ACTIVATION
    
    async def disable_instrument_tp_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Отключить активацию Take Profit для инструмента"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Обновить настройки
        await self.settings_manager.update_instrument_settings(
            active_account.account_id,
            ticker,
            tp_activation_pct=0  # Явно задаем 0, чтобы отличать от NULL (глобальные)
        )
        
        await query.answer("✅ Активация TP отключена для инструмента", show_alert=True)
        
        # Вернуться в меню настроек инструмента
        return await self.show_instrument_settings(update, context, ticker)
    
    async def reset_instrument_tp_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str):
        """Сбросить активацию Take Profit для инструмента на глобальные"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Обновить настройки
        await self.settings_manager.update_instrument_settings(
            active_account.account_id,
            ticker,
            tp_activation_pct=None  # NULL = использовать глобальные
        )
        
        await query.answer("✅ Активация TP сброшена на глобальные", show_alert=True)
        
        # Вернуться в меню настроек инструмента
        return await self.show_instrument_settings(update, context, ticker)
    
    async def save_instrument_tp_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новое значение активации Take Profit для инструмента"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 0.1 or value > 10:
                await update.message.reply_text(
                    "❌ Значение должно быть от 0.1% до 10%\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_INSTRUMENT_TP_ACTIVATION
            
            # Получить тикер из контекста
            ticker = context.user_data.get('ticker')
            if not ticker:
                await update.message.reply_text("❌ Ошибка: тикер не найден")
                return ConversationHandler.END
            
            # Получить активный аккаунт
            active_account = await self.db.get_active_account()
            if not active_account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return ConversationHandler.END
            
            # Получить текущие настройки для валидации
            effective = await self.settings_manager.get_effective_settings(
                active_account.account_id,
                ticker
            )
            tp_pct = effective['take_profit_pct']
            
            # Валидация с TP
            valid, error = self.settings_manager.validate_activation_settings(
                sl_pct=0,
                sl_activation_pct=None,
                tp_pct=tp_pct,
                tp_activation_pct=value
            )
            
            if not valid:
                await update.message.reply_text(
                    f"❌ Ошибка валидации: {error}\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_INSTRUMENT_TP_ACTIVATION
            
            # Обновить настройки
            await self.settings_manager.update_instrument_settings(
                active_account.account_id,
                ticker,
                tp_activation_pct=value
            )
            
            await update.message.reply_text(
                f"✅ Активация Take Profit для <b>{ticker}</b> обновлена: <b>{value}%</b>\n\n"
                "Возвращаюсь в меню настроек...",
                parse_mode='HTML'
            )
            
            # Отправляем новое сообщение с меню
            keyboard = [
                [InlineKeyboardButton(f"📈 {ticker}", callback_data=f"instrument_{ticker}")],
                [InlineKeyboardButton("📈 Настройки инструментов", callback_data="instrument_list")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите действие:",
                reply_markup=reply_markup
            )
            
            return MAIN_MENU
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 0.5):"
            )
            return EDIT_INSTRUMENT_TP_ACTIVATION
    
    # ==================== ОБНОВЛЕННЫЕ ОБРАБОТЧИКИ CALLBACK ====================
    
    async def handle_callback_full(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Полный обработчик callback кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        # Главное меню
        if data == "main_menu":
            return await self.show_main_menu(update, context)
        
        # Глобальные настройки
        elif data == "global_settings":
            return await self.show_global_settings(update, context)
        
        # Редактирование глобальных настроек
        elif data == "edit_global_sl":
            return await self.edit_global_sl(update, context)
        
        elif data == "edit_global_tp":
            return await self.edit_global_tp(update, context)
        
        # Активация SL/TP для глобальных настроек
        elif data == "edit_global_sl_activation":
            return await self.edit_global_sl_activation(update, context)
        
        elif data == "disable_global_sl_activation":
            return await self.disable_global_sl_activation(update, context)
        
        elif data == "edit_global_tp_activation":
            return await self.edit_global_tp_activation(update, context)
        
        elif data == "disable_global_tp_activation":
            return await self.disable_global_tp_activation(update, context)
        
        # Multi-TP для глобальных настроек
        elif data == "global_multi_tp":
            return await self.show_multi_tp_menu(update, context, is_global=True)
        
        elif data == "toggle_global_multi_tp":
            return await self.toggle_multi_tp(update, context, is_global=True)
        
        elif data == "add_global_level":
            return await self.add_level_start(update, context)
        
        elif data == "edit_level_menu_global":
            return await self.edit_level_menu(update, context)
        
        elif data == "delete_level_menu_global":
            return await self.delete_level_menu(update, context)
        
        elif data == "show_multi_tp":
            ctx = context.user_data.get('multi_tp_context', {})
            is_global = ctx.get('is_global', True)
            ticker = ctx.get('ticker')
            return await self.show_multi_tp_menu(update, context, is_global, ticker)
        
        # Редактирование уровня Multi-TP
        elif data.startswith("edit_level_") and not data.startswith("edit_level_menu_"):
            parts = data.replace("edit_level_", "").split("_")
            level_index = int(parts[0])
            return await self.edit_level_start(update, context, level_index)
        
        # Удаление уровня Multi-TP
        elif data.startswith("delete_level_") and not data.startswith("delete_level_menu_"):
            parts = data.replace("delete_level_", "").split("_")
            level_index = int(parts[0])
            return await self.delete_level_confirm(update, context, level_index)
        
        elif data.startswith("confirm_delete_"):
            return await self.delete_level_execute(update, context)
        
        # Список инструментов
        elif data == "instrument_list":
            return await self.show_instrument_list(update, context)
        
        # Добавление инструмента
        elif data == "add_instrument":
            return await self.add_instrument_start(update, context)
        
        # Multi-TP для инструмента
        elif data.startswith("inst_multi_tp_"):
            ticker = data.replace("inst_multi_tp_", "")
            return await self.show_multi_tp_menu(update, context, is_global=False, ticker=ticker)
        
        elif data.startswith("toggle_inst_multi_tp_"):
            ticker = data.replace("toggle_inst_multi_tp_", "")
            return await self.toggle_multi_tp(update, context, is_global=False, ticker=ticker)
        
        elif data.startswith("add_inst_level_"):
            return await self.add_level_start(update, context)
        
        elif data.startswith("edit_level_menu_") and data != "edit_level_menu_global":
            return await self.edit_level_menu(update, context)
        
        elif data.startswith("delete_level_menu_") and data != "delete_level_menu_global":
            return await self.delete_level_menu(update, context)
        
        # Просмотр настроек инструмента
        elif data.startswith("instrument_"):
            ticker = data.replace("instrument_", "")
            return await self.show_instrument_settings(update, context, ticker)
        
        # Редактирование SL/TP для инструмента
        elif data.startswith("edit_inst_sl_") and not data.startswith("edit_inst_sl_activation_"):
            ticker = data.replace("edit_inst_sl_", "")
            return await self.edit_instrument_sl(update, context, ticker)
        
        elif data.startswith("edit_inst_tp_") and not data.startswith("edit_inst_tp_activation_"):
            ticker = data.replace("edit_inst_tp_", "")
            return await self.edit_instrument_tp(update, context, ticker)
        
        # Активация SL/TP для инструмента
        elif data.startswith("edit_inst_sl_activation_"):
            ticker = data.replace("edit_inst_sl_activation_", "")
            return await self.edit_instrument_sl_activation(update, context, ticker)
        
        elif data.startswith("disable_inst_sl_activation_"):
            ticker = data.replace("disable_inst_sl_activation_", "")
            return await self.disable_instrument_sl_activation(update, context, ticker)
        
        elif data.startswith("reset_inst_sl_activation_"):
            ticker = data.replace("reset_inst_sl_activation_", "")
            return await self.reset_instrument_sl_activation(update, context, ticker)
        
        elif data.startswith("edit_inst_tp_activation_"):
            ticker = data.replace("edit_inst_tp_activation_", "")
            return await self.edit_instrument_tp_activation(update, context, ticker)
        
        elif data.startswith("disable_inst_tp_activation_"):
            ticker = data.replace("disable_inst_tp_activation_", "")
            return await self.disable_instrument_tp_activation(update, context, ticker)
        
        elif data.startswith("reset_inst_tp_activation_"):
            ticker = data.replace("reset_inst_tp_activation_", "")
            return await self.reset_instrument_tp_activation(update, context, ticker)
        
        # Сброс настроек инструмента
        elif data.startswith("reset_inst_") and not data.startswith("reset_inst_sl_activation_") and not data.startswith("reset_inst_tp_activation_"):
            ticker = data.replace("reset_inst_", "")
            return await self.reset_instrument_settings(update, context, ticker)
        
        # Удаление инструмента
        elif data.startswith("delete_inst_"):
            ticker = data.replace("delete_inst_", "")
            return await self.delete_instrument(update, context, ticker)
        
        # Просмотр всех настроек
        elif data == "view_all":
            return await self.view_all_settings(update, context)
        
        # Закрыть меню
        elif data == "close":
            await query.edit_message_text("✅ Меню закрыто")
            return ConversationHandler.END
        
        return MAIN_MENU
    
    # ==================== MULTI-TP ФУНКЦИОНАЛ ====================
    
    async def show_multi_tp_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_global: bool = True, ticker: str = None):
        """Показать меню Multi-TP"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить настройки
        if is_global:
            settings = await self.settings_manager.get_global_settings(active_account.account_id)
            if not settings:
                settings = await self.settings_manager.create_global_settings(active_account.account_id)
            
            multi_tp_enabled = settings.multi_tp_enabled
            multi_tp_levels_json = settings.multi_tp_levels
            title = "🌍 ГЛОБАЛЬНЫЙ MULTI-TP"
            back_callback = "global_settings"
            toggle_callback = "toggle_global_multi_tp"
            add_callback = "add_global_level"
        else:
            effective = await self.settings_manager.get_effective_settings(active_account.account_id, ticker)
            multi_tp_enabled = effective['multi_tp_enabled']
            multi_tp_levels_json = json.dumps(effective['multi_tp_levels']) if effective['multi_tp_levels'] else None
            title = f"🎯 MULTI-TP ДЛЯ {ticker}"
            back_callback = f"instrument_{ticker}"
            toggle_callback = f"toggle_inst_multi_tp_{ticker}"
            add_callback = f"add_inst_level_{ticker}"
        
        # Парсинг уровней
        levels = []
        if multi_tp_levels_json:
            try:
                levels = json.loads(multi_tp_levels_json)
            except:
                pass
        
        # Формирование текста
        status = "✅ Включен" if multi_tp_enabled else "❌ Выключен"
        
        text = f"{title}\n\n"
        text += f"Статус: {status}\n\n"
        
        if levels:
            text += "Уровни выхода:\n"
            text += "┌─────────────────────────┐\n"
            for i, level in enumerate(levels, 1):
                level_pct = level.get('level_pct', 0)
                volume_pct = level.get('volume_pct', 0)
                text += f"│ {i}️⃣ +{level_pct}% → {volume_pct}% позиции\n"
            text += "└─────────────────────────┘\n"
            
            # Проверка суммы
            total_volume = sum(l.get('volume_pct', 0) for l in levels)
            if abs(total_volume - 100) < 0.01:
                text += "\n✅ Сумма уровней: 100%"
            else:
                text += f"\n⚠️ Сумма уровней: {total_volume}% (должно быть 100%)"
        else:
            text += "<i>Уровни не настроены</i>"
        
        # Кнопки
        keyboard = []
        
        if multi_tp_enabled:
            keyboard.append([InlineKeyboardButton("❌ Выключить Multi-TP", callback_data=toggle_callback)])
            if levels:
                keyboard.append([InlineKeyboardButton("✏️ Изменить уровень", callback_data=f"edit_level_menu_{ticker if ticker else 'global'}")])
                keyboard.append([InlineKeyboardButton("🗑️ Удалить уровень", callback_data=f"delete_level_menu_{ticker if ticker else 'global'}")])
            if len(levels) < 10:
                keyboard.append([InlineKeyboardButton("➕ Добавить уровень", callback_data=add_callback)])
        else:
            keyboard.append([InlineKeyboardButton("✅ Включить Multi-TP", callback_data=toggle_callback)])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=back_callback)])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['multi_tp_context'] = {
            'is_global': is_global,
            'ticker': ticker
        }
        
        return MULTI_TP_MENU
    
    async def toggle_multi_tp(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_global: bool, ticker: str = None):
        """Включить/выключить Multi-TP"""
        query = update.callback_query
        await query.answer()
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        if is_global:
            settings = await self.settings_manager.get_global_settings(active_account.account_id)
            new_state = not settings.multi_tp_enabled if settings else True
            
            await self.settings_manager.update_global_settings(
                active_account.account_id,
                multi_tp_enabled=new_state
            )
        else:
            inst_settings = await self.settings_manager.get_instrument_settings(active_account.account_id, ticker)
            if inst_settings and inst_settings.multi_tp_enabled is not None:
                new_state = not inst_settings.multi_tp_enabled
            else:
                # Получить из глобальных
                global_settings = await self.settings_manager.get_global_settings(active_account.account_id)
                new_state = not global_settings.multi_tp_enabled if global_settings else True
            
            await self.settings_manager.update_instrument_settings(
                active_account.account_id,
                ticker,
                multi_tp_enabled=new_state
            )
        
        # Показать обновленное меню
        return await self.show_multi_tp_menu(update, context, is_global, ticker)
    
    async def add_level_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать добавление уровня Multi-TP"""
        query = update.callback_query
        await query.answer()
        
        ctx = context.user_data.get('multi_tp_context', {})
        is_global = ctx.get('is_global', True)
        ticker = ctx.get('ticker')
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_level")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "➕ <b>Добавить уровень Multi-TP</b>\n\n"
            "Шаг 1/2: Уровень цены\n\n"
            "Введите процент от средней цены:\n"
            "Примеры: <code>1.0</code>, <code>2.5</code>, <code>5.0</code>\n\n"
            "Диапазон: 0.1% - 20%"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        return ADD_LEVEL_PRICE
    
    async def add_level_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить уровень цены и запросить объем"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 0.1 or value > 20:
                await update.message.reply_text(
                    "❌ Значение должно быть от 0.1% до 20%\n"
                    "Попробуйте еще раз:"
                )
                return ADD_LEVEL_PRICE
            
            # Сохранить в контекст
            context.user_data['new_level_price'] = value
            
            # Запросить объем
            keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_level")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = (
                "➕ <b>Добавить уровень Multi-TP</b>\n\n"
                f"Уровень цены: <b>+{value}%</b> ✅\n\n"
                "Шаг 2/2: Объем закрытия\n\n"
                "Введите процент позиции для закрытия:\n"
                "Примеры: <code>25</code>, <code>50</code>, <code>100</code>\n\n"
                "Диапазон: 1% - 100%"
            )
            
            await update.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            return ADD_LEVEL_VOLUME
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 2.5):"
            )
            return ADD_LEVEL_PRICE
    
    async def add_level_volume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить объем и добавить уровень"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 1 or value > 100:
                await update.message.reply_text(
                    "❌ Значение должно быть от 1% до 100%\n"
                    "Попробуйте еще раз:"
                )
                return ADD_LEVEL_VOLUME
            
            # Получить данные из контекста
            level_price = context.user_data.get('new_level_price')
            ctx = context.user_data.get('multi_tp_context', {})
            is_global = ctx.get('is_global', True)
            ticker = ctx.get('ticker')
            
            # Получить активный аккаунт
            active_account = await self.db.get_active_account()
            if not active_account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return ConversationHandler.END
            
            # Получить текущие уровни
            if is_global:
                settings = await self.settings_manager.get_global_settings(active_account.account_id)
                current_levels = json.loads(settings.multi_tp_levels) if settings and settings.multi_tp_levels else []
            else:
                effective = await self.settings_manager.get_effective_settings(active_account.account_id, ticker)
                current_levels = effective['multi_tp_levels']
            
            # Добавить новый уровень
            new_level = {
                'level_pct': level_price,
                'volume_pct': value
            }
            current_levels.append(new_level)
            
            # Сортировать по level_pct
            current_levels.sort(key=lambda x: x['level_pct'])
            
            # Валидация
            valid, error = self.settings_manager.validate_multi_tp_levels(current_levels)
            if not valid:
                await update.message.reply_text(
                    f"❌ Ошибка валидации: {error}\n\n"
                    "Уровень не добавлен. Попробуйте другие значения."
                )
                
                # Вернуться в меню
                keyboard = [
                    [InlineKeyboardButton("🎯 Multi-TP", callback_data="show_multi_tp")],
                    [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "⚙️ Выберите действие:",
                    reply_markup=reply_markup
                )
                
                return MAIN_MENU
            
            # Сохранить
            if is_global:
                await self.settings_manager.update_global_settings(
                    active_account.account_id,
                    multi_tp_levels=current_levels
                )
            else:
                await self.settings_manager.update_instrument_settings(
                    active_account.account_id,
                    ticker,
                    multi_tp_levels=current_levels
                )
            
            await update.message.reply_text(
                f"✅ Уровень добавлен: <b>+{level_price}% → {value}%</b>\n\n"
                "Возвращаюсь в меню Multi-TP...",
                parse_mode='HTML'
            )
            
            # Вернуться в меню
            keyboard = [
                [InlineKeyboardButton("🎯 Multi-TP", callback_data="show_multi_tp")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите действие:",
                reply_markup=reply_markup
            )
            
            return MAIN_MENU
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 25):"
            )
            return ADD_LEVEL_VOLUME
    
    # ==================== РЕДАКТИРОВАНИЕ УРОВНЕЙ MULTI-TP ====================
    
    async def edit_level_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню выбора уровня для редактирования"""
        query = update.callback_query
        await query.answer()
        
        ctx = context.user_data.get('multi_tp_context', {})
        is_global = ctx.get('is_global', True)
        ticker = ctx.get('ticker')
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить текущие уровни
        if is_global:
            settings = await self.settings_manager.get_global_settings(active_account.account_id)
            levels = json.loads(settings.multi_tp_levels) if settings and settings.multi_tp_levels else []
        else:
            effective = await self.settings_manager.get_effective_settings(active_account.account_id, ticker)
            levels = effective['multi_tp_levels'] if effective['multi_tp_levels'] else []
        
        if not levels:
            await query.answer("❌ Нет уровней для редактирования", show_alert=True)
            return await self.show_multi_tp_menu(update, context, is_global, ticker)
        
        # Формирование кнопок
        keyboard = []
        for i, level in enumerate(levels):
            level_pct = level.get('level_pct', 0)
            volume_pct = level.get('volume_pct', 0)
            keyboard.append([
                InlineKeyboardButton(
                    f"{i+1}️⃣ +{level_pct}% → {volume_pct}%",
                    callback_data=f"edit_level_{i}_{ticker if ticker else 'global'}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="show_multi_tp")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "✏️ <b>Выберите уровень для редактирования</b>\n\n"
            "Текущие уровни:"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        return EDIT_LEVEL
    
    async def edit_level_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE, level_index: int):
        """Начать редактирование уровня"""
        query = update.callback_query
        await query.answer()
        
        ctx = context.user_data.get('multi_tp_context', {})
        is_global = ctx.get('is_global', True)
        ticker = ctx.get('ticker')
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить текущие уровни
        if is_global:
            settings = await self.settings_manager.get_global_settings(active_account.account_id)
            levels = json.loads(settings.multi_tp_levels) if settings and settings.multi_tp_levels else []
        else:
            effective = await self.settings_manager.get_effective_settings(active_account.account_id, ticker)
            levels = effective['multi_tp_levels'] if effective['multi_tp_levels'] else []
        
        if level_index >= len(levels):
            await query.answer("❌ Уровень не найден", show_alert=True)
            return await self.show_multi_tp_menu(update, context, is_global, ticker)
        
        level = levels[level_index]
        current_price = level.get('level_pct', 0)
        current_volume = level.get('volume_pct', 0)
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_edit_level")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"✏️ <b>Редактирование уровня {level_index + 1}</b>\n\n"
            f"Текущие значения:\n"
            f"  Уровень цены: <b>+{current_price}%</b>\n"
            f"  Объем закрытия: <b>{current_volume}%</b>\n\n"
            "Шаг 1/2: Новый уровень цены\n\n"
            "Введите новый процент от средней цены:\n"
            "Примеры: <code>1.0</code>, <code>2.5</code>, <code>5.0</code>\n\n"
            "Диапазон: 0.1% - 20%"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['editing_level_index'] = level_index
        
        return EDIT_LEVEL_PRICE
    
    async def edit_level_price_save(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новый уровень цены и запросить объем"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 0.1 or value > 20:
                await update.message.reply_text(
                    "❌ Значение должно быть от 0.1% до 20%\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_LEVEL_PRICE
            
            # Сохранить в контекст
            context.user_data['edit_level_price'] = value
            
            level_index = context.user_data.get('editing_level_index', 0)
            
            # Запросить объем
            keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_edit_level")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = (
                f"✏️ <b>Редактирование уровня {level_index + 1}</b>\n\n"
                f"Новый уровень цены: <b>+{value}%</b> ✅\n\n"
                "Шаг 2/2: Новый объем закрытия\n\n"
                "Введите новый процент позиции для закрытия:\n"
                "Примеры: <code>25</code>, <code>50</code>, <code>100</code>\n\n"
                "Диапазон: 1% - 100%"
            )
            
            await update.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            return EDIT_LEVEL_VOLUME
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 2.5):"
            )
            return EDIT_LEVEL_PRICE
    
    async def edit_level_volume_save(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранить новый объем и обновить уровень"""
        try:
            # Парсинг значения
            value = float(update.message.text.strip().replace(',', '.'))
            
            # Валидация
            if value < 1 or value > 100:
                await update.message.reply_text(
                    "❌ Значение должно быть от 1% до 100%\n"
                    "Попробуйте еще раз:"
                )
                return EDIT_LEVEL_VOLUME
            
            # Получить данные из контекста
            level_index = context.user_data.get('editing_level_index', 0)
            level_price = context.user_data.get('edit_level_price')
            ctx = context.user_data.get('multi_tp_context', {})
            is_global = ctx.get('is_global', True)
            ticker = ctx.get('ticker')
            
            # Получить активный аккаунт
            active_account = await self.db.get_active_account()
            if not active_account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return ConversationHandler.END
            
            # Получить текущие уровни
            if is_global:
                settings = await self.settings_manager.get_global_settings(active_account.account_id)
                current_levels = json.loads(settings.multi_tp_levels) if settings and settings.multi_tp_levels else []
            else:
                effective = await self.settings_manager.get_effective_settings(active_account.account_id, ticker)
                current_levels = effective['multi_tp_levels'] if effective['multi_tp_levels'] else []
            
            if level_index >= len(current_levels):
                await update.message.reply_text("❌ Уровень не найден")
                return ConversationHandler.END
            
            # Обновить уровень
            current_levels[level_index] = {
                'level_pct': level_price,
                'volume_pct': value
            }
            
            # Сортировать по level_pct
            current_levels.sort(key=lambda x: x['level_pct'])
            
            # Валидация
            valid, error = self.settings_manager.validate_multi_tp_levels(current_levels)
            if not valid:
                await update.message.reply_text(
                    f"❌ Ошибка валидации: {error}\n\n"
                    "Изменения не сохранены."
                )
                
                # Вернуться в меню
                keyboard = [
                    [InlineKeyboardButton("🎯 Multi-TP", callback_data="show_multi_tp")],
                    [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "⚙️ Выберите действие:",
                    reply_markup=reply_markup
                )
                
                return MAIN_MENU
            
            # Сохранить
            if is_global:
                await self.settings_manager.update_global_settings(
                    active_account.account_id,
                    multi_tp_levels=current_levels
                )
            else:
                await self.settings_manager.update_instrument_settings(
                    active_account.account_id,
                    ticker,
                    multi_tp_levels=current_levels
                )
            
            await update.message.reply_text(
                f"✅ Уровень {level_index + 1} обновлен: <b>+{level_price}% → {value}%</b>\n\n"
                "Возвращаюсь в меню Multi-TP...",
                parse_mode='HTML'
            )
            
            # Вернуться в меню
            keyboard = [
                [InlineKeyboardButton("🎯 Multi-TP", callback_data="show_multi_tp")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите действие:",
                reply_markup=reply_markup
            )
            
            return MAIN_MENU
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 25):"
            )
            return EDIT_LEVEL_VOLUME
    
    # ==================== УДАЛЕНИЕ УРОВНЕЙ MULTI-TP ====================
    
    async def delete_level_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню выбора уровня для удаления"""
        query = update.callback_query
        await query.answer()
        
        ctx = context.user_data.get('multi_tp_context', {})
        is_global = ctx.get('is_global', True)
        ticker = ctx.get('ticker')
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить текущие уровни
        if is_global:
            settings = await self.settings_manager.get_global_settings(active_account.account_id)
            levels = json.loads(settings.multi_tp_levels) if settings and settings.multi_tp_levels else []
        else:
            effective = await self.settings_manager.get_effective_settings(active_account.account_id, ticker)
            levels = effective['multi_tp_levels'] if effective['multi_tp_levels'] else []
        
        if not levels:
            await query.answer("❌ Нет уровней для удаления", show_alert=True)
            return await self.show_multi_tp_menu(update, context, is_global, ticker)
        
        # Формирование кнопок
        keyboard = []
        for i, level in enumerate(levels):
            level_pct = level.get('level_pct', 0)
            volume_pct = level.get('volume_pct', 0)
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑️ {i+1}️⃣ +{level_pct}% → {volume_pct}%",
                    callback_data=f"delete_level_{i}_{ticker if ticker else 'global'}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="show_multi_tp")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "🗑️ <b>Выберите уровень для удаления</b>\n\n"
            "Текущие уровни:"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        return DELETE_LEVEL
    
    async def delete_level_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE, level_index: int):
        """Подтверждение удаления уровня"""
        query = update.callback_query
        await query.answer()
        
        ctx = context.user_data.get('multi_tp_context', {})
        is_global = ctx.get('is_global', True)
        ticker = ctx.get('ticker')
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить текущие уровни
        if is_global:
            settings = await self.settings_manager.get_global_settings(active_account.account_id)
            levels = json.loads(settings.multi_tp_levels) if settings and settings.multi_tp_levels else []
        else:
            effective = await self.settings_manager.get_effective_settings(active_account.account_id, ticker)
            levels = effective['multi_tp_levels'] if effective['multi_tp_levels'] else []
        
        if level_index >= len(levels):
            await query.answer("❌ Уровень не найден", show_alert=True)
            return await self.show_multi_tp_menu(update, context, is_global, ticker)
        
        level = levels[level_index]
        level_pct = level.get('level_pct', 0)
        volume_pct = level.get('volume_pct', 0)
        
        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{level_index}_{ticker if ticker else 'global'}")],
            [InlineKeyboardButton("❌ Отмена", callback_data="show_multi_tp")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            "🗑️ <b>Подтверждение удаления</b>\n\n"
            f"Удалить уровень {level_index + 1}?\n"
            f"  Уровень цены: <b>+{level_pct}%</b>\n"
            f"  Объем закрытия: <b>{volume_pct}%</b>\n\n"
            "⚠️ Это действие нельзя отменить"
        )
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Сохранить контекст
        context.user_data['deleting_level_index'] = level_index
        
        return DELETE_LEVEL
    
    async def delete_level_execute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выполнить удаление уровня"""
        query = update.callback_query
        await query.answer()
        
        level_index = context.user_data.get('deleting_level_index', 0)
        ctx = context.user_data.get('multi_tp_context', {})
        is_global = ctx.get('is_global', True)
        ticker = ctx.get('ticker')
        
        # Получить активный аккаунт
        active_account = await self.db.get_active_account()
        if not active_account:
            await query.edit_message_text("❌ Активный аккаунт не найден")
            return ConversationHandler.END
        
        # Получить текущие уровни
        if is_global:
            settings = await self.settings_manager.get_global_settings(active_account.account_id)
            current_levels = json.loads(settings.multi_tp_levels) if settings and settings.multi_tp_levels else []
        else:
            effective = await self.settings_manager.get_effective_settings(active_account.account_id, ticker)
            current_levels = effective['multi_tp_levels'] if effective['multi_tp_levels'] else []
        
        if level_index >= len(current_levels):
            await query.answer("❌ Уровень не найден", show_alert=True)
            return await self.show_multi_tp_menu(update, context, is_global, ticker)
        
        # Удалить уровень
        deleted_level = current_levels.pop(level_index)
        
        # Сохранить
        if is_global:
            await self.settings_manager.update_global_settings(
                active_account.account_id,
                multi_tp_levels=current_levels if current_levels else None
            )
        else:
            await self.settings_manager.update_instrument_settings(
                active_account.account_id,
                ticker,
                multi_tp_levels=current_levels if current_levels else None
            )
        
        await query.answer(
            f"✅ Уровень {level_index + 1} удален (+{deleted_level['level_pct']}% → {deleted_level['volume_pct']}%)",
            show_alert=True
        )
        
        # Показать обновленное меню
        return await self.show_multi_tp_menu(update, context, is_global, ticker)
    
    # ==================== ОТМЕНА ====================
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена и выход из меню"""
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ Операция отменена")
        else:
            await update.message.reply_text("❌ Операция отменена")
        
        return ConversationHandler.END
