"""
Telegram Bot для управления системой Auto-Stop
"""

import asyncio
from typing import Optional
from datetime import datetime
from telegram import Bot, BotCommand
from telegram.ext import Application, CommandHandler, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

from src.storage.database import Database
from src.core.position_manager import PositionManager
from src.analytics.operations_cache import OperationsCache
from src.analytics.statistics import StatisticsCalculator
from src.analytics.reports import ReportFormatter
from src.config.settings_manager import SettingsManager
from src.bot.settings_menu import SettingsMenu
from src.bot.handlers.system import SystemHandler
from src.bot.handlers.positions import PositionsHandler
from src.bot.handlers.statistics import StatisticsHandler
from src.bot.handlers.accounts import AccountsHandler
from src.utils.logger import get_logger

logger = get_logger("bot")


class TelegramBot:
    """
    Telegram Bot для управления системой
    """
    
    def __init__(
        self,
        token: str,
        chat_id: str,
        database: Database,
        position_manager: PositionManager,
        system_control: Optional[object] = None,
        operations_cache: Optional[OperationsCache] = None,
        statistics_calculator: Optional[StatisticsCalculator] = None,
        report_formatter: Optional[ReportFormatter] = None
    ):
        """
        Инициализация бота
        
        Args:
            token: Токен Telegram бота
            chat_id: ID чата для уведомлений
            database: База данных
            position_manager: Менеджер позиций
            system_control: Объект для управления системой (start/stop)
            operations_cache: Кэш операций для статистики
            statistics_calculator: Калькулятор статистики
            report_formatter: Форматтер отчетов
        """
        self.token = token
        self.chat_id = chat_id
        self.db = database
        self.position_manager = position_manager
        self.system_control = system_control
        self.operations_cache = operations_cache
        self.statistics_calculator = statistics_calculator
        self.report_formatter = report_formatter
        
        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None
        self._running = False
        self.start_time = datetime.utcnow()
        
        # Инициализация меню настроек
        self.settings_manager = SettingsManager(database)
        self.settings_menu = SettingsMenu(
            settings_manager=self.settings_manager,
            database=database,
            chat_id=chat_id
        )
        
        # Инициализация обработчиков команд
        self.system_handler = SystemHandler(self)
        self.positions_handler = PositionsHandler(self)
        self.statistics_handler = StatisticsHandler(self)
        self.accounts_handler = AccountsHandler(self)
    
    async def start(self):
        """Запуск бота"""
        if self._running:
            logger.warning("Бот уже запущен")
            return
        
        try:
            # Создание приложения
            self.application = Application.builder().token(self.token).build()
            self.bot = self.application.bot
            
            # Регистрация обработчиков команд
            
            # Системные команды
            self.application.add_handler(CommandHandler("start", self.system_handler.cmd_start))
            self.application.add_handler(CommandHandler("stop", self.system_handler.cmd_stop_system))
            self.application.add_handler(CommandHandler("help", self.system_handler.cmd_help))
            self.application.add_handler(CommandHandler("status", self.system_handler.cmd_status))
            self.application.add_handler(CommandHandler("logs", self.system_handler.cmd_logs))
            self.application.add_handler(CommandHandler("set_token", self.system_handler.cmd_set_token))
            
            # Команды для работы с позициями
            self.application.add_handler(CommandHandler("positions", self.positions_handler.cmd_positions))
            
            # Команды для работы со статистикой
            self.application.add_handler(CommandHandler("stats", self.statistics_handler.cmd_stats))
            self.application.add_handler(CommandHandler("stats_detailed", self.statistics_handler.cmd_stats_detailed))
            self.application.add_handler(CommandHandler("stats_instrument", self.statistics_handler.cmd_stats_instrument))
            
            # Команды управления аккаунтами
            self.application.add_handler(CommandHandler("accounts", self.accounts_handler.cmd_accounts))
            self.application.add_handler(CommandHandler("add_account", self.accounts_handler.cmd_add_account))
            self.application.add_handler(CommandHandler("switch_account", self.accounts_handler.cmd_switch_account))
            self.application.add_handler(CommandHandler("current_account", self.accounts_handler.cmd_current_account))
            self.application.add_handler(CommandHandler("remove_account", self.accounts_handler.cmd_remove_account))
            
            # ConversationHandler для меню настроек
            from src.bot.settings_menu import (
                MAIN_MENU, GLOBAL_SETTINGS, INSTRUMENT_LIST, INSTRUMENT_SETTINGS,
                EDIT_SL, EDIT_TP, MULTI_TP_MENU, ADD_LEVEL, ADD_LEVEL_PRICE, ADD_LEVEL_VOLUME,
                EDIT_LEVEL, EDIT_LEVEL_PRICE, EDIT_LEVEL_VOLUME, DELETE_LEVEL,
                SL_STRATEGY, ADD_INSTRUMENT, EDIT_INSTRUMENT_SL, EDIT_INSTRUMENT_TP
            )
            
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
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.settings_menu.save_global_sl),
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    EDIT_TP: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.settings_menu.save_global_tp),
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    INSTRUMENT_LIST: [
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    ADD_INSTRUMENT: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.settings_menu.add_instrument_save),
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    INSTRUMENT_SETTINGS: [
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    EDIT_INSTRUMENT_SL: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.settings_menu.save_instrument_sl),
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    EDIT_INSTRUMENT_TP: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.settings_menu.save_instrument_tp),
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    MULTI_TP_MENU: [
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    ADD_LEVEL_PRICE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.settings_menu.add_level_price),
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    ADD_LEVEL_VOLUME: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.settings_menu.add_level_volume),
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    EDIT_LEVEL: [
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    EDIT_LEVEL_PRICE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.settings_menu.edit_level_price_save),
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    EDIT_LEVEL_VOLUME: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.settings_menu.edit_level_volume_save),
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                    DELETE_LEVEL: [
                        CallbackQueryHandler(self.settings_menu.handle_callback_full)
                    ],
                },
                fallbacks=[
                    CommandHandler('cancel', self.settings_menu.cancel),
                    CallbackQueryHandler(self.settings_menu.cancel, pattern='^cancel')
                ],
                name="settings_conversation",
                persistent=False,
                per_chat=False,
                per_message=False
            )
            
            self.application.add_handler(settings_conv)
            
            # Запуск бота
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            # Установка команд для меню
            commands = [
                BotCommand("start", "🏠 Главное меню"),
                BotCommand("status", "📊 Статус системы"),
                BotCommand("positions", "📈 Текущие позиции"),
                BotCommand("settings", "⚙️ Настройки SL/TP"),
                BotCommand("stats", "📊 Статистика торговли"),
                BotCommand("stats_detailed", "📋 Детальная статистика сделок"),
                BotCommand("stats_instrument", "📈 Статистика по инструменту"),
                BotCommand("accounts", "👥 Управление счетами"),
                BotCommand("logs", "📋 Последние логи"),
                BotCommand("help", "❓ Справка"),
            ]
            await self.bot.set_my_commands(commands)
            logger.info("Команды меню установлены")
            
            self._running = True
            logger.info("Telegram Bot запущен")
            
            # Отправка приветственного сообщения
            await self.send_message("🤖 Бот Auto-Stop запущен и готов к работе!")
            
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
            raise
    
    async def stop(self):
        """Остановка бота"""
        if not self._running:
            return
        
        try:
            self._running = False
            
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            
            logger.info("Telegram Bot остановлен")
            
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}")
    
    async def send_message(self, text: str):
        """
        Отправка сообщения в чат
        
        Args:
            text: Текст сообщения
        """
        try:
            if self.bot:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        await update.message.reply_text(
            "🤖 <b>Добро пожаловать в Auto-Stop Bot!</b>\n\n"
            "Я помогу вам управлять системой автоматических стоп-лоссов и тейк-профитов.\n\n"
            "Доступные команды:\n"
            "/status - Статус системы\n"
            "/positions - Текущие позиции\n"
            "/stats - Статистика\n"
            "/logs - Последние логи\n"
            "/help - Справка",
            parse_mode='HTML'
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        await update.message.reply_text(
            "📖 <b>Справка по командам</b>\n\n"
            "<b>Информация:</b>\n"
            "/status - Статус системы (uptime, состояние)\n"
            "/positions - Список открытых позиций\n"
            "/logs - Последние события\n\n"
            "<b>Статистика:</b>\n"
            "/stats [период] [год] - Торговая статистика\n"
            "  • период: month, week, day (по умолчанию: month)\n"
            "  • год: 2024, 2025 (по умолчанию: текущий)\n"
            "  Примеры:\n"
            "  • /stats - месячная за текущий год\n"
            "  • /stats week - недельная за текущий год\n"
            "  • /stats month 2024 - месячная за 2024\n\n"
            "/stats_detailed - Детальная статистика сделок за сегодня\n"
            "  • Показывает прибыльные/убыточные сделки\n"
            "  • Цены входа/выхода\n"
            "  • Открытые позиции\n\n"
            "/stats_instrument {ticker} [период] - Статистика по инструменту\n"
            "  Примеры:\n"
            "  • /stats_instrument SBER\n"
            "  • /stats_instrument GAZP week\n\n"
            "<b>Управление аккаунтами:</b>\n"
            "/accounts - Список всех счетов\n"
            "/current_account - Текущий активный счет\n"
            "/add_account {название} {токен} {account_id} - Добавить счет\n"
            "/switch_account {название} - Переключить счет (без перезапуска!)\n"
            "/remove_account {название} - Удалить счет\n\n"
            "<b>Управление системой:</b>\n"
            "/stop - Остановить мониторинг\n"
            "/set_token - Обновить Tinkoff API токен\n\n"
            "<b>Прочее:</b>\n"
            "/help - Эта справка\n\n"
            "💡 <i>Все команды работают только для авторизованного пользователя</i>",
            parse_mode='HTML'
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            # Расчет uptime
            uptime = datetime.utcnow() - self.start_time
            hours = int(uptime.total_seconds() // 3600)
            minutes = int((uptime.total_seconds() % 3600) // 60)
            
            status_text = (
                "📊 <b>Статус системы</b>\n\n"
                f"🟢 Статус: <b>Работает</b>\n"
                f"⏱ Uptime: <b>{hours}ч {minutes}м</b>\n"
                f"📅 Запущена: <b>{self.start_time.strftime('%d.%m.%Y %H:%M:%S')} UTC</b>\n"
            )
            
            await update.message.reply_text(status_text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_status: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /positions"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            # Получение открытых позиций
            positions = await self.db.get_open_positions()
            
            if not positions:
                await update.message.reply_text("📭 Нет открытых позиций")
                return
            
            text = "📈 <b>Открытые позиции</b>\n\n"
            
            for pos in positions:
                direction_emoji = "🟢" if pos.direction == "BUY" else "🔴"
                text += (
                    f"{direction_emoji} <b>{pos.ticker}</b>\n"
                    f"  Количество: {pos.quantity}\n"
                    f"  Средняя цена: {pos.average_price:.2f}\n"
                    f"  Тип: {pos.instrument_type}\n\n"
                )
            
            await update.message.reply_text(text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_positions: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def cmd_stats_detailed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats_detailed - детальная статистика сделок за сегодня"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            # Проверка доступности компонентов аналитики
            if not self.operations_cache or not self.statistics_calculator or not self.report_formatter:
                await update.message.reply_text(
                    "❌ <b>Модуль статистики недоступен</b>\n\n"
                    "Компоненты аналитики не инициализированы.",
                    parse_mode='HTML'
                )
                return
            
            # Отправка уведомления о начале обработки
            processing_msg = await update.message.reply_text(
                "⏳ Загружаю операции и формирую детальный отчет...",
                parse_mode='HTML'
            )
            
            # Получение активного аккаунта
            active_account = await self.db.get_active_account()
            if not active_account:
                await processing_msg.edit_text(
                    "❌ Активный аккаунт не найден",
                    parse_mode='HTML'
                )
                return
            
            # Определение диапазона дат (только сегодня)
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            from_date = today
            to_date = datetime.now(timezone.utc)
            
            # Получение операций с кэшированием
            operations = await self.operations_cache.get_operations(
                account_id=active_account.account_id,
                from_date=from_date,
                to_date=to_date
            )
            
            if not operations:
                await processing_msg.edit_text(
                    "📭 <b>Нет операций за сегодня</b>",
                    parse_mode='HTML'
                )
                return
            
            # Расчет статистики
            stats = self.statistics_calculator.calculate_statistics(operations, period="day")
            
            # Форматирование детального отчета
            report = self.report_formatter.format_detailed_report(
                stats, 
                operations=operations,
                period="day",
                start_year=datetime.now().year
            )
            
            # Отправка отчета (может быть длинным, разбиваем если нужно)
            if len(report) > 4096:
                # Telegram ограничение на длину сообщения
                parts = [report[i:i+4096] for i in range(0, len(report), 4096)]
                await processing_msg.delete()
                for part in parts:
                    await update.message.reply_text(part, parse_mode='HTML')
            else:
                await processing_msg.edit_text(report, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_stats_detailed: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats [период] [год]"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            # Проверка доступности компонентов аналитики
            if not self.operations_cache or not self.statistics_calculator or not self.report_formatter:
                await update.message.reply_text(
                    "❌ <b>Модуль статистики недоступен</b>\n\n"
                    "Компоненты аналитики не инициализированы.",
                    parse_mode='HTML'
                )
                return
            
            # Парсинг аргументов
            period = "month"  # По умолчанию
            start_year = datetime.now().year  # Текущий год
            
            if len(context.args) >= 1:
                period_arg = context.args[0].lower()
                if period_arg in ["month", "week", "day"]:
                    period = period_arg
                else:
                    await update.message.reply_text(
                        "❌ <b>Неверный период</b>\n\n"
                        "Доступные периоды: month, week, day",
                        parse_mode='HTML'
                    )
                    return
            
            if len(context.args) >= 2:
                try:
                    start_year = int(context.args[1])
                    if start_year < 2020 or start_year > 2030:
                        raise ValueError("Год должен быть в диапазоне 2020-2030")
                except ValueError as e:
                    await update.message.reply_text(
                        f"❌ <b>Неверный год</b>\n\n{str(e)}",
                        parse_mode='HTML'
                    )
                    return
            
            # Отправка уведомления о начале обработки
            processing_msg = await update.message.reply_text(
                "⏳ Загружаю операции и рассчитываю статистику...",
                parse_mode='HTML'
            )
            
            # Получение активного аккаунта
            active_account = await self.db.get_active_account()
            if not active_account:
                await processing_msg.edit_text(
                    "❌ Активный аккаунт не найден",
                    parse_mode='HTML'
                )
                return
            
            # Определение диапазона дат
            from_date = datetime(start_year, 1, 1, tzinfo=timezone.utc)
            to_date = datetime.now(timezone.utc)
            
            # Получение операций с кэшированием
            operations = await self.operations_cache.get_operations(
                account_id=active_account.account_id,
                from_date=from_date,
                to_date=to_date
            )
            
            if not operations:
                await processing_msg.edit_text(
                    f"📭 <b>Нет операций за {start_year} год</b>",
                    parse_mode='HTML'
                )
                return
            
            # Расчет статистики
            stats = self.statistics_calculator.calculate_statistics(operations, period=period)
            
            # Форматирование отчета
            report = self.report_formatter.format_report(stats, period=period, start_year=start_year)
            
            # Отправка отчета (может быть длинным, разбиваем если нужно)
            if len(report) > 4096:
                # Telegram ограничение на длину сообщения
                parts = [report[i:i+4096] for i in range(0, len(report), 4096)]
                await processing_msg.delete()
                for part in parts:
                    await update.message.reply_text(part, parse_mode='HTML')
            else:
                await processing_msg.edit_text(report, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_stats: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def cmd_stats_instrument(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats_instrument <ticker> [период]"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            # Проверка доступности компонентов аналитики
            if not self.operations_cache or not self.statistics_calculator or not self.report_formatter:
                await update.message.reply_text(
                    "❌ <b>Модуль статистики недоступен</b>\n\n"
                    "Компоненты аналитики не инициализированы.",
                    parse_mode='HTML'
                )
                return
            
            # Проверка аргументов
            if not context.args:
                await update.message.reply_text(
                    "❌ <b>Использование:</b>\n"
                    "<code>/stats_instrument &lt;ticker&gt; [период]</code>\n\n"
                    "<b>Примеры:</b>\n"
                    "• /stats_instrument SBER\n"
                    "• /stats_instrument GAZP week\n"
                    "• /stats_instrument YNDX month",
                    parse_mode='HTML'
                )
                return
            
            # Парсинг аргументов
            ticker = context.args[0].upper()
            period = "month"  # По умолчанию
            
            if len(context.args) >= 2:
                period_arg = context.args[1].lower()
                if period_arg in ["month", "week", "day"]:
                    period = period_arg
                else:
                    await update.message.reply_text(
                        "❌ <b>Неверный период</b>\n\n"
                        "Доступные периоды: month, week, day",
                        parse_mode='HTML'
                    )
                    return
            
            # Отправка уведомления о начале обработки
            processing_msg = await update.message.reply_text(
                f"⏳ Загружаю операции по <b>{ticker}</b>...",
                parse_mode='HTML'
            )
            
            # Получение активного аккаунта
            active_account = await self.db.get_active_account()
            if not active_account:
                await processing_msg.edit_text(
                    "❌ Активный аккаунт не найден",
                    parse_mode='HTML'
                )
                return
            
            # Получение операций за текущий год
            from_date = datetime(datetime.now(timezone.utc).year, 1, 1, tzinfo=timezone.utc)
            to_date = datetime.now(timezone.utc)
            
            operations = await self.operations_cache.get_operations(
                account_id=active_account.account_id,
                from_date=from_date,
                to_date=to_date
            )
            
            # Фильтрация по тикеру
            instrument_operations = [op for op in operations if op.get('ticker') == ticker]
            
            if not instrument_operations:
                await processing_msg.edit_text(
                    f"📭 <b>Нет операций по {ticker}</b>\n\n"
                    f"За период: {from_date.strftime('%d.%m.%Y')} - {to_date.strftime('%d.%m.%Y')}",
                    parse_mode='HTML'
                )
                return
            
            # Расчет статистики
            stats = self.statistics_calculator.calculate_statistics(instrument_operations, period=period)
            
            # Форматирование отчета
            report = self.report_formatter.format_instrument_report(
                stats, 
                ticker=ticker, 
                period=period,
                start_year=datetime.now().year
            )
            
            # Отправка отчета
            if len(report) > 4096:
                parts = [report[i:i+4096] for i in range(0, len(report), 4096)]
                await processing_msg.delete()
                for part in parts:
                    await update.message.reply_text(part, parse_mode='HTML')
            else:
                await processing_msg.edit_text(report, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_stats_instrument: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /logs"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            # Получение последних событий
            events = await self.db.get_recent_events(limit=10)
            
            if not events:
                await update.message.reply_text("📭 Нет событий в логах")
                return
            
            text = "📋 <b>Последние события</b>\n\n"
            
            for event in events:
                emoji = "ℹ️" if event.event_type == "INFO" else "⚠️" if event.event_type == "STREAM_ERROR" else "❌"
                text += (
                    f"{emoji} <code>{event.created_at.strftime('%H:%M:%S')}</code> "
                    f"{event.event_type}\n"
                    f"  {event.description[:100]}\n\n"
                )
            
            await update.message.reply_text(text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_logs: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def cmd_set_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /set_token"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            # Удаление сообщения с токеном для безопасности
            try:
                await update.message.delete()
            except:
                pass
            
            # Проверка аргументов
            if not context.args or len(context.args) == 0:
                await self.send_message(
                    "❌ <b>Ошибка</b>\n\n"
                    "Использование: <code>/set_token НОВЫЙ_ТОКЕН</code>\n\n"
                    "⚠️ Сообщение с токеном будет автоматически удалено"
                )
                return
            
            new_token = context.args[0]
            
            # Сохраняем токен в базу данных
            await self.db.set_setting(
                key="tinkoff_token",
                value=new_token,
                description="Tinkoff API токен (обновлен через Telegram бот)"
            )
            
            logger.info("Токен Tinkoff API обновлен через Telegram бот и сохранен в БД")
            
            await self.send_message(
                "✅ <b>Токен сохранен в базу данных!</b>\n\n"
                "⚠️ <b>Для применения изменений необходимо перезапустить контейнер:</b>\n"
                "<code>docker compose restart</code>\n\n"
                "После перезапуска система будет использовать новый токен."
            )
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_set_token: {e}")
            await self.send_message(f"❌ Ошибка при обновлении токена: {str(e)}")
    
    async def cmd_stop_system(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stop"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            if self.system_control and hasattr(self.system_control, 'stop'):
                await self.system_control.stop()
                
                # Получение количества активных позиций
                positions = await self.db.get_open_positions()
                
                await update.message.reply_text(
                    "⏸️ <b>Система остановлена</b>\n\n"
                    f"📊 Активных позиций: <b>{len(positions)}</b>\n"
                    f"🔴 Мониторинг: <b>выключен</b>\n"
                    f"🔴 Автоордера: <b>выключены</b>\n\n"
                    "Используйте <code>/start</code> для возобновления работы",
                    parse_mode='HTML'
                )
                
                logger.info("Система остановлена через Telegram бот")
            else:
                await update.message.reply_text(
                    "❌ <b>Ошибка</b>\n\n"
                    "Управление системой недоступно.\n"
                    "Функция остановки не реализована.",
                    parse_mode='HTML'
                )
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_stop_system: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    # Команды управления аккаунтами
    
    async def cmd_accounts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /accounts - список всех аккаунтов"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            accounts = await self.db.get_all_accounts()
            
            if not accounts:
                await update.message.reply_text("📭 Нет добавленных аккаунтов")
                return
            
            text = "📊 <b>Счета Tinkoff</b>\n\n"
            
            for acc in accounts:
                status = "🟢" if acc.is_active else "⚪"
                active_label = " (активный)" if acc.is_active else ""
                last_used = acc.last_used_at.strftime('%d.%m.%Y %H:%M') if acc.last_used_at else "никогда"
                
                text += (
                    f"{status} <b>{acc.name}</b>{active_label}\n"
                    f"   🆔 ID: <code>{acc.account_id}</code>\n"
                    f"   📄 {acc.description or 'без описания'}\n"
                    f"   🕐 Последнее использование: {last_used}\n\n"
                )
            
            await update.message.reply_text(text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_accounts: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def cmd_add_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /add_account - добавить новый аккаунт"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            # Удалить сообщение с токеном
            try:
                await update.message.delete()
            except:
                pass
            
            # Валидация аргументов
            if len(context.args) < 3:
                await self.send_message(
                    "❌ <b>Использование:</b>\n"
                    "<code>/add_account название токен account_id [описание]</code>\n\n"
                    "<b>Пример:</b>\n"
                    "<code>/add_account main t.xxx... 2000012345 Основной счет</code>\n\n"
                    "⚠️ Сообщение с токеном будет автоматически удалено"
                )
                return
            
            name = context.args[0]
            token = context.args[1]
            account_id = context.args[2]
            description = " ".join(context.args[3:]) if len(context.args) > 3 else None
            
            # Добавить аккаунт в БД
            account = await self.db.add_account(name, token, account_id, description)
            
            await self.send_message(
                f"✅ <b>Аккаунт добавлен!</b>\n\n"
                f"📝 Название: <b>{name}</b>\n"
                f"🆔 Account ID: <code>{account_id}</code>\n"
                f"📄 Описание: {description or 'не указано'}\n\n"
                f"Используйте <code>/switch_account {name}</code> для переключения"
            )
            
        except ValueError as e:
            await self.send_message(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"Ошибка в cmd_add_account: {e}")
            await self.send_message(f"❌ Ошибка: {str(e)}")
    
    async def cmd_switch_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /switch_account - переключить активный аккаунт"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            if not context.args:
                await update.message.reply_text(
                    "❌ <b>Использование:</b> <code>/switch_account название</code>",
                    parse_mode='HTML'
                )
                return
            
            account_name = context.args[0]
            
            # Отправить уведомление о начале переключения
            await update.message.reply_text(
                f"🔄 Переключаюсь на аккаунт <b>{account_name}</b>...\n"
                f"⏳ Переподключение к API...",
                parse_mode='HTML'
            )
            
            # Вызвать горячее переподключение
            if self.system_control and hasattr(self.system_control, 'reload_api_client'):
                await self.system_control.reload_api_client(account_name)
                
                # Получить информацию о новом активном аккаунте
                account = await self.db.get_active_account()
                
                await self.send_message(
                    f"✅ <b>Переключение завершено!</b>\n\n"
                    f"🟢 Активный аккаунт: <b>{account.name}</b>\n"
                    f"🆔 Account ID: <code>{account.account_id}</code>\n"
                    f"📄 Описание: {account.description or 'не указано'}\n\n"
                    f"🔄 Система работает без перезапуска!"
                )
            else:
                await update.message.reply_text("❌ Функция переключения недоступна")
                
        except ValueError as e:
            await self.send_message(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"Ошибка в cmd_switch_account: {e}")
            await self.send_message(f"❌ Ошибка при переключении: {str(e)}")
    
    async def cmd_current_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /current_account - показать текущий активный аккаунт"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            account = await self.db.get_active_account()
            
            if not account:
                await update.message.reply_text("❌ Активный аккаунт не найден")
                return
            
            last_used = account.last_used_at.strftime('%d.%m.%Y %H:%M:%S') if account.last_used_at else "никогда"
            
            text = (
                f"🟢 <b>Активный аккаунт</b>\n\n"
                f"📝 Название: <b>{account.name}</b>\n"
                f"🆔 Account ID: <code>{account.account_id}</code>\n"
                f"📄 Описание: {account.description or 'не указано'}\n"
                f"🕐 Последнее использование: {last_used}\n"
                f"📅 Создан: {account.created_at.strftime('%d.%m.%Y %H:%M')}"
            )
            
            await update.message.reply_text(text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_current_account: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def cmd_remove_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /remove_account - удалить аккаунт"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            if not context.args:
                await update.message.reply_text(
                    "❌ <b>Использование:</b> <code>/remove_account название</code>",
                    parse_mode='HTML'
                )
                return
            
            account_name = context.args[0]
            
            # Проверить, не активный ли это аккаунт
            account = await self.db.get_account_by_name(account_name)
            if not account:
                await update.message.reply_text(f"❌ Аккаунт '{account_name}' не найден")
                return
            
            if account.is_active:
                await update.message.reply_text(
                    f"⚠️ <b>Нельзя удалить активный аккаунт!</b>\n"
                    f"Сначала переключитесь на другой аккаунт.",
                    parse_mode='HTML'
                )
                return
            
            # Удалить
            success = await self.db.remove_account(account_name)
            
            if success:
                await update.message.reply_text(
                    f"✅ Аккаунт <b>{account_name}</b> удален",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(f"❌ Не удалось удалить аккаунт")
                
        except ValueError as e:
            await update.message.reply_text(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"Ошибка в cmd_remove_account: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
