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
from src.bot.bot import TelegramBot
from src.analytics import OperationsFetcher, OperationsCache, StatisticsCalculator, ReportFormatter
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
        self.telegram_bot = None
        
        # Компоненты аналитики
        self.operations_fetcher = None
        self.operations_cache = None
        self.statistics_calculator = None
        self.report_formatter = None
        
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
            
            # Выполнение необходимых миграций БД
            await self.database.run_migrations()
            
            # ПРИОРИТЕТ: Токен из БД > Токен из .env
            active_account = await self.database.get_active_account()
            
            if active_account:
                # Используем токен из БД
                token = active_account.token
                account_id = active_account.account_id
                logger.info(f"🔑 Используется аккаунт из БД: {active_account.name} (ID: {account_id})")
            else:
                # Fallback на токен из .env
                token = self.config.api.token
                account_id = self.config.account_id
                logger.warning("⚠️ Активный аккаунт не найден в БД, используется токен из конфигурации")
            
            # Инициализация API клиента
            self.api_client = TinkoffAPIClient(
                token=token,
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
            
            # Инициализация менеджера настроек
            from src.config.settings_manager import SettingsManager
            self.settings_manager = SettingsManager(self.database)
            
            # Инициализация калькулятора рисков
            self.risk_calculator = RiskCalculator(
                default_settings=self.config.default_settings,
                instrument_cache=self.instrument_cache,
                settings_manager=self.settings_manager
            )
            
            # Инициализация исполнителя ордеров
            self.order_executor = OrderExecutor(
                api_client=self.api_client,
                database=self.database,
                instrument_cache=self.instrument_cache
            )
            
            # Инициализация стратегий
            self._initialize_strategies()
            
            # Инициализация компонентов аналитики
            self._initialize_analytics()
            
            # Инициализация Telegram уведомлений
            if self.config.telegram and self.config.telegram.bot_token and self.config.telegram.chat_id:
                self.telegram_notifier = TelegramNotifier(settings=self.config.telegram)
                await self.telegram_notifier.start()
                
                # Инициализация интерактивного Telegram бота
                self.telegram_bot = TelegramBot(
                    token=self.config.telegram.bot_token,
                    chat_id=self.config.telegram.chat_id,
                    database=self.database,
                    position_manager=self.position_manager,
                    system_control=self,
                    operations_cache=self.operations_cache,
                    statistics_calculator=self.statistics_calculator,
                    report_formatter=self.report_formatter
                )
                await self.telegram_bot.start()
            
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
    
    def _initialize_analytics(self):
        """
        Инициализация компонентов аналитики
        """
        # Инициализация fetcher для получения операций из API
        self.operations_fetcher = OperationsFetcher(
            api_client=self.api_client,
            instrument_cache=self.instrument_cache
        )
        
        # Инициализация кэша операций
        self.operations_cache = OperationsCache(
            database=self.database,
            fetcher=self.operations_fetcher
        )
        
        # Инициализация калькулятора статистики
        self.statistics_calculator = StatisticsCalculator()
        
        # Инициализация форматтера отчетов
        self.report_formatter = ReportFormatter()
        
        logger.info("Компоненты аналитики инициализированы")
    
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
        
        # Получаем account_id из активного аккаунта или из конфигурации
        active_account = await self.database.get_active_account()
        if active_account:
            account_id = active_account.account_id
        else:
            account_id = self.config.account_id
        
        if not account_id:
            logger.error("Не указан ID счета")
            return
        
        try:
            # Запускаем обработчик потоков
            await self.stream_handler.start(account_id)
            
            self._running = True
            logger.info(f"Система запущена для счета {account_id}")
            
            # Обновляем last_used_at если используется аккаунт из БД
            if active_account:
                await self.database.update_account_last_used(account_id)
            
            # Ожидаем сигнала завершения
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Ошибка при запуске системы: {e}")
        finally:
            await self.shutdown()
    
    async def reload_api_client(self, new_account_name: Optional[str] = None):
        """
        Горячее переподключение к API с новым токеном
        
        Args:
            new_account_name: Имя аккаунта для переключения (если None - перечитать активный)
        """
        logger.info("Начинаем переподключение API клиента...")
        
        try:
            # 1. Переключить аккаунт в БД (если указан)
            if new_account_name:
                success = await self.database.switch_account(new_account_name)
                if not success:
                    raise ValueError(f"Аккаунт {new_account_name} не найден")
            
            # 2. Получить активный аккаунт из БД
            active_account = await self.database.get_active_account()
            if not active_account:
                raise ValueError("Активный аккаунт не найден в БД")
            
            # 3. Остановить текущий stream handler
            if self.stream_handler:
                logger.info("Останавливаем stream handler...")
                await self.stream_handler.stop()
            
            # 4. Закрыть текущий API клиент
            if self.api_client:
                logger.info("Закрываем текущий API клиент...")
                await self.api_client.__aexit__(None, None, None)
            
            # 5. Создать новый API клиент с новым токеном
            logger.info(f"Создаем новый API клиент для аккаунта '{active_account.name}'...")
            self.api_client = TinkoffAPIClient(
                token=active_account.token,
                app_name=self.config.api.app_name
            )
            await self.api_client.__aenter__()
            
            # 6. Переинициализировать зависимые компоненты
            logger.info("Переинициализируем зависимые компоненты...")
            self.instrument_cache = InstrumentInfoCache(self.api_client)
            
            self.order_executor = OrderExecutor(
                api_client=self.api_client,
                database=self.database,
                instrument_cache=self.instrument_cache
            )
            
            # Переинициализировать стратегии с новым executor
            self._initialize_strategies()
            
            # 7. Создать новый stream handler
            logger.info("Создаем новый stream handler...")
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
            
            # 8. Запустить stream handler с новым account_id
            logger.info(f"Запускаем stream handler для аккаунта {active_account.account_id}...")
            await self.stream_handler.start(active_account.account_id)
            
            # 9. Обновить last_used_at
            await self.database.update_account_last_used(active_account.account_id)
            
            logger.info(f"✅ Переподключение завершено. Активный аккаунт: {active_account.name}")
            
            # Отправить уведомление в Telegram
            if self.telegram_bot:
                await self.telegram_bot.send_message(
                    f"✅ Переключение на аккаунт <b>{active_account.name}</b> завершено!\n"
                    f"🆔 Account ID: <code>{active_account.account_id}</code>"
                )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при переподключении: {e}")
            
            # Отправить уведомление об ошибке
            if self.telegram_bot:
                await self.telegram_bot.send_message(
                    f"❌ Ошибка при переподключении: {str(e)}"
                )
            
            raise
    
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
            
            # Останавливаем Telegram бота с таймаутом
            if self.telegram_bot:
                logger.info("Останавливаем Telegram бота...")
                try:
                    await asyncio.wait_for(self.telegram_bot.stop(), timeout=2.0)
                    logger.info("Telegram бот остановлен")
                except asyncio.TimeoutError:
                    logger.warning("Таймаут при остановке Telegram бота (2 сек)")
            
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
