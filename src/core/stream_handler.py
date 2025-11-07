"""
Координатор потоков данных через gRPC
"""
from typing import Optional, Dict, Any

from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.core.position_manager import PositionManager
from src.core.risk_calculator import RiskCalculator
from src.core.order_executor import OrderExecutor
from src.core.cleanup_scheduler import CleanupScheduler
from src.storage.database import Database
from src.config.settings import InstrumentsConfig, Config
from src.config.settings_manager import SettingsManager
from src.utils.logger import get_logger

# Импортируем компоненты для работы с потоками
from src.core.streams.activation_checker import ActivationChecker
from src.core.streams.stream_monitor import StreamMonitor
from src.core.streams.trades_processor import TradesProcessor
from src.core.streams.positions_processor import PositionsProcessor

logger = get_logger("core.stream_handler")


class StreamHandler:
    """
    Координатор потоков данных через gRPC
    
    Управляет жизненным циклом потоков и делегирует обработку специализированным компонентам.
    """
    
    def __init__(
        self,
        api_client: TinkoffAPIClient,
        database: Database,
        position_manager: PositionManager,
        risk_calculator: RiskCalculator,
        order_executor: OrderExecutor,
        config: Config,
        instruments_config: InstrumentsConfig,
        instrument_cache: InstrumentInfoCache,
        settings_manager: SettingsManager
    ):
        """
        Инициализация координатора потоков
        
        Args:
            api_client: Клиент API Tinkoff
            database: Объект для работы с базой данных
            position_manager: Менеджер позиций
            risk_calculator: Калькулятор рисков
            order_executor: Исполнитель ордеров
            config: Основная конфигурация
            instruments_config: Конфигурация инструментов
            instrument_cache: Кэш информации об инструментах
            settings_manager: Менеджер настроек
        """
        self.api_client = api_client
        self.db = database
        self.position_manager = position_manager
        self.risk_calculator = risk_calculator
        self.order_executor = order_executor
        self.config = config
        self.instruments_config = instruments_config
        self.instrument_cache = instrument_cache
        self.settings_manager = settings_manager
        
        # Флаг для управления потоками
        self._running = False
        
        # Планировщик очистки старых позиций
        self._cleanup_scheduler: Optional[CleanupScheduler] = None
        
        # Создаем компоненты для работы с потоками
        self._activation_checker = ActivationChecker(database)
        
        self._stream_monitor = StreamMonitor(
            db=database,
            monitor_interval=60,  # секунды между проверками
            stream_timeout=300    # секунды без сообщений до перезапуска (5 минут)
        )
        
        self._trades_processor = TradesProcessor(
            api_client=api_client,
            database=database,
            position_manager=position_manager,
            risk_calculator=risk_calculator,
            order_executor=order_executor,
            instrument_cache=instrument_cache,
            instruments_config=instruments_config,
            settings_manager=settings_manager,
            stream_monitor=self._stream_monitor
        )
        
        self._positions_processor = PositionsProcessor(
            api_client=api_client,
            database=database,
            position_manager=position_manager,
            risk_calculator=risk_calculator,
            order_executor=order_executor,
            instrument_cache=instrument_cache,
            instruments_config=instruments_config,
            settings_manager=settings_manager,
            activation_checker=self._activation_checker,
            stream_monitor=self._stream_monitor
        )
        
        # Устанавливаем колбэк для отправки уведомлений
        self._stream_monitor.register_notification_callback(self._send_stream_restart_notification)
    
    async def start(self, account_id: str):
        """
        Запуск обработчика потоков
        
        Args:
            account_id: ID счета
        """
        if self._running:
            logger.warning("Обработчик потоков уже запущен")
            return
        
        self._running = True
        
        # Синхронизация позиций с брокером при старте
        await self._sync_positions_with_broker(account_id)
        
        # Запуск планировщика очистки старых позиций
        await self._start_cleanup_scheduler(account_id)
        
        # Запускаем потоки
        await self._trades_processor.start(account_id)
        await self._positions_processor.start(account_id)
        
        # Запускаем мониторинг потоков
        await self._stream_monitor.start(account_id)
        
        logger.info(f"Обработчик потоков запущен для счета {account_id}")
    
    async def stop(self):
        """
        Остановка обработчика потоков
        """
        if not self._running:
            logger.warning("Обработчик потоков не запущен")
            return
        
        logger.info("Останавливаем потоки...")
        self._running = False
        
        # Останавливаем планировщик очистки
        if self._cleanup_scheduler:
            await self._cleanup_scheduler.stop()
        
        # Останавливаем компоненты
        await self._stream_monitor.stop()
        await self._trades_processor.stop()
        await self._positions_processor.stop()
        
        logger.info("Обработчик потоков остановлен")
    
    async def _sync_positions_with_broker(self, account_id: str) -> None:
        """
        Синхронизация позиций с брокером при старте
        
        Args:
            account_id: ID счета
        """
        try:
            logger.info("🔄 Синхронизация позиций с брокером...")
            
            # Обнаруживаем расхождения
            discrepancies = await self.position_manager.detect_discrepancies(
                account_id=account_id,
                api_client=self.api_client
            )
            
            # Проверяем наличие расхождений
            has_discrepancies = (
                discrepancies.get('missing_in_broker') or
                discrepancies.get('missing_in_db') or
                discrepancies.get('quantity_mismatch')
            )
            
            if has_discrepancies:
                logger.warning(
                    f"⚠️ Обнаружены расхождения между БД и брокером:\n"
                    f"  - Позиций в БД, но нет у брокера: {len(discrepancies.get('missing_in_broker', []))}\n"
                    f"  - Позиций у брокера, но нет в БД: {len(discrepancies.get('missing_in_db', []))}\n"
                    f"  - Расхождений в количестве: {len(discrepancies.get('quantity_mismatch', []))}"
                )
                
                # Устраняем расхождения
                result = await self.position_manager.resolve_discrepancies(
                    account_id=account_id,
                    api_client=self.api_client
                )
                
                logger.info(
                    f"✅ Расхождения устранены:\n"
                    f"  - Удалено из БД: {result.get('removed_from_db', 0)}\n"
                    f"  - Добавлено в БД: {result.get('added_to_db', 0)}\n"
                    f"  - Обновлено количество: {result.get('updated_quantity', 0)}"
                )
                
                # Логируем событие
                await self.db.log_event(
                    event_type="SYNC_COMPLETED",
                    account_id=account_id,
                    description="Синхронизация позиций с брокером завершена",
                    details={
                        "discrepancies": discrepancies,
                        "result": result
                    }
                )
            else:
                logger.info("✅ Расхождений не обнаружено, БД синхронизирована с брокером")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при синхронизации с брокером: {e}", exc_info=True)
            
            # Логируем ошибку
            await self.db.log_event(
                event_type="SYNC_ERROR",
                account_id=account_id,
                description=f"Ошибка при синхронизации с брокером: {str(e)}",
                details={"error": str(e)}
            )
            
            # Не пробрасываем исключение, чтобы система могла продолжить работу
            logger.warning("⚠️ Синхронизация не удалась, но система продолжит работу")
    
    async def _start_cleanup_scheduler(self, account_id: str) -> None:
        """
        Запуск планировщика очистки старых позиций
        
        Args:
            account_id: ID счета
        """
        try:
            logger.info("🧹 Запуск планировщика очистки старых позиций...")
            
            # Создаем планировщик
            self._cleanup_scheduler = CleanupScheduler(
                position_manager=self.position_manager,
                database=self.db
            )
            
            # Запускаем планировщик
            await self._cleanup_scheduler.start(account_id)
            
            logger.info("✅ Планировщик очистки запущен (время очистки: 00:01)")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске планировщика очистки: {e}", exc_info=True)
            
            # Логируем ошибку
            await self.db.log_event(
                event_type="CLEANUP_SCHEDULER_ERROR",
                account_id=account_id,
                description=f"Ошибка при запуске планировщика очистки: {str(e)}",
                details={"error": str(e)}
            )
            
            # Не пробрасываем исключение, чтобы система могла продолжить работу
            logger.warning("⚠️ Планировщик очистки не запущен, но система продолжит работу")
    
    async def _send_stream_restart_notification(self, stream_name: str, message: str) -> None:
        """
        Отправка уведомления о перезапуске потока
        
        Args:
            stream_name: Имя потока
            message: Текст сообщения
        """
        try:
            # Получаем экземпляр notifier из main.py
            # Это не идеальное решение, но работает для отправки уведомлений
            # В идеале нужно передавать notifier в конструкторе
            import sys
            main_module = sys.modules.get('__main__')
            if hasattr(main_module, 'system') and hasattr(main_module.system, 'telegram_notifier'):
                notifier = main_module.system.telegram_notifier
                if notifier:
                    await notifier.send_message(message)
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о перезапуске потока: {e}")
    
    def get_pending_activations(self) -> Dict[str, Dict[str, Any]]:
        """
        Получение списка позиций, ожидающих активации
        
        Returns:
            Dict[str, Dict[str, Any]]: Словарь позиций, ожидающих активации
        """
        return self._activation_checker.get_pending_activations()
    
    def add_pending_activation(
        self,
        figi: str,
        position_id: int,
        sl_activation_price: Optional[float],
        tp_activation_price: Optional[float]
    ) -> None:
        """
        Добавление позиции в список ожидающих активации
        
        Args:
            figi: FIGI инструмента
            position_id: ID позиции
            sl_activation_price: Цена активации стоп-лосса
            tp_activation_price: Цена активации тейк-профита
        """
        self._activation_checker.add_pending_activation(
            figi=figi,
            position_id=position_id,
            sl_activation_price=sl_activation_price,
            tp_activation_price=tp_activation_price
        )
