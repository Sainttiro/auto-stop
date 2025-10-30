"""
Обработчики команд для работы с позициями
"""

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers.base import BaseHandler
from src.utils.logger import get_logger

logger = get_logger("bot.handlers.positions")


class PositionsHandler(BaseHandler):
    """
    Обработчики команд для работы с позициями
    
    Команды:
    - /positions - Список открытых позиций
    """
    
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /positions"""
        try:
            # Проверка авторизации
            if not self._check_auth(update):
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
