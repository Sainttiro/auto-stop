"""
Обработка потока изменений позиций
"""
import asyncio
from typing import Optional, Any
from decimal import Decimal

from tinkoff.invest import PositionsStreamResponse

from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.core.position_manager import PositionManager
from src.core.risk_calculator import RiskCalculator
from src.core.order_executor import OrderExecutor
from src.storage.database import Database
from src.storage.models import Position
from src.config.settings import InstrumentsConfig
from src.config.settings_manager import SettingsManager
from src.utils.converters import quotation_to_decimal
from src.utils.logger import get_logger
from src.core.streams.activation_checker import ActivationChecker

logger = get_logger("core.streams.positions_processor")


class PositionsProcessor:
    """
    Обработка потока изменений позиций
    """
    
    def __init__(
        self,
        api_client: TinkoffAPIClient,
        database: Database,
        position_manager: PositionManager,
        risk_calculator: RiskCalculator,
        order_executor: OrderExecutor,
        instrument_cache: InstrumentInfoCache,
        instruments_config: InstrumentsConfig,
        settings_manager: SettingsManager,
        activation_checker: ActivationChecker,
        stream_monitor = None  # Будет установлен позже
    ):
        """
        Инициализация обработчика позиций
        
        Args:
            api_client: Клиент API Tinkoff
            database: Объект для работы с базой данных
            position_manager: Менеджер позиций
            risk_calculator: Калькулятор рисков
            order_executor: Исполнитель ордеров
            instrument_cache: Кэш информации об инструментах
            instruments_config: Конфигурация инструментов
            settings_manager: Менеджер настроек
            activation_checker: Проверка активации SL/TP
            stream_monitor: Монитор потоков (опционально)
        """
        self.api_client = api_client
        self.db = database
        self.position_manager = position_manager
        self.risk_calculator = risk_calculator
        self.order_executor = order_executor
        self.instrument_cache = instrument_cache
        self.instruments_config = instruments_config
        self.settings_manager = settings_manager
        self.activation_checker = activation_checker
        self.stream_monitor = stream_monitor
        
        # Флаги для управления потоком
        self._running = False
        self._positions_stream_task = None
        
        # Блокировка для синхронизации
        self._lock = asyncio.Lock()
    
    def set_stream_monitor(self, stream_monitor) -> None:
        """
        Установка монитора потоков
        
        Args:
            stream_monitor: Монитор потоков
        """
        self.stream_monitor = stream_monitor
    
    async def start(self, account_id: str) -> None:
        """
        Запуск обработчика потока позиций
        
        Args:
            account_id: ID счета
        """
        if self._running:
            logger.warning("Обработчик потока позиций уже запущен")
            return
        
        self._running = True
        self._positions_stream_task = asyncio.create_task(
            self._run_positions_stream(account_id)
        )
        
        # Регистрируем поток в мониторе
        if self.stream_monitor:
            self.stream_monitor.register_stream("positions")
            self.stream_monitor.register_restart_callback(
                "positions",
                self._restart_stream
            )
        
        logger.info(f"Обработчик потока позиций запущен для счета {account_id}")
    
    async def stop(self) -> None:
        """
        Остановка обработчика потока позиций
        """
        if not self._running:
            logger.warning("Обработчик потока позиций не запущен")
            return
        
        logger.info("Останавливаем поток позиций...")
        self._running = False
        
        if self._positions_stream_task and not self._positions_stream_task.done():
            self._positions_stream_task.cancel()
            try:
                await asyncio.wait_for(self._positions_stream_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        self._positions_stream_task = None
        logger.info("Обработчик потока позиций остановлен")
    
    async def _restart_stream(self, account_id: str) -> None:
        """
        Перезапуск потока позиций
        
        Args:
            account_id: ID счета
        """
        logger.info(f"Перезапуск потока позиций для счета {account_id}")
        
        # Отменяем текущую задачу
        if self._positions_stream_task and not self._positions_stream_task.done():
            self._positions_stream_task.cancel()
            try:
                await asyncio.wait_for(self._positions_stream_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        # Создаем новую задачу
        self._positions_stream_task = asyncio.create_task(
            self._run_positions_stream(account_id)
        )
        
        logger.info(f"Поток позиций перезапущен для счета {account_id}")
    
    async def _run_positions_stream(self, account_id: str) -> None:
        """
        Запуск потока изменений позиций
        
        Args:
            account_id: ID счета
        """
        retry_count = 0
        max_retries = 100
        retry_delay = 1.0  # секунды
        max_delay = 300.0  # Максимальная задержка 5 минут
        
        while self._running:
            try:
                logger.info(f"Подключение к потоку изменений позиций для счета {account_id}")
                
                async for response in self.api_client.services.operations_stream.positions_stream(
                    accounts=[account_id]
                ):
                    if not self._running:
                        break
                    
                    # Обновляем время последнего сообщения в мониторе
                    if self.stream_monitor:
                        self.stream_monitor.update_last_message_time("positions")
                    
                    # Обрабатываем изменение позиций
                    await self._handle_position_change(response, account_id)
                    
                    # Сбрасываем счетчик повторов при успешном получении данных
                    retry_count = 0
                
                # Если мы вышли из цикла, но _running все еще True, значит произошла ошибка
                if self._running:
                    raise Exception("Поток изменений позиций прервался")
                    
            except Exception as e:
                if not self._running:
                    break
                
                retry_count += 1
                # Экспоненциальная задержка с ограничением максимума
                delay = min(retry_delay * (2 ** min(retry_count - 1, 8)), max_delay)
                
                logger.error(f"Ошибка в потоке изменений позиций: {e}. Повторное подключение через {delay:.1f} сек... (попытка {retry_count}/{max_retries})")
                
                # Логируем событие
                await self.db.log_event(
                    event_type="STREAM_ERROR",
                    account_id=account_id,
                    description=f"Ошибка в потоке изменений позиций: {str(e)}",
                    details={"error": str(e), "retry_count": retry_count, "max_retries": max_retries}
                )
                
                # Если превышено максимальное количество попыток, логируем критическую ошибку
                # но НЕ останавливаем систему - продолжаем попытки с максимальной задержкой
                if retry_count >= max_retries:
                    logger.critical(
                        f"Превышено максимальное количество попыток ({max_retries}) подключения к потоку изменений позиций. "
                        f"Продолжаем попытки с интервалом {max_delay:.1f} сек..."
                    )
                    # Сбрасываем счетчик, чтобы продолжить попытки
                    retry_count = max_retries - 1
                
                await asyncio.sleep(delay)
    
    async def _handle_position_change(self, position_response: PositionsStreamResponse, account_id: str) -> None:
        """
        Обработка изменения позиций
        
        Args:
            position_response: Данные об изменении позиций (PositionsStreamResponse)
            account_id: ID счета
        """
        try:
            # Обработка ping-сообщений (keep-alive)
            if hasattr(position_response, 'ping') and position_response.ping:
                logger.debug("Получен ping в потоке позиций")
                return
                
            # Обработка подтверждения подписки
            if hasattr(position_response, 'subscriptions') and position_response.subscriptions:
                logger.info(f"Подписка на поток позиций подтверждена для счета {account_id}")
                return
                
            # Обработка начальных позиций при подключении
            if hasattr(position_response, 'initial_positions') and position_response.initial_positions:
                logger.info(f"Получены начальные позиции для счета {account_id}")
                # Можно обработать начальные позиции, если необходимо
                return
                
            # Обработка изменения позиции
            if not hasattr(position_response, "position") or position_response.position is None:
                logger.debug(f"Получено пустое сообщение в потоке позиций")
                return
                
            position_data = position_response.position
            
            # Проверяем наличие securities (позиций по инструментам)
            # Если securities пусто, это обновление баланса счета, а не позиций
            if not hasattr(position_data, "securities") or not position_data.securities:
                logger.debug(f"Получено обновление баланса счета {account_id}")
                return
            
            # Обрабатываем каждую позицию по инструменту
            for security in position_data.securities:
                if not hasattr(security, 'figi') or not security.figi:
                    logger.warning(f"Получена позиция без FIGI: {security}")
                    continue
                
                await self._process_security_position(security, account_id)
        
        except Exception as e:
            logger.error(f"Ошибка при обработке изменения позиций: {e}")
            
            # Логируем ошибку
            await self.db.log_event(
                event_type="ERROR",
                account_id=account_id,
                description=f"Ошибка при обработке изменения позиций: {str(e)}",
                details={"error": str(e)}
            )
    
    async def _process_security_position(self, security, account_id: str) -> None:
        """
        Обработка изменения позиции по конкретному инструменту
        
        Args:
            security: Данные о позиции по инструменту
            account_id: ID счета
        """
        try:
            figi = security.figi
            
            # Получаем новое количество из потока
            new_quantity = security.balance
            
            # Получаем информацию об инструменте
            instrument = await self.instrument_cache.get_instrument_by_figi(figi)
            if not instrument:
                logger.warning(f"Не удалось получить информацию об инструменте {figi}")
                return
            
            ticker = instrument.ticker
            instrument_type = "stock" if instrument.instrument_type.lower().startswith("share") else "futures"
            
            # Получаем среднюю цену и текущую цену из API
            avg_price = Decimal(0)
            current_price = Decimal(0)
            
            if hasattr(security, 'average_position_price') and security.average_position_price:
                avg_price = quotation_to_decimal(security.average_position_price)
            
            # Получаем текущую цену из last_price, если доступно
            if hasattr(security, 'current_price') and security.current_price:
                current_price = quotation_to_decimal(security.current_price)
            elif hasattr(security, 'last_price') and security.last_price:
                current_price = quotation_to_decimal(security.last_price)
            
            # Получаем текущую позицию из БД
            position = await self.position_manager.get_position(account_id, figi)
            
            # Проверяем активацию для существующих позиций
            if position and current_price > 0:
                # Проверяем, есть ли позиция в списке ожидающих активации
                if self.activation_checker.is_pending_activation(figi):
                    # Получаем настройки активации
                    settings = await self.settings_manager.get_effective_settings(
                        account_id=account_id,
                        ticker=position.ticker
                    )
                    
                    # Проверяем условия активации
                    sl_activated, tp_activated = await self.activation_checker.check_activation_conditions(
                        figi=figi,
                        current_price=current_price,
                        position=position,
                        settings=settings
                    )
                    
                    # Если SL активирован и раньше не был активирован
                    if sl_activated:
                        # Рассчитываем уровень SL
                        sl_price, _ = await self.risk_calculator.calculate_levels(
                            figi=figi,
                            ticker=position.ticker,
                            instrument_type=position.instrument_type,
                            avg_price=Decimal(str(position.average_price)),
                            direction=position.direction,
                            account_id=account_id
                        )
                        
                        # Выставляем SL ордер
                        await self.order_executor.place_stop_loss_order(position, sl_price)
                        
                        # Отправляем уведомление
                        await self.db.log_event(
                            event_type="SL_ORDER_PLACED",
                            account_id=account_id,
                            figi=figi,
                            ticker=position.ticker,
                            description=f"Выставлен SL ордер для {position.ticker} после активации",
                            details={
                                "price": float(sl_price),
                                "position_id": position.id
                            }
                        )
                    
                    # Если TP активирован и раньше не был активирован
                    if tp_activated:
                        # Рассчитываем уровень TP
                        _, tp_price = await self.risk_calculator.calculate_levels(
                            figi=figi,
                            ticker=position.ticker,
                            instrument_type=position.instrument_type,
                            avg_price=Decimal(str(position.average_price)),
                            direction=position.direction,
                            account_id=account_id
                        )
                        
                        # Выставляем TP ордер
                        await self.order_executor.place_take_profit_order(position, tp_price)
                        
                        # Отправляем уведомление
                        await self.db.log_event(
                            event_type="TP_ORDER_PLACED",
                            account_id=account_id,
                            figi=figi,
                            ticker=position.ticker,
                            description=f"Выставлен TP ордер для {position.ticker} после активации",
                            details={
                                "price": float(tp_price),
                                "position_id": position.id
                            }
                        )
                    
                    # Если оба активированы, удаляем из списка ожидающих
                    if sl_activated and tp_activated:
                        self.activation_checker.remove_pending_activation(figi)
            
            # СЛУЧАЙ 1: Новая позиция (открыта вручную)
            if not position and new_quantity > 0:
                if avg_price == 0:
                    logger.warning(f"Средняя цена для {ticker} недоступна, пропускаем")
                    return
                
                logger.info(
                    f"🆕 Обнаружена новая позиция из PositionsStream: {ticker}, "
                    f"количество={new_quantity}, цена={avg_price}"
                )
                
                # Создаем позицию
                position = await self.position_manager.create_position(
                    account_id=account_id,
                    figi=figi,
                    ticker=ticker,
                    instrument_type=instrument_type,
                    quantity=new_quantity,
                    price=avg_price,
                    direction="LONG"
                )
                
                # Получаем настройки инструмента
                instrument_settings = self.instruments_config.instruments.get(ticker)
                
                # Проверяем, нужно ли использовать многоуровневый тейк-профит
                use_multi_tp = False
                multi_tp_levels = []
                
                # Сначала проверяем настройки из БД (имеют высший приоритет)
                effective_settings = await self.settings_manager.get_effective_settings(
                    account_id=account_id,
                    ticker=ticker
                )
                
                if effective_settings['multi_tp_enabled']:
                    use_multi_tp = True
                    # Получаем уровни из БД
                    if effective_settings['multi_tp_levels']:
                        multi_tp_levels = [(level['level_pct'], level['volume_pct']) for level in effective_settings['multi_tp_levels']]
                        logger.debug(f"Используются уровни Multi-TP из БД для {ticker}: {len(multi_tp_levels)} уровней")
                # Если в БД не включен Multi-TP, проверяем настройки из YAML
                elif instrument_settings and instrument_settings.multi_tp and instrument_settings.multi_tp.enabled:
                    use_multi_tp = True
                    multi_tp_levels = [(level.level_pct, level.volume_pct) for level in instrument_settings.multi_tp.levels]
                    logger.debug(f"Используются уровни Multi-TP из настроек инструмента для {ticker}")
                
                logger.info(f"Режим TP для {ticker}: {'многоуровневый' if use_multi_tp else 'обычный'}")
                
                # Рассчитываем уровни SL/TP
                if use_multi_tp:
                    # Многоуровневый тейк-профит
                    logger.debug(f"Расчет многоуровневых SL/TP для {ticker}...")
                    sl_price, tp_levels = await self._calculate_multi_tp_levels(
                        position=position,
                        instrument_settings=instrument_settings,
                        account_id=account_id
                    )
                    logger.info(f"Рассчитаны уровни: SL={sl_price}, TP уровней={len(tp_levels)}")
                    
                    # Получаем sl_pct для расчета смещения цены исполнения
                    sl_pct = Decimal(str(effective_settings.get('sl_pct', 0.5)))
                    
                    # Выставляем ордера
                    logger.debug(f"Выставление многоуровневых ордеров для {ticker}...")
                    sl_order, tp_orders = await self.order_executor.place_multi_tp_orders(
                        position=position,
                        sl_price=sl_price,
                        tp_levels=tp_levels,
                        sl_pct=sl_pct
                    )
                    logger.info(f"Выставлены ордера: SL={'OK' if sl_order else 'FAIL'}, TP={len([o for o in tp_orders if o])} из {len(tp_orders)}")
                    
                    # Сохраняем уровни в БД
                    await self.position_manager.setup_multi_tp_levels(
                        position_id=position.id,
                        levels=multi_tp_levels
                    )
                else:
                    # Обычный SL/TP
                    logger.debug(f"Расчет обычных SL/TP для {ticker}...")
                    sl_price, tp_price = await self.risk_calculator.calculate_levels(
                        figi=figi,
                        ticker=ticker,
                        instrument_type=instrument_type,
                        avg_price=avg_price,
                        direction="LONG",
                        instrument_settings=instrument_settings,
                        account_id=account_id
                    )
                    logger.info(f"Рассчитаны уровни: SL={sl_price}, TP={tp_price}")
                    
                    # Выставляем ордера
                    logger.debug(f"Выставление ордеров SL/TP для {ticker}...")
                    sl_order, tp_order = await self.order_executor.place_sl_tp_orders(
                        position=position,
                        sl_price=sl_price,
                        tp_price=tp_price
                    )
                    logger.info(f"Выставлены ордера: SL={'OK' if sl_order else 'FAIL'}, TP={'OK' if tp_order else 'FAIL'}")
                
                logger.info(f"✅ Позиция {ticker} синхронизирована и защищена SL/TP")
                return
            
            # СЛУЧАЙ 2: Позиция закрыта
            if position and new_quantity == 0:
                logger.info(
                    f"Позиция {position.ticker} ({figi}) закрыта в брокере "
                    f"(количество {position.quantity} -> 0)"
                )
                await self.position_manager.close_position(position.id)
                return
            
            # СЛУЧАЙ 3: Изменение количества (усреднение или частичное закрытие)
            if position and position.quantity != new_quantity:
                # Проверяем, не является ли это расхождением между TradesStream и PositionsStream
                # Если разница слишком большая (>50%), это может быть из-за старых позиций
                # которые были до запуска бота и не должны учитываться
                quantity_diff = abs(new_quantity - position.quantity)
                quantity_ratio = quantity_diff / position.quantity if position.quantity > 0 else float('inf')
                
                # Если разница больше 50% и новое количество больше старого,
                # это может быть из-за старых позиций, которые не отслеживаются ботом
                if quantity_ratio > 0.5 and new_quantity > position.quantity:
                    logger.warning(
                        f"⚠️ Обнаружено большое расхождение в количестве для {ticker}: "
                        f"{position.quantity} -> {new_quantity} (разница {quantity_diff}, {quantity_ratio:.1%}). "
                        f"Возможно, это старые позиции, которые не отслеживаются ботом. "
                        f"Игнорируем обновление из PositionsStream."
                    )
                    
                    # Логируем событие
                    await self.db.log_event(
                        event_type="POSITION_DISCREPANCY",
                        account_id=account_id,
                        figi=figi,
                        ticker=ticker,
                        description=f"Обнаружено большое расхождение в количестве для {ticker}",
                        details={
                            "db_quantity": position.quantity,
                            "broker_quantity": new_quantity,
                            "difference": quantity_diff,
                            "ratio": float(quantity_ratio),
                            "ignored": True
                        }
                    )
                    return
                
                # ВАЖНО: Пропускаем обработку изменения количества для отслеживаемых позиций
                # Это будет обработано TradesStream, который получает точную информацию о каждой сделке
                # Предотвращает race condition между потоками и дублирование ордеров
                logger.info(
                    f"ℹ️ Изменение количества для {ticker} ({position.quantity} -> {new_quantity}) "
                    f"будет обработано TradesStream. Пропускаем обработку в PositionsStream."
                )
                
                # Логируем событие
                await self.db.log_event(
                    event_type="POSITION_UPDATE_SKIPPED",
                    account_id=account_id,
                    figi=figi,
                    ticker=ticker,
                    description=f"Пропущена обработка изменения количества для {ticker} в PositionsStream",
                    details={
                        "old_quantity": position.quantity,
                        "new_quantity": new_quantity,
                        "reason": "Предотвращение race condition с TradesStream"
                    }
                )
                return
        
        except Exception as e:
            logger.error(f"Ошибка при обработке позиции {figi}: {e}")
            
            # Логируем ошибку
            await self.db.log_event(
                event_type="ERROR",
                account_id=account_id,
                description=f"Ошибка при обработке позиции {figi}: {str(e)}",
                details={"error": str(e), "figi": figi}
            )
    
    async def _calculate_multi_tp_levels(
        self,
        position: Position,
        instrument_settings: Optional[Any] = None,
        account_id: Optional[str] = None
    ) -> tuple[Decimal, list[tuple[Decimal, float]]]:
        """
        Расчет уровней для многоуровневого тейк-профита
        
        Args:
            position: Позиция
            instrument_settings: Настройки инструмента
            account_id: ID аккаунта для получения настроек из БД
            
        Returns:
            tuple[Decimal, list[tuple[Decimal, float]]]: (стоп-лосс, список уровней TP)
        """
        # Получаем среднюю цену
        avg_price = Decimal(str(position.average_price))
        
        # Рассчитываем стоп-лосс
        sl_price, _ = await self.risk_calculator.calculate_levels(
            figi=position.figi,
            ticker=position.ticker,
            instrument_type=position.instrument_type,
            avg_price=avg_price,
            direction=position.direction,
            instrument_settings=instrument_settings,
            account_id=account_id
        )
        
        # Определяем уровни TP
        multi_tp_levels = []
        
        # Сначала проверяем настройки из БД (имеют высший приоритет)
        if account_id:
            effective_settings = await self.settings_manager.get_effective_settings(
                account_id=account_id,
                ticker=position.ticker
            )
            
            if effective_settings['multi_tp_enabled'] and effective_settings['multi_tp_levels']:
                multi_tp_levels = [(level['level_pct'], level['volume_pct']) for level in effective_settings['multi_tp_levels']]
                logger.debug(f"_calculate_multi_tp_levels: Используются уровни Multi-TP из БД для {position.ticker}: {len(multi_tp_levels)} уровней")
        
        # Если в БД нет уровней, проверяем настройки из YAML
        if not multi_tp_levels:
            if instrument_settings and instrument_settings.multi_tp and instrument_settings.multi_tp.enabled:
                multi_tp_levels = [(level.level_pct, level.volume_pct) for level in instrument_settings.multi_tp.levels]
                logger.debug(f"_calculate_multi_tp_levels: Используются уровни Multi-TP из настроек инструмента для {position.ticker}")
        
        logger.debug(f"_calculate_multi_tp_levels: Итоговые уровни Multi-TP для {position.ticker}: {multi_tp_levels}")
        
        # Рассчитываем цены уровней
        tp_levels = await self.risk_calculator.calculate_multi_tp_levels(
            figi=position.figi,
            ticker=position.ticker,
            instrument_type=position.instrument_type,
            avg_price=avg_price,
            direction=position.direction,
            levels=multi_tp_levels
        )
        
        return sl_price, tp_levels
