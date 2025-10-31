"""
Базовый класс для обработчиков команд Telegram бота
"""

from telegram import Update

from src.utils.logger import get_logger

logger = get_logger("bot.handlers")


class BaseHandler:
    """
    Базовый класс для всех обработчиков команд
    
    Содержит общую функциональность и доступ к компонентам системы
    """
    
    def __init__(self, bot_instance):
        """
        Инициализация базового обработчика
        
        Args:
            bot_instance: Экземпляр TelegramBot
        """
        self.bot = bot_instance
        self.db = bot_instance.db
        self.chat_id = bot_instance.chat_id
        self.position_manager = bot_instance.position_manager
        self.system_control = bot_instance.system_control
        self.operations_cache = bot_instance.operations_cache
        self.statistics_calculator = bot_instance.statistics_calculator
        self.report_formatter = bot_instance.report_formatter
        self.settings_manager = bot_instance.settings_manager
    
    def _check_auth(self, update: Update) -> bool:
        """
        Проверка авторизации пользователя
        
        Args:
            update: Объект обновления Telegram
            
        Returns:
            True если пользователь авторизован, иначе False
        """
        return str(update.effective_chat.id) == self.chat_id
    
    async def send_message(self, text: str):
        """
        Отправка сообщения в чат
        
        Args:
            text: Текст сообщения
        """
        await self.bot.send_message(text)
