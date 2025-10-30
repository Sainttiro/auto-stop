"""
Обработчики системных команд Telegram бота
"""

from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers.base import BaseHandler
from src.utils.logger import get_logger

logger = get_logger("bot.handlers.system")


class SystemHandler(BaseHandler):
    """
    Обработчики системных команд
    
    Команды:
    - /start - Приветствие
    - /help - Справка
    - /status - Статус системы
    - /logs - Последние логи
    - /set_token - Обновление токена
    - /stop - Остановка системы
    """
    
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
            if not self._check_auth(update):
                await update.message.reply_text("❌ Доступ запрещен")
                return
            
            # Расчет uptime
            uptime = datetime.utcnow() - self.bot.start_time
            hours = int(uptime.total_seconds() // 3600)
            minutes = int((uptime.total_seconds() % 3600) // 60)
            
            status_text = (
                "📊 <b>Статус системы</b>\n\n"
                f"🟢 Статус: <b>Работает</b>\n"
                f"⏱ Uptime: <b>{hours}ч {minutes}м</b>\n"
                f"📅 Запущена: <b>{self.bot.start_time.strftime('%d.%m.%Y %H:%M:%S')} UTC</b>\n"
            )
            
            await update.message.reply_text(status_text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Ошибка в cmd_status: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /logs"""
        try:
            # Проверка авторизации
            if not self._check_auth(update):
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
            if not self._check_auth(update):
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
            if not self._check_auth(update):
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
