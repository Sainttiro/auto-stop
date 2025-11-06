"""
Обработка потока сделок
"""
import asyncio
from typing import Set, Optional, Any
from decimal import Decimal
from datetime import datetime

from tinkoff.invest import (
    OrderTrades,
    OrderDirection
)

from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.core.position_manager import PositionManager
from src.core.risk_calculator import RiskCalculator
from src.core.order_executor import OrderExecutor
from src.storage.database import Database
from src.storage.models import Position, Trade
from src.config.settings import InstrumentsConfig
from src.config.settings_manager import SettingsManager
from src.utils.converters import quotation_to_decimal
from src.utils.logger import get_logger

logger = get_logger("core.streams.trades_processor")


class TradesProcessor:
    """
    Обработка потока сделок
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
        stream_monitor = None  # Будет установлен позже
    ):
        """
        Инициализация обработчика сделок
        
        Args:
            api_client: Клиент API Tinkoff
            database: Объект для работы с базой данных
            position_manager: Менеджер позиций
            risk_calculator: Калькулятор рисков
            order_executor: Исполнитель ордеров
            instrument_cache: Кэш информации об инструментах
            instruments_config: Конфигурация инструментов
            settings_manager: Менеджер настроек
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
        self.stream_monitor = stream_monitor
        
        # Флаги для управления потоком
        self._running = False
        self._trades_stream_task = None
        
        # Блокировка для синхронизации
        self._lock = asyncio.Lock()
        
        # Множество обработанных сделок для избежания дублирования
        # Используем trade_id вместо order_id, так как один ордер может генерировать несколько сделок
        self._processed_trades: Set[str] = set()
    
    def set_stream_monitor(self, stream_monitor) -> None:
        """
        Установка монитора потоков
        
        Args:
            stream_monitor: Монитор потоков
        """
        self.stream_monitor = stream_monitor
    
    async def start(self, account_id: str) -> None:
        """
        Запуск обработчика потока сделок
        
        Args:
            account_id: ID счета
        """
        if self._running:
            logger.warning("Обработчик потока сделок уже запущен")
            return
        
        self._running = True
        self._trades_stream_task = asyncio.create_task(
            self._run_trades_stream(account_id)
        )
        
        # Регистрируем поток в мониторе
        if self.stream_monitor:
            self.stream_monitor.register_stream("trades")
            self.stream_monitor.register_restart_callback(
                "trades",
                self._restart_stream
            )
        
        logger.info(f"Обработчик потока сделок запущен для счета {account_id}")
    
    async def stop(self) -> None:
        """
        Остановка обработчика потока сделок
        """
        if not self._running:
            logger.warning("Обработчик потока сделок не запущен")
            return
        
        logger.info("Останавливаем поток сделок...")
        self._running = False
        
        if self._trades_stream_task and not self._trades_stream_task.done():
            self._trades_stream_task.cancel()
            try:
                await asyncio.wait_for(self._trades_stream_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        self._trades_stream_task = None
        logger.info("Обработчик потока сделок остановлен")
    
    async def _restart_stream(self, account_id: str) -> None:
        """
        Перезапуск потока сделок
        
        Args:
            account_id: ID счета
        """
        logger.info(f"Перезапуск потока сделок для счета {account_id}")
        
        # Отменяем текущую задачу
        if self._trades_stream_task and not self._trades_stream_task.done():
            self._trades_stream_task.cancel()
            try:
                await asyncio.wait_for(self._trades_stream_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        # Создаем новую задачу
        self._trades_stream_task = asyncio.create_task(
            self._run_trades_stream(account_id)
        )
        
        logger.info(f"Поток сделок перезапущен для счета {account_id}")
    
    async def _run_trades_stream(self, account_id: str) -> None:
        """
        Запуск потока исполнений сделок
        
        Args:
            account_id: ID счета
        """
        retry_count = 0
        max_retries = 100
        retry_delay = 1.0  # секунды
        max_delay = 300.0  # Максимальная задержка 5 минут
        
        while self._running:
            try:
                logger.info(f"Подключение к потоку исполнений сделок для счета {account_id}")
                
                async for response in self.api_client.services.orders_stream.trades_stream(
                    accounts=[account_id]
                ):
                    if not self._running:
                        break
                    
                    # Обновляем время последнего сообщения в мониторе
                    if self.stream_monitor:
                        self.stream_monitor.update_last_message_time("trades")
                    
                    # Обработка ping-сообщений (keep-alive)
                    if hasattr(response, 'ping') and response.ping:
                        logger.debug("Получен ping в потоке сделок")
                        continue
                    
                    # Обработка подтверждения подписки
                    if hasattr(response, 'subscription') and response.subscription:
                        logger.info(f"Подписка на поток сделок подтверждена: {response.subscription}")
                        continue
                    
                    # Обработка данных о сделке
                    if not hasattr(response, 'order_trades') or not response.order_trades:
                        logger.debug(f"Получено пустое сообщение в потоке сделок")
                        continue
                    
                    # Обрабатываем исполнение сделки
                    await self._handle_trade(response.order_trades, account_id)
                    
                    # Сбрасываем счетчик повторов при успешном получении данных
                    retry_count = 0
                
                # Если мы вышли из цикла, но _running все еще True, значит произошла ошибка
                if self._running:
                    raise Exception("Поток исполнений сделок прервался")
                    
            except Exception as e:
                if not self._running:
                    break
                
                retry_count += 1
                # Экспоненциальная задержка с ограничением максимума
                delay = min(retry_delay * (2 ** min(retry_count - 1, 8)), max_delay)
                
                logger.error(f"Ошибка в потоке исполнений сделок: {e}. Повторное подключение через {delay:.1f} сек... (попытка {retry_count}/{max_retries})")
                
                # Логируем событие
                await self.db.log_event(
                    event_type="STREAM_ERROR",
                    account_id=account_id,
                    description=f"Ошибка в потоке исполнений сделок: {str(e)}",
                    details={"error": str(e), "retry_count": retry_count, "max_retries": max_retries}
                )
                
                # Если превышено максимальное количество попыток, логируем критическую ошибку
                # но НЕ останавливаем систему - продолжаем попытки с максимальной задержкой
                if retry_count >= max_retries:
                    logger.critical(
                        f"Превышено максимальное количество попыток ({max_retries}) подключения к потоку исполнений сделок. "
                        f"Продолжаем попытки с интервалом {max_delay:.1f} сек..."
                    )
                    # Сбрасываем счетчик, чтобы продолжить попытки
                    retry_count = max_retries - 1
                
                await asyncio.sleep(delay)
    
    async def _handle_trade(self, order_trades: OrderTrades, account_id: str) -> None:
        """
        Обработка исполнения сделки
        
        Args:
            order_trades: Данные об исполнении сделки
            account_id: ID счета
        """
        order_id = order_trades.order_id
        
        # Получаем информацию о сделке из order_trades
        direction = "BUY" if order_trades.direction == OrderDirection.ORDER_DIRECTION_BUY else "SELL"
        figi = order_trades.figi
        
        # Обрабатываем все сделки в order_trades
        # При частичном исполнении один order_id может приходить несколько раз
        # с разными частями исполнения
        if not order_trades.trades:
            logger.warning(f"Ордер {order_id} не содержит сделок")
            return
        
        # Для каждой сделки создаем уникальный ID на основе времени исполнения
        # Это позволяет обрабатывать частичное исполнение одного ордера
        total_quantity = 0
        all_parts_processed = True  # Флаг для отслеживания, все ли части уже обработаны
        
        for trade in order_trades.trades:
            # Создаем уникальный ID для каждой части сделки
            trade_time = trade.date_time if hasattr(trade, 'date_time') else datetime.utcnow()
            trade_unique_id = f"{order_id}_{trade_time.timestamp()}"
            
            # Проверяем, не обрабатывали ли мы уже эту конкретную часть сделки
            async with self._lock:
                if trade_unique_id in self._processed_trades:
                    logger.debug(f"Часть сделки {trade_unique_id} уже обработана, пропускаем")
                    continue
                
                # Если хотя бы одна часть не обработана, устанавливаем флаг
                all_parts_processed = False
                
                # Добавляем в множество обработанных
                self._processed_trades.add(trade_unique_id)
            
            # Суммируем количество из всех частей
            total_quantity += trade.quantity
        
        # ИСПРАВЛЕНИЕ: Даже если все части уже обработаны, продолжаем выполнение
        # для проверки позиции и выставления ордеров
        if total_quantity == 0:
            if all_parts_processed:
                logger.debug(f"Все части ордера {order_id} уже обработаны, но продолжаем проверку позиции")
            else:
                logger.warning(
                    f"⚠️ Странная ситуация: total_quantity=0 для ордера {order_id}, "
                    f"но не все части помечены как обработанные. Продолжаем обработку."
                )
        
        try:
            logger.debug(f"Обработка сделки: order_id={order_id}, figi={figi}, direction={direction}")
            
            # Получаем тикер и тип инструмента
            instrument = await self.instrument_cache.get_instrument_by_figi(figi)
            if not instrument:
                logger.error(f"Не удалось получить информацию об инструменте {figi}")
                return
            
            ticker = instrument.ticker
            instrument_type = "stock" if instrument.instrument_type.lower().startswith("share") else "futures"
            
            logger.debug(f"Инструмент определен: ticker={ticker}, type={instrument_type}")
            
            # Рассчитываем среднюю цену и общее количество из всех частей
            total_amount = Decimal('0')
            for trade in order_trades.trades:
                trade_price = quotation_to_decimal(trade.price)
                trade_quantity = trade.quantity
                total_amount += trade_price * Decimal(trade_quantity)
            
            # Средневзвешенная цена
            price = total_amount / Decimal(total_quantity) if total_quantity > 0 else Decimal('0')
            quantity = total_quantity
            
            logger.info(
                f"Получено исполнение сделки: {ticker} ({figi}), "
                f"направление={direction}, цена={price}, количество={quantity}"
            )
            
            # Сохраняем сделку в БД
            # Используем уникальный ID из datetime, так как trade_id может отсутствовать
            trade_id = f"{order_id}_{datetime.utcnow().timestamp()}"
            trade = Trade(
                trade_id=trade_id,
                order_id=order_id,
                account_id=account_id,
                figi=figi,
                ticker=ticker,
                direction=direction,
                quantity=quantity,
                price=float(price),
                total_amount=float(price * Decimal(quantity)),
                trade_date=datetime.utcnow(),
            )
            await self.db.add(trade)
            logger.debug(f"Сделка сохранена в БД: trade_id={trade_id}")
            
            # Сохраняем старое количество для проверки изменений
            old_position = await self.position_manager.get_position(account_id, figi)
            old_quantity = old_position.quantity if old_position else 0
            
            # Обновляем позицию
            logger.debug(f"Обновление позиции для {ticker}...")
            try:
                position = await self.position_manager.update_position_on_trade(
                    account_id=account_id,
                    figi=figi,
                    ticker=ticker,
                    instrument_type=instrument_type,
                    quantity=quantity,
                    price=price,
                    direction=direction
                )
                
                # Если позиция была закрыта, выходим
                if not position:
                    logger.info(f"Позиция {ticker} была закрыта")
                    return
                
                logger.info(f"Позиция обновлена: {ticker}, количество={position.quantity}, средняя цена={position.average_price}")
            except Exception as e:
                logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА при обновлении позиции {ticker}: {e}", exc_info=True)
                # Логируем ошибку
                await self.db.log_event(
                    event_type="ERROR",
                    account_id=account_id,
                    description=f"Ошибка при обновлении позиции {ticker}: {str(e)}",
                    details={"error": str(e), "traceback": str(e.__traceback__)}
                )
                # Пробрасываем исключение дальше
                raise
            
            # Проверяем, изменилось ли количество в позиции (увеличение или уменьшение)
            is_position_changed = old_quantity > 0 and position.quantity != old_quantity
            
            if is_position_changed:
                change_type = "увеличена" if position.quantity > old_quantity else "уменьшена"
                is_position_decreased = position.quantity < old_quantity
                
                logger.warning(
                    f"⚠️ Позиция {ticker} {change_type}: "
                    f"{old_quantity} → {position.quantity} лотов. "
                    f"Отменяем старые ордера и выставляем новые на правильное количество."
                )
                
                try:
                    # Проверяем, активен ли Multi-TP и уменьшилась ли позиция
                    use_multi_tp = False
                    try:
                        effective_settings = await self.settings_manager.get_effective_settings(
                            account_id=account_id,
                            ticker=ticker
                        )
                        use_multi_tp = effective_settings.get('multi_tp_enabled', False)
                    except Exception as e:
                        logger.error(f"❌ Ошибка при получении настроек из БД для {ticker}: {e}")
                        use_multi_tp = False
                    
                    # Если позиция уменьшилась и активен Multi-TP, отменяем только SL и выставляем новый в безубыток
                    if is_position_decreased and use_multi_tp:
                        logger.info(
                            f"🔄 Позиция {ticker} уменьшена с Multi-TP активным. "
                            f"Отменяем только SL и выставляем новый в безубыток."
                        )
                        
                        # Отменяем только SL ордера
                        cancelled_count = await self.order_executor.cancel_stop_loss_orders(position.id)
                        logger.info(f"Отменено {cancelled_count} стоп-лосс ордеров для {ticker}")
                        
                        # Выставляем новый SL в безубыток (средняя цена + 0.10%)
                        avg_price = Decimal(str(position.average_price))
                        
                        # Расчет цены безубытка в зависимости от направления позиции
                        if position.direction == "LONG":
                            breakeven_price = avg_price * Decimal('1.001')  # +0.10%
                        else:
                            breakeven_price = avg_price * Decimal('0.999')  # -0.10%
                        
                        logger.info(
                            f"Выставление SL в безубыток для {ticker}: "
                            f"средняя цена={avg_price}, безубыток={breakeven_price}"
                        )
                        
                        # Выставляем SL в безубыток
                        await self.order_executor.place_stop_loss_order(
                            position=position,
                            stop_price=breakeven_price
                        )
                        
                        # Логируем событие
                        await self.db.log_event(
                            event_type="BREAKEVEN_SL_PLACED",
                            account_id=account_id,
                            figi=position.figi,
                            ticker=position.ticker,
                            description=f"Выставлен SL в безубыток для {ticker} после частичного закрытия",
                            details={
                                "avg_price": float(avg_price),
                                "breakeven_price": float(breakeven_price),
                                "quantity": position.quantity
                            }
                        )
                        
                        # Пропускаем дальнейшее выставление ордеров, так как TP ордера остались активными
                        logger.info(
                            f"✅ SL в безубыток выставлен для {ticker}. "
                            f"TP ордера остались активными. Пропускаем дальнейшее выставление ордеров."
                        )
                        return
                    else:
                        # Стандартная логика - отменяем ВСЕ ордера
                        cancelled_count = await self.order_executor.cancel_all_position_orders(position.id)
                        logger.info(f"Отменено {cancelled_count} старых ордеров для {ticker}")
                        
                        # Важно: после отмены старых ордеров нужно выставить новые
                        # Это будет сделано ниже в коде
                except Exception as e:
                    logger.error(f"❌ Ошибка при отмене старых ордеров для {ticker}: {e}", exc_info=True)
                    # Логируем ошибку, но продолжаем выполнение
                    await self.db.log_event(
                        event_type="ERROR",
                        account_id=account_id,
                        description=f"Ошибка при отмене старых ордеров для {ticker}: {str(e)}",
                        details={"error": str(e)}
                    )
                    # НЕ пробрасываем исключение дальше, чтобы продолжить выставление новых ордеров
            
            # Получаем настройки инструмента
            try:
                instrument_settings = self.instruments_config.instruments.get(ticker)
                logger.debug(f"Настройки инструмента для {ticker}: {instrument_settings is not None}")
            except Exception as e:
                logger.error(f"❌ Ошибка при получении настроек инструмента для {ticker}: {e}", exc_info=True)
                # Используем None как настройки инструмента
                instrument_settings = None
            
            # Проверяем, нужно ли использовать многоуровневый тейк-профит
            use_multi_tp = False
            multi_tp_levels = []
            
            try:
                # Сначала проверяем настройки из БД (имеют высший приоритет)
                effective_settings = await self.settings_manager.get_effective_settings(
                    account_id=account_id,
                    ticker=ticker
                )
                
                logger.debug(f"Получены эффективные настройки для {ticker}: {effective_settings}")
            except Exception as e:
                logger.error(f"❌ Ошибка при получении настроек из БД для {ticker}: {e}", exc_info=True)
                # Используем пустой словарь как настройки
                effective_settings = {
                    'multi_tp_enabled': False,
                    'multi_tp_levels': []
                }
            
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
                    avg_price=Decimal(str(position.average_price)),
                    direction=position.direction,
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
        
        except Exception as e:
            logger.error(f"Ошибка при обработке исполнения сделки: {e}", exc_info=True)
            
            # Логируем ошибку
            await self.db.log_event(
                event_type="ERROR",
                account_id=account_id,
                description=f"Ошибка при обработке исполнения сделки: {str(e)}",
                details={"error": str(e), "order_id": order_id, "traceback": str(e.__traceback__)}
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
