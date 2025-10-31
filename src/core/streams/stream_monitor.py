"""
Мониторинг здоровья потоков данных
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, Awaitable

from src.storage.database import Database
from src.utils.logger import get_logger

logger = get_logger("core.streams.stream_monitor")


class StreamMonitor:
    """
    Мониторинг здоровья потоков данных
    
    Проверяет, что потоки получают сообщения регулярно.
    Если поток не получает сообщений в течение stream_timeout секунд,
    он считается "зависшим" и перезапускается.
    """
    
    def __init__(
        self,
        db: Database,
        monitor_interval: int = 60,
        stream_timeout: int = 300
    ):
        """
        Инициализация монитора потоков
        
        Args:
            db: Объект для работы с базой данных
            monitor_interval: Интервал между проверками (секунды)
            stream_timeout: Таймаут потока (секунды)
        """
        self.db = db
        self._monitor_interval = monitor_interval  # секунды между проверками
        self._stream_timeout = stream_timeout  # секунды без сообщений до перезапуска (5 минут)
        
        # Время последнего сообщения для каждого потока
        self._last_message_times: Dict[str, datetime] = {}
        
        # Флаг работы монитора
        self._running = False
        
        # Задача мониторинга
        self._monitor_task = None
        
        # Колбэки для перезапуска потоков
        self._restart_callbacks: Dict[str, Callable[[str], Awaitable[None]]] = {}
        
        # Колбэк для отправки уведомлений
        self._notification_callback: Optional[Callable[[str, str], Awaitable[None]]] = None
    
    def register_stream(self, stream_name: str) -> None:
        """
        Регистрация потока для мониторинга
        
        Args:
            stream_name: Имя потока
        """
        self._last_message_times[stream_name] = datetime.now()
        logger.info(f"Поток {stream_name} зарегистрирован для мониторинга")
    
    def register_restart_callback(
        self,
        stream_name: str,
        callback: Callable[[str], Awaitable[None]]
    ) -> None:
        """
        Регистрация колбэка для перезапуска потока
        
        Args:
            stream_name: Имя потока
            callback: Колбэк для перезапуска потока
        """
        self._restart_callbacks[stream_name] = callback
        logger.info(f"Колбэк для перезапуска потока {stream_name} зарегистрирован")
    
    def register_notification_callback(
        self,
        callback: Callable[[str, str], Awaitable[None]]
    ) -> None:
        """
        Регистрация колбэка для отправки уведомлений
        
        Args:
            callback: Колбэк для отправки уведомлений
        """
        self._notification_callback = callback
        logger.info("Колбэк для отправки уведомлений зарегистрирован")
    
    def update_last_message_time(self, stream_name: str) -> None:
        """
        Обновление времени последнего сообщения для потока
        
        Args:
            stream_name: Имя потока
        """
        if stream_name in self._last_message_times:
            self._last_message_times[stream_name] = datetime.now()
    
    async def start(self, account_id: str) -> None:
        """
        Запуск мониторинга потоков
        
        Args:
            account_id: ID счета
        """
        if self._running:
            logger.warning("Монитор потоков уже запущен")
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_streams(account_id))
        logger.info(f"Монитор потоков запущен для счета {account_id}")
    
    async def stop(self) -> None:
        """
        Остановка мониторинга потоков
        """
        if not self._running:
            logger.warning("Монитор потоков не запущен")
            return
        
        self._running = False
        
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await asyncio.wait_for(self._monitor_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        self._monitor_task = None
        logger.info("Монитор потоков остановлен")
    
    async def _monitor_streams(self, account_id: str) -> None:
        """
        Мониторинг здоровья потоков данных
        
        Args:
            account_id: ID счета
        """
        logger.info(f"Запущен мониторинг здоровья потоков для счета {account_id}")
        
        while self._running:
            try:
                # Ждем указанный интервал между проверками
                await asyncio.sleep(self._monitor_interval)
                
                # Получаем текущее время
                now = datetime.now()
                
                # Проверяем каждый поток
                for stream_name, last_time in self._last_message_times.items():
                    idle_time = (now - last_time).total_seconds()
                    
                    # Если поток не отвечает дольше таймаута
                    if idle_time > self._stream_timeout:
                        logger.critical(
                            f"⚠️ КРИТИЧЕСКАЯ ОШИБКА: Поток {stream_name} не отвечает {idle_time:.1f} секунд "
                            f"(> {self._stream_timeout} сек). Перезапуск..."
                        )
                        
                        # Логируем событие в БД
                        await self.db.log_event(
                            event_type="STREAM_TIMEOUT",
                            account_id=account_id,
                            description=f"Поток {stream_name} не отвечает {idle_time:.1f} секунд. Перезапуск...",
                            details={
                                "stream_name": stream_name,
                                "idle_time": idle_time,
                                "timeout": self._stream_timeout
                            }
                        )
                        
                        # Перезапускаем поток
                        await self._restart_stream(stream_name, account_id)
            
            except asyncio.CancelledError:
                logger.info("Задача мониторинга потоков отменена")
                break
            except Exception as e:
                logger.error(f"Ошибка в задаче мониторинга потоков: {e}")
    
    async def _restart_stream(self, stream_name: str, account_id: str) -> None:
        """
        Перезапуск потока данных
        
        Args:
            stream_name: Имя потока
            account_id: ID счета
        """
        try:
            # Вызываем колбэк для перезапуска потока
            if stream_name in self._restart_callbacks:
                await self._restart_callbacks[stream_name](account_id)
                
                # Обновляем время последнего сообщения
                self._last_message_times[stream_name] = datetime.now()
                
                # Отправляем уведомление
                await self._send_stream_restart_notification(stream_name, account_id)
                
                logger.info(f"Поток {stream_name} успешно перезапущен")
            else:
                logger.error(f"Колбэк для перезапуска потока {stream_name} не зарегистрирован")
        
        except Exception as e:
            logger.error(f"Ошибка при перезапуске потока {stream_name}: {e}")
    
    async def _send_stream_restart_notification(self, stream_name: str, account_id: str) -> None:
        """
        Отправка уведомления о перезапуске потока
        
        Args:
            stream_name: Имя потока
            account_id: ID счета
        """
        try:
            if self._notification_callback:
                message = (
                    f"⚠️ <b>ВНИМАНИЕ! Перезапуск потока {stream_name}</b>\n\n"
                    f"Поток {stream_name} не отвечал более {self._stream_timeout} секунд "
                    f"и был автоматически перезапущен.\n\n"
                    f"<i>Account ID:</i> <code>{account_id}</code>\n"
                    f"<i>Время:</i> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                await self._notification_callback(stream_name, message)
            else:
                logger.warning("Колбэк для отправки уведомлений не зарегистрирован")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о перезапуске потока: {e}")
