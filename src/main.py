import asyncio
import argparse
import signal
import sys
from pathlib import Path
from typing import Dict, Optional, Any

from src.config.loader import load_config
from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.storage.database import Database
from src.core.position_manager import PositionManager
from src.core.risk_calculator import RiskCalculator
from src.core.order_executor import OrderExecutor
from src.core.stream_handler import StreamHandler
from src.strategies.stock_sl_tp import StockStrategy
from src.strategies.futures_sl_tp import FuturesStrategy
from src.strategies.multi_tp import MultiTakeProfitStrategy
from src.notifications.telegram import TelegramNotifier
from src.utils.logger import setup_logger, get_logger

logger = get_logger("main")


class AutoStopSystem:
    """
    Основной класс системы автоматического управления стоп-лоссами и тейк-профитами
    """
    
    def __init__(self, config_path: Optional[str] = None, instruments_path: Optional[str] = None):
        """
        Инициализация системы
        
        Args:
            config_path: Путь к файлу конфигурации
            instruments_path: Путь к файлу конфигурации инструментов
        """
        self.config_path = config_path
        self.instruments_path = instruments_path
        
        # Компоненты системы
        self.config = None
        self.instruments_config = None
        self.api_client = None
        self.database = None
        self.instrument_cache = None
        self.position_manager = None
        self.risk_calculator = None
        self.order_executor = None
        self.stream_handler = None
        self.telegram_notifier = None
        
        # Стратегии
        self.strategies = {}
        
        # Флаг работы системы
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self):
        """
        Инициализация компонентов системы
        """
        try:
            # Загрузка конфигурации
            self.config, self.instruments_config = load_config(
                config_path=self.config_path,
                instruments_path=self.instruments_path
            )
            
            # Настройка логирования
            setup_logger(self.config.logging)
            
            # Инициализация базы данных
            self.database = Database()
            await self.database.create_tables()
            
            # Инициализация API клиента
            self.api_client = TinkoffAPIClient(
                token=self.config.api.token,
                app_name=self.config.api.app_name
            )
            await self.api_client.__aenter__()
            
            # Инициализация кэша инструментов
            self.instrument_cache = InstrumentInfoCache(self.api_client)
            
            # Инициализация менеджера позиций
            self.position_manager = PositionManager(
                database=self.database,
                instrument_cache=self.instrument_cache
            )
            await self.position_manager.initialize()
            
            # Очистка старых позиций из БД при запуске
            # Система работает только с позициями, открытыми после запуска
            logger.info("Очистка старых позиций из базы данных...")
            await self.database.clear_all_positions()
            
            # Очистка кэша позиций после очистки БД
            self.position_manager.clear_cache()
            
            # СИНХРОНИЗАЦИЯ ОТКЛЮЧЕНА
            # Система НЕ подхватывает позиции, открытые до запуска
            # SL/TP выставляются только на новые позиции, открытые после запуска системы
            logger.info("Синхронизация позиций отключена. Система будет отслеживать только новые позиции.")
            
            # Инициализация калькулятора рисков
            self.risk_calculator = RiskCalculator(
                default_settings=self.config.default_settings,
                instrument_cache=self.instrument_cache
            )
            
            # Инициализация исполнителя ордеров
            self.order_executor = OrderExecutor(
                api_client=self.api_client,
                database=self.database
            )
            
            # Инициализация стратегий
            self._initialize_strategies()
            
            # Инициализация Telegram уведомлений
            if self.config.telegram and self.config.telegram.bot_token and self.config.telegram.chat_id:
                self.telegram_notifier = TelegramNotifier(settings=self.config.telegram)
                await self.telegram_notifier.start()
            
            # Инициализация обработчика потоков
            self.stream_handler = StreamHandler(
                api_client=self.api_client,
                database=self.database,
                position_manager=self.position_manager,
                risk_calculator=self.risk_calculator,
                order_executor=self.order_executor,
                config=self.config,
                instruments_config=self.instruments_config,
                instrument_cache=self.instrument_cache
            )
            
            logger.info("Система инициализирована успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации системы: {e}")
            await self.shutdown()
            return False
    
    def _initialize_strategies(self):
        """
        Инициализация стратегий
        """
        # Стратегия для акций
        self.strategies["stock"] = StockStrategy(
            risk_calculator=self.risk_calculator,
            order_executor=self.order_executor
        )
        
        # Стратегия для фьючерсов
        self.strategies["futures"] = FuturesStrategy(
            risk_calculator=self.risk_calculator,
            order_executor=self.order_executor
        )
        
        # Стратегия для многоуровневого тейк-профита
        self.strategies["multi_tp"] = MultiTakeProfitStrategy(
            risk_calculator=self.risk_calculator,
            order_executor=self.order_executor
        )
    
    async def start(self):
        """
        Запуск системы
        """
        if self._running:
            logger.warning("Система уже запущена")
            return
        
        if not self.config or not self.stream_handler:
            logger.error("Система не инициализирована")
            return
        
        if not self.config.account_id:
            logger.error("Не указан ID счета в конфигурации")
            return
        
        try:
            # Запускаем обработчик потоков
            await self.stream_handler.start(self.config.account_id)
            
            self._running = True
            logger.info(f"Система запущена для счета {self.config.account_id}")
            
            # Ожидаем сигнала завершения
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Ошибка при запуске системы: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """
        Завершение работы системы
        """
        if not self._running:
            return
        
        logger.info("Начинаем завершение работы системы...")
        self._running = False
        
        try:
            # Останавливаем обработчик потоков с таймаутом
            if self.stream_handler:
                logger.info("Останавливаем обработчик потоков...")
                try:
                    await asyncio.wait_for(self.stream_handler.stop(), timeout=5.0)
                    logger.info("Обработчик потоков остановлен")
                except asyncio.TimeoutError:
                    logger.warning("Таймаут при остановке обработчика потоков (5 сек)")
            
            # Останавливаем Telegram уведомления с таймаутом
            if self.telegram_notifier:
                logger.info("Останавливаем Telegram уведомления...")
                try:
                    await asyncio.wait_for(self.telegram_notifier.stop(), timeout=2.0)
                    logger.info("Telegram уведомления остановлены")
                except asyncio.TimeoutError:
                    logger.warning("Таймаут при остановке Telegram уведомлений (2 сек)")
            
            # Закрываем API клиент с таймаутом
            if self.api_client:
                logger.info("Закрываем API клиент...")
                try:
                    await asyncio.wait_for(
                        self.api_client.__aexit__(None, None, None),
                        timeout=3.0
                    )
                    logger.info("API клиент закрыт")
                except asyncio.TimeoutError:
                    logger.warning("Таймаут при закрытии API клиента (3 сек)")
            
            logger.info("Система остановлена")
            
        except Exception as e:
            logger.error(f"Ошибка при завершении работы: {e}")
        finally:
            # Устанавливаем событие завершения в любом случае
            self._shutdown_event.set()
    
    def signal_handler(self, sig, frame):
        """
        Обработчик сигналов завершения
        """
        logger.info(f"Получен сигнал {sig}, завершаем работу...")
        
        # Получаем текущий event loop
        try:
            loop = asyncio.get_event_loop()
            # Планируем завершение в event loop потокобезопасным способом
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self.shutdown()))
        except RuntimeError:
            # Если event loop недоступен, устанавливаем событие завершения напрямую
            self._shutdown_event.set()


async def main():
    """
    Точка входа в приложение
    """
    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description="Система автоматического управления стоп-лоссами и тейк-профитами")
    parser.add_argument("--config", help="Путь к файлу конфигурации")
    parser.add_argument("--instruments", help="Путь к файлу конфигурации инструментов")
    args = parser.parse_args()
    
    # Создание и инициализация системы
    system = AutoStopSystem(
        config_path=args.config,
        instruments_path=args.instruments
    )
    
    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, system.signal_handler)
    signal.signal(signal.SIGTERM, system.signal_handler)
    
    # Инициализация и запуск системы
    if await system.initialize():
        await system.start()


if __name__ == "__main__":
    asyncio.run(main())
