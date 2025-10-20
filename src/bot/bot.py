"""
Telegram Bot для управления системой Auto-Stop
"""

import asyncio
from typing import Optional
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

from src.storage.database import Database
from src.core.position_manager import PositionManager
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
        system_control: Optional[object] = None
    ):
        """
        Инициализация бота
        
        Args:
            token: Токен Telegram бота
            chat_id: ID чата для уведомлений
            database: База данных
            position_manager: Менеджер позиций
            system_control: Объект для управления системой (start/stop)
        """
        self.token = token
        self.chat_id = chat_id
        self.db = database
        self.position_manager = position_manager
        self.system_control = system_control
        
        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None
        self._running = False
        self.start_time = datetime.utcnow()
    
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
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("help", self.cmd_help))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            self.application.add_handler(CommandHandler("positions", self.cmd_positions))
            self.application.add_handler(CommandHandler("stats", self.cmd_stats))
            self.application.add_handler(CommandHandler("logs", self.cmd_logs))
            
            # Запуск бота
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
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
            "<b>/status</b> - Показывает статус системы (работает/остановлена, uptime)\n"
            "<b>/positions</b> - Список текущих открытых позиций с P&L\n"
            "<b>/stats</b> - Статистика по сделкам и прибыли\n"
            "<b>/logs</b> - Последние 10 записей из логов\n"
            "<b>/help</b> - Эта справка\n\n"
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
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats"""
        try:
            # Проверка авторизации
            if str(update.effective_chat.id) != self.chat_id:
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            # Получение статистики
            total_trades = await self.db.get_total_trades_count()
            open_positions = await self.db.get_open_positions()
            
            text = (
                "📊 <b>Статистика</b>\n\n"
                f"📝 Всего сделок: <b>{total_trades}</b>\n"
                f"📈 Открытых позиций: <b>{len(open_positions)}</b>\n"
            )
            
            await update.message.reply_text(text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_stats: {e}")
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
                    f"{emoji} <code>{event.timestamp.strftime('%H:%M:%S')}</code> "
                    f"{event.event_type}\n"
                    f"  {event.description[:100]}\n\n"
                )
            
            await update.message.reply_text(text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_logs: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
