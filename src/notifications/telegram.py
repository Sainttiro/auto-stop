import asyncio
from typing import Optional, Dict, Any
import json
from datetime import datetime

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from src.config.settings import TelegramSettings
from src.utils.logger import get_logger

logger = get_logger("notifications.telegram")


class TelegramNotifier:
    """
    Отправка уведомлений через Telegram
    """
    
    def __init__(self, settings: TelegramSettings):
        """
        Инициализация уведомлений Telegram
        
        Args:
            settings: Настройки Telegram
        """
        self.bot_token = settings.bot_token
        self.chat_id = settings.chat_id
        self.enabled_notifications = set(settings.notifications)
        self._bot: Optional[Bot] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """
        Запуск обработчика уведомлений
        """
        if self._running:
            logger.warning("Обработчик уведомлений Telegram уже запущен")
            return
        
        if not self.bot_token or not self.chat_id:
            logger.error("Не настроены токен бота или ID чата Telegram")
            return
        
        try:
            self._bot = Bot(token=self.bot_token)
            await self._bot.get_me()  # Проверка подключения
            
            self._running = True
            self._worker_task = asyncio.create_task(self._process_queue())
            
            logger.info("Обработчик уведомлений Telegram запущен")
            
            # Отправляем тестовое сообщение
            await self.send_notification(
                "system_start",
                "🚀 Система автоматического управления стоп-лоссами и тейк-профитами запущена"
            )
            
        except TelegramError as e:
            logger.error(f"Ошибка при инициализации Telegram бота: {e}")
            self._bot = None
    
    async def stop(self):
        """
        Остановка обработчика уведомлений
        """
        if not self._running:
            return
        
        self._running = False
        
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        
        logger.info("Обработчик уведомлений Telegram остановлен")
    
    async def send_notification(
        self,
        event_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Отправка уведомления
        
        Args:
            event_type: Тип события
            message: Текст сообщения
            details: Детали события
        """
        if not self._running or not self._bot:
            logger.warning(f"Обработчик уведомлений Telegram не запущен, пропускаем: {message}")
            return
        
        # Проверяем, включен ли этот тип уведомлений
        if event_type not in self.enabled_notifications and "errors" != event_type:
            logger.debug(f"Уведомление типа {event_type} отключено, пропускаем")
            return
        
        # Добавляем в очередь
        await self._queue.put((event_type, message, details))
    
    async def _process_queue(self):
        """
        Обработка очереди уведомлений
        """
        while self._running:
            try:
                # Получаем сообщение из очереди
                event_type, message, details = await self._queue.get()
                
                # Формируем текст сообщения
                text = self._format_message(event_type, message, details)
                
                # Отправляем сообщение
                await self._bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML
                )
                
                # Отмечаем задачу как выполненную
                self._queue.task_done()
                
                # Небольшая задержка, чтобы не превысить лимиты Telegram API
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления Telegram: {e}")
                await asyncio.sleep(1)  # Задержка перед повторной попыткой
    
    def _format_message(self, event_type: str, message: str, details: Optional[Dict[str, Any]]) -> str:
        """
        Форматирование сообщения
        
        Args:
            event_type: Тип события
            message: Текст сообщения
            details: Детали события
            
        Returns:
            str: Отформатированное сообщение
        """
        # Добавляем эмодзи в зависимости от типа события
        emoji = self._get_emoji_for_event(event_type)
        
        # Форматируем основное сообщение
        formatted_message = f"{emoji} <b>{message}</b>"
        
        # Добавляем детали, если они есть
        if details:
            details_text = "\n\n<b>Детали:</b>\n"
            for key, value in details.items():
                # Форматируем значение, если это словарь или список
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, indent=2)
                details_text += f"• <b>{key}:</b> {value}\n"
            
            formatted_message += details_text
        
        # Добавляем время
        now = datetime.now().strftime("%H:%M:%S")
        formatted_message += f"\n\n<i>Время: {now}</i>"
        
        return formatted_message
    
    def _get_emoji_for_event(self, event_type: str) -> str:
        """
        Получение эмодзи для типа события
        
        Args:
            event_type: Тип события
            
        Returns:
            str: Эмодзи
        """
        emoji_map = {
            "trade_executed": "🔄",
            "order_placed": "📝",
            "stop_triggered": "🛑",
            "take_profit_triggered": "💰",
            "position_created": "➕",
            "position_closed": "➖",
            "position_updated": "📊",
            "multi_tp_setup": "🎯",
            "multi_tp_triggered": "🎯",
            "errors": "❌",
            "system_start": "🚀",
            "system_stop": "🛑",
            "stream_error": "⚠️",
        }
        
        return emoji_map.get(event_type, "ℹ️")
