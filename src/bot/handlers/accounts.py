"""
Обработчики команд для управления аккаунтами
"""

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers.base import BaseHandler
from src.utils.logger import get_logger

logger = get_logger("bot.handlers.accounts")


class AccountsHandler(BaseHandler):
    """
    Обработчики команд для управления аккаунтами
    
    Команды:
    - /accounts - Список всех аккаунтов
    - /add_account - Добавить новый аккаунт
    - /switch_account - Переключить активный аккаунт
    - /current_account - Показать текущий активный аккаунт
    - /remove_account - Удалить аккаунт
    """
    
    async def cmd_accounts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /accounts - список всех аккаунтов"""
        try:
            # Проверка авторизации
            if not self._check_auth(update):
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
            if not self._check_auth(update):
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
            if not self._check_auth(update):
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
            if not self._check_auth(update):
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
            if not self._check_auth(update):
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
