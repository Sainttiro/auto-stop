"""
Telegram Bot для управления системой Auto-Stop
"""

import asyncio
import os
from typing import Optional
from datetime import datetime, timedelta
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
            self.application.add_handler(CommandHandler("stop", self.cmd_stop_system))
            self.application.add_handler(CommandHandler("help", self.cmd_help))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            self.application.add_handler(CommandHandler("positions", self.cmd_positions))
            self.application.add_handler(CommandHandler("stats", self.cmd_stats))
            self.application.add_handler(CommandHandler("logs", self.cmd_logs))
            self.application.add_handler(CommandHandler("set_token", self.cmd_set_token))
            
            # Команды управления аккаунтами
            self.application.add_handler(CommandHandler("accounts", self.cmd_accounts))
            self.application.add_handler(CommandHandler("add_account", self.cmd_add_account))
            self.application.add_handler(CommandHandler("switch_account", self.cmd_switch_account))
            self.application.add_handler(CommandHandler("current_account", self.cmd_current_account))
            self.application.add_handler(CommandHandler("remove_account", self.cmd_remove_account))
            
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
            "<b>Информация:</b>\n"
            "/status - Статус системы (uptime, состояние)\n"
            "/positions - Список открытых позиций\n"
            "/stats - Статистика по сделкам\n"
            "/logs - Последние события\n\n"
            "<b>Управление аккаунтами:</b>\n"
            "/accounts - Список всех счетов\n"
            "/current_account - Текущий активный счет\n"
            "/add_account - Добавить новый счет\n"
            "/switch_account - Переключить счет (без перезапуска!)\n"
            "/remove_account - Удалить счет\n\n"
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
