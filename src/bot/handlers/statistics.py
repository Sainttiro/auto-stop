"""
Обработчики команд для работы со статистикой
"""

from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers.base import BaseHandler
from src.utils.logger import get_logger

logger = get_logger("bot.handlers.statistics")


class StatisticsHandler(BaseHandler):
    """
    Обработчики команд для работы со статистикой
    
    Команды:
    - /stats [период] [год] - Общая статистика
    - /stats_detailed - Детальная статистика за сегодня
    - /stats_instrument <ticker> [период] - Статистика по инструменту
    """
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats [период] [год]"""
        try:
            # Проверка авторизации
            if not self._check_auth(update):
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
    
    async def cmd_stats_detailed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats_detailed - детальная статистика сделок за сегодня"""
        try:
            # Проверка авторизации
            if not self._check_auth(update):
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
            
            # Форматирование детального отчета с актуальными позициями от брокера
            report = await self.report_formatter.format_detailed_report(
                stats, 
                operations=operations,
                period="day",
                start_year=datetime.now().year,
                api_client=self.api_client,
                account_id=active_account.account_id,
                instrument_cache=self.instrument_cache
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
    
    async def cmd_stats_instrument(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats_instrument <ticker> [период]"""
        try:
            # Проверка авторизации
            if not self._check_auth(update):
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
