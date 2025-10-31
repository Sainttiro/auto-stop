from typing import Dict, List, Optional, Set, Callable, Awaitable, Any, Tuple
import asyncio
from decimal import Decimal
import json
from datetime import datetime, timedelta

from tinkoff.invest import (
    OrderTrades,
    OrderState,
    PositionsStreamResponse,
    PositionsResponse,
    OrderDirection,
    OrderExecutionReportStatus
)

from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.core.position_manager import PositionManager
from src.core.risk_calculator import RiskCalculator
from src.core.order_executor import OrderExecutor
from src.storage.database import Database
from src.storage.models import Position, Order, Trade
from src.config.settings import InstrumentsConfig, Config
from src.config.settings_manager import SettingsManager
from src.utils.converters import quotation_to_decimal, money_value_to_decimal
from src.utils.logger import get_logger

logger = get_logger("core.stream_handler")


class StreamHandler:
    """
    Обработчик потоков данных через gRPC
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
        Инициализация обработчика потоков
        
        Args:
            api_client: Клиент API Tinkoff
            database: Объект для работы с базой данных
            position_manager: Менеджер позиций
            risk_calculator: Калькулятор рисков
            order_executor: Исполнитель ордеров
            config: Основная конфигурация
            instruments_config: Конфигурация инструментов
            instrument_cache: Кэш информации об инструментах
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
        
        # Флаги для управления потоками
        self._running = False
        self._trades_stream_task = None
        self._positions_stream_task = None
        self._monitor_task = None
        
        # Блокировка для синхронизации
        self._lock = asyncio.Lock()
        
        # Время последнего сообщения для мониторинга здоровья потоков
        self._last_trades_message = datetime.now()
        self._last_positions_message = datetime.now()
        
        # Настройки мониторинга
        self._monitor_interval = 60  # секунды между проверками
        self._stream_timeout = 300   # секунды без сообщений до перезапуска (5 минут)
        
        # Множество обработанных сделок для избежания дублирования
        # Используем trade_id вместо order_id, так как один ордер может генерировать несколько сделок
        self._processed_trades: Set[str] = set()
        
        # Словарь для отслеживания позиций, ожидающих активации
        # Формат: {figi: {'position_id': id, 'sl_activation_price': price, 'tp_activation_price': price, 'sl_activated': bool, 'tp_activated': bool}}
        self._pending_activations: Dict[str, Dict[str, Any]] = {}
    
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
        
        # Запускаем потоки
        self._trades_stream_task = asyncio.create_task(
            self._run_trades_stream(account_id)
        )
        self._positions_stream_task = asyncio.create_task(
            self._run_positions_stream(account_id)
        )
        
        # Запускаем мониторинг потоков
        self._monitor_task = asyncio.create_task(
            self._monitor_streams(account_id)
        )
        
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
        
        # Отменяем задачи с таймаутом
        tasks_to_cancel = []
        
        if self._trades_stream_task and not self._trades_stream_task.done():
            tasks_to_cancel.append(("trades", self._trades_stream_task))
        
        if self._positions_stream_task and not self._positions_stream_task.done():
            tasks_to_cancel.append(("positions", self._positions_stream_task))
            
        if self._monitor_task and not self._monitor_task.done():
            tasks_to_cancel.append(("monitor", self._monitor_task))
        
        for task_name, task in tasks_to_cancel:
            logger.debug(f"Отменяем задачу {task_name}...")
            task.cancel()
            try:
                # Ждем завершения задачи с таймаутом 2 секунды
                await asyncio.wait_for(task, timeout=2.0)
            except asyncio.CancelledError:
                logger.debug(f"Задача {task_name} отменена")
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут при отмене задачи {task_name}")
            except Exception as e:
                logger.error(f"Ошибка при отмене задачи {task_name}: {e}")
        
        self._trades_stream_task = None
        self._positions_stream_task = None
        self._monitor_task = None
        
        logger.info("Обработчик потоков остановлен")
    
    async def _run_trades_stream(self, account_id: str):
        """
        Запуск потока исполнений сделок
        
        Args:
            account_id: ID счета
        """
        retry_count = 0
        max_retries = 100  # Увеличено с 10 до 100
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
                    
                    # Обрабатываем исполнение сделки
                    await self._handle_trade(response, account_id)
                    
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
    
    async def _run_positions_stream(self, account_id: str):
        """
        Запуск потока изменений позиций
        
        Args:
            account_id: ID счета
        """
        retry_count = 0
        max_retries = 100  # Увеличено с 10 до 100
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
    
    async def _handle_trade(self, trade_response, account_id: str):
        """
        Обработка исполнения сделки
        
        Args:
            trade_response: Данные об исполнении сделки (TradesStreamResponse)
            account_id: ID счета
        """
        # Обработка ping-сообщений (keep-alive)
        if hasattr(trade_response, 'ping') and trade_response.ping:
            logger.debug("Получен ping в потоке сделок")
            # Обновляем время последнего сообщения
            self._last_trades_message = datetime.now()
            return
        
        # Обработка подтверждения подписки
        if hasattr(trade_response, 'subscription') and trade_response.subscription:
            logger.info(f"Подписка на поток сделок подтверждена: {trade_response.subscription}")
            # Обновляем время последнего сообщения
            self._last_trades_message = datetime.now()
            return
        
        # Обработка данных о сделке
        if not hasattr(trade_response, 'order_trades') or not trade_response.order_trades:
            logger.debug(f"Получено пустое сообщение в потоке сделок")
            # Обновляем время последнего сообщения даже для пустых сообщений
            self._last_trades_message = datetime.now()
            return
        
        # Извлекаем данные о сделке из order_trades
        order_trades = trade_response.order_trades
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
        for trade in order_trades.trades:
            # Создаем уникальный ID для каждой части сделки
            trade_time = trade.date_time if hasattr(trade, 'date_time') else datetime.utcnow()
            trade_unique_id = f"{order_id}_{trade_time.timestamp()}"
            
            # Проверяем, не обрабатывали ли мы уже эту конкретную часть сделки
            async with self._lock:
                if trade_unique_id in self._processed_trades:
                    logger.debug(f"Часть сделки {trade_unique_id} уже обработана, пропускаем")
                    continue
                
                # Добавляем в множество обработанных
                self._processed_trades.add(trade_unique_id)
            
            # Суммируем количество из всех частей
            total_quantity += trade.quantity
        
        # Если все части уже были обработаны, выходим
        if total_quantity == 0:
            logger.debug(f"Все части ордера {order_id} уже обработаны")
            return
        
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
            
            # Проверяем, изменилось ли количество в позиции (увеличение или уменьшение)
            is_position_changed = old_quantity > 0 and position.quantity != old_quantity
            
            if is_position_changed:
                change_type = "увеличена" if position.quantity > old_quantity else "уменьшена"
                logger.warning(
                    f"⚠️ Позиция {ticker} {change_type}: "
                    f"{old_quantity} → {position.quantity} лотов. "
                    f"Отменяем старые ордера и выставляем новые на правильное количество."
                )
                
                # Отменяем ВСЕ старые ордера для этой позиции
                cancelled_count = await self.order_executor.cancel_all_position_orders(position.id)
                logger.info(f"Отменено {cancelled_count} старых ордеров для {ticker}")
            
            # Получаем настройки инструмента
            instrument_settings = self.instruments_config.instruments.get(ticker)
            logger.debug(f"Настройки инструмента для {ticker}: {instrument_settings is not None}")
            
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
            elif self.config.multi_take_profit.enabled:
                use_multi_tp = True
                multi_tp_levels = [(level.level_pct, level.volume_pct) for level in self.config.multi_take_profit.levels]
                logger.debug(f"Используются уровни Multi-TP из глобальных настроек для {ticker}")
            
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
            
            # При ошибке НЕ удаляем из обработанных, так как у нас может быть
            # несколько trade_unique_id для одного ордера (частичное исполнение)
            # Повторная обработка произойдет при следующем сообщении от API
            pass
    
    async def _handle_position_change(self, position_response: PositionsStreamResponse, account_id: str):
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
                # Обновляем время последнего сообщения
                self._last_positions_message = datetime.now()
                return
                
            # Обработка подтверждения подписки
            if hasattr(position_response, 'subscriptions') and position_response.subscriptions:
                logger.info(f"Подписка на поток позиций подтверждена для счета {account_id}")
                # Обновляем время последнего сообщения
                self._last_positions_message = datetime.now()
                return
                
            # Обработка начальных позиций при подключении
            if hasattr(position_response, 'initial_positions') and position_response.initial_positions:
                logger.info(f"Получены начальные позиции для счета {account_id}")
                # Обновляем время последнего сообщения
                self._last_positions_message = datetime.now()
                # Можно обработать начальные позиции, если необходимо
                return
                
            # Обработка изменения позиции
            if not hasattr(position_response, "position") or position_response.position is None:
                logger.debug(f"Получено пустое сообщение в потоке позиций")
                # Обновляем время последнего сообщения даже для пустых сообщений
                self._last_positions_message = datetime.now()
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
    
    async def _check_activation_conditions(
        self,
        figi: str,
        current_price: Decimal,
        position: Position,
        settings: Dict[str, Any]
    ) -> Tuple[bool, bool]:
        """
        Проверка условий активации SL/TP
        
        Args:
            figi: FIGI инструмента
            current_price: Текущая цена
            position: Позиция
            settings: Настройки инструмента
            
        Returns:
            Tuple[bool, bool]: (sl_activated, tp_activated)
        """
        sl_activation_pct = settings.get('sl_activation_pct')
        tp_activation_pct = settings.get('tp_activation_pct')
        
        # Если нет настроек активации, считаем что активировано сразу
        if sl_activation_pct is None and tp_activation_pct is None:
            return True, True
        
        # Получаем цены активации
        sl_activation_price, tp_activation_price = await self.risk_calculator.calculate_activation_prices(
            figi=figi,
            ticker=position.ticker,
            instrument_type=position.instrument_type,
            avg_price=Decimal(str(position.average_price)),
            direction=position.direction,
            sl_activation_pct=sl_activation_pct,
            tp_activation_pct=tp_activation_pct
        )
        
        # Проверяем активацию SL
        sl_activated = True  # По умолчанию активировано, если нет настроек активации
        if sl_activation_price is not None:
            if position.direction == "LONG":
                # Для LONG: активация SL когда цена падает ниже уровня активации
                sl_activated = current_price <= sl_activation_price
            else:  # SHORT
                # Для SHORT: активация SL когда цена растет выше уровня активации
                sl_activated = current_price >= sl_activation_price
        
        # Проверяем активацию TP
        tp_activated = True  # По умолчанию активировано, если нет настроек активации
        if tp_activation_price is not None:
            if position.direction == "LONG":
                # Для LONG: активация TP когда цена растет выше уровня активации
                tp_activated = current_price >= tp_activation_price
            else:  # SHORT
                # Для SHORT: активация TP когда цена падает ниже уровня активации
                tp_activated = current_price <= tp_activation_price
        
        # Логируем активацию
        if sl_activated and sl_activation_price is not None:
            logger.info(
                f"🔔 SL для {position.ticker} активирован! "
                f"Цена активации: {sl_activation_price}, текущая цена: {current_price}"
            )
            
            # Логируем событие
            await self.db.log_event(
                event_type="SL_ACTIVATED",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"SL для {position.ticker} активирован",
                details={
                    "activation_price": float(sl_activation_price),
                    "current_price": float(current_price),
                    "position_id": position.id
                }
            )
        
        if tp_activated and tp_activation_price is not None:
            logger.info(
                f"🔔 TP для {position.ticker} активирован! "
                f"Цена активации: {tp_activation_price}, текущая цена: {current_price}"
            )
            
            # Логируем событие
            await self.db.log_event(
                event_type="TP_ACTIVATED",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"TP для {position.ticker} активирован",
                details={
                    "activation_price": float(tp_activation_price),
                    "current_price": float(current_price),
                    "position_id": position.id
                }
            )
        
        return sl_activated, tp_activated
    
    async def _monitor_streams(self, account_id: str):
        """
        Мониторинг здоровья потоков данных
        
        Проверяет, что потоки получают сообщения регулярно.
        Если поток не получает сообщений в течение self._stream_timeout секунд,
        он считается "зависшим" и перезапускается.
        
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
                
                # Проверяем поток сделок
                trades_idle_time = (now - self._last_trades_message).total_seconds()
                if trades_idle_time > self._stream_timeout:
                    logger.critical(
                        f"⚠️ КРИТИЧЕСКАЯ ОШИБКА: Поток сделок не отвечает {trades_idle_time:.1f} секунд "
                        f"(> {self._stream_timeout} сек). Перезапуск..."
                    )
                    
                    # Логируем событие в БД
                    await self.db.log_event(
                        event_type="STREAM_TIMEOUT",
                        account_id=account_id,
                        description=f"Поток сделок не отвечает {trades_idle_time:.1f} секунд. Перезапуск...",
                        details={
                            "stream_type": "trades",
                            "idle_time": trades_idle_time,
                            "timeout": self._stream_timeout
                        }
                    )
                    
                    # Перезапускаем поток сделок
                    await self._restart_stream("trades", account_id)
                
                # Проверяем поток позиций
                positions_idle_time = (now - self._last_positions_message).total_seconds()
                if positions_idle_time > self._stream_timeout:
                    logger.critical(
                        f"⚠️ КРИТИЧЕСКАЯ ОШИБКА: Поток позиций не отвечает {positions_idle_time:.1f} секунд "
                        f"(> {self._stream_timeout} сек). Перезапуск..."
                    )
                    
                    # Логируем событие в БД
                    await self.db.log_event(
                        event_type="STREAM_TIMEOUT",
                        account_id=account_id,
                        description=f"Поток позиций не отвечает {positions_idle_time:.1f} секунд. Перезапуск...",
                        details={
                            "stream_type": "positions",
                            "idle_time": positions_idle_time,
                            "timeout": self._stream_timeout
                        }
                    )
                    
                    # Перезапускаем поток позиций
                    await self._restart_stream("positions", account_id)
                
            except asyncio.CancelledError:
                logger.info("Задача мониторинга потоков отменена")
                break
            except Exception as e:
                logger.error(f"Ошибка в задаче мониторинга потоков: {e}")
    
    async def _restart_stream(self, stream_type: str, account_id: str):
        """
        Безопасный перезапуск потока данных
        
        Args:
            stream_type: Тип потока ("trades" или "positions")
            account_id: ID счета
        """
        try:
            if stream_type == "trades":
                # Отменяем текущую задачу потока сделок
                if self._trades_stream_task and not self._trades_stream_task.done():
                    logger.info("Отменяем текущую задачу потока сделок...")
                    self._trades_stream_task.cancel()
                    try:
                        await asyncio.wait_for(asyncio.shield(self._trades_stream_task), timeout=2.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                
                # Создаем новую задачу
                logger.info("Создаем новую задачу потока сделок...")
                self._trades_stream_task = asyncio.create_task(self._run_trades_stream(account_id))
                
                # Сбрасываем время последнего сообщения
                self._last_trades_message = datetime.now()
                
                # Отправляем уведомление
                await self._send_stream_restart_notification(
                    stream_type="trades",
                    account_id=account_id
                )
                
            elif stream_type == "positions":
                # Отменяем текущую задачу потока позиций
                if self._positions_stream_task and not self._positions_stream_task.done():
                    logger.info("Отменяем текущую задачу потока позиций...")
                    self._positions_stream_task.cancel()
                    try:
                        await asyncio.wait_for(asyncio.shield(self._positions_stream_task), timeout=2.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                
                # Создаем новую задачу
                logger.info("Создаем новую задачу потока позиций...")
                self._positions_stream_task = asyncio.create_task(self._run_positions_stream(account_id))
                
                # Сбрасываем время последнего сообщения
                self._last_positions_message = datetime.now()
                
                # Отправляем уведомление
                await self._send_stream_restart_notification(
                    stream_type="positions",
                    account_id=account_id
                )
            
            logger.info(f"Поток {stream_type} успешно перезапущен")
            
        except Exception as e:
            logger.error(f"Ошибка при перезапуске потока {stream_type}: {e}")
    
    async def _send_stream_restart_notification(self, stream_type: str, account_id: str):
        """
        Отправка уведомления о перезапуске потока
        
        Args:
            stream_type: Тип потока ("trades" или "positions")
            account_id: ID счета
        """
        try:
            # Проверяем наличие Telegram уведомлений
            from src.notifications.telegram import TelegramNotifier
            
            # Получаем экземпляр TelegramNotifier из main.py
            # Это не идеальное решение, но работает для отправки уведомлений
            # В идеале нужно передавать notifier в конструкторе
            import sys
            main_module = sys.modules.get('__main__')
            if hasattr(main_module, 'system') and hasattr(main_module.system, 'telegram_notifier'):
                notifier = main_module.system.telegram_notifier
                if notifier:
                    message = (
                        f"⚠️ <b>ВНИМАНИЕ! Перезапуск потока {stream_type}</b>\n\n"
                        f"Поток {stream_type} не отвечал более {self._stream_timeout} секунд "
                        f"и был автоматически перезапущен.\n\n"
                        f"<i>Account ID:</i> <code>{account_id}</code>\n"
                        f"<i>Время:</i> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    await notifier.send_message(message)
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о перезапуске потока: {e}")
    
    async def _process_security_position(self, security, account_id: str):
        """
        Обработка изменения позиции по конкретному инструменту
        
        ОБНОВЛЕНО: Теперь обрабатывает ВСЕ изменения позиций:
        - Создание новых позиций (открытых вручную)
        - Изменение количества
        - Закрытие позиций
        - Отслеживание цены для активации SL/TP
        
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
                if figi in self._pending_activations and self._pending_activations[figi]['position_id'] == position.id:
                    # Получаем настройки активации
                    settings = await self.settings_manager.get_effective_settings(
                        account_id=account_id,
                        ticker=position.ticker
                    )
                    
                    # Проверяем условия активации
                    sl_activated, tp_activated = await self._check_activation_conditions(
                        figi=figi,
                        current_price=current_price,
                        position=position,
                        settings=settings
                    )
                    
                    # Если SL активирован и раньше не был активирован
                    if sl_activated and not self._pending_activations[figi]['sl_activated']:
                        self._pending_activations[figi]['sl_activated'] = True
                        
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
                    if tp_activated and not self._pending_activations[figi]['tp_activated']:
                        self._pending_activations[figi]['tp_activated'] = True
                        
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
                        del self._pending_activations[figi]
            
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
                elif self.config.multi_take_profit.enabled:
                    use_multi_tp = True
                    multi_tp_levels = [(level.level_pct, level.volume_pct) for level in self.config.multi_take_profit.levels]
                    logger.debug(f"Используются уровни Multi-TP из глобальных настроек для {ticker}")
                
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
                logger.info(
                    f"🔄 Изменение количества в PositionsStream: {ticker}, "
                    f"{position.quantity} -> {new_quantity}"
                )
                
                # Обновляем позицию
                if avg_price > 0:
                    await self.position_manager.update_position(
                        position_id=position.id,
                        new_quantity=new_quantity,
                        new_price=avg_price
                    )
                else:
                    await self.position_manager.update_position(
                        position_id=position.id,
                        new_quantity=new_quantity
                    )
                
                # Отменяем старые ордера
                cancelled = await self.order_executor.cancel_all_position_orders(position.id)
                logger.info(f"Отменено {cancelled} старых ордеров для {ticker}")
                
                # Получаем обновленную позицию
                updated_position = await self.position_manager.get_position(account_id, figi)
                
                # Получаем настройки инструмента
                instrument_settings = self.instruments_config.instruments.get(ticker)
                
                # Рассчитываем новые SL/TP
                sl_price, tp_price = await self.risk_calculator.calculate_levels(
                    figi=figi,
                    ticker=ticker,
                    instrument_type=instrument_type,
                    avg_price=Decimal(str(updated_position.average_price)),
                    direction=updated_position.direction,
                    instrument_settings=instrument_settings,
                    account_id=account_id
                )
                
                # Выставляем новые ордера
                await self.order_executor.place_sl_tp_orders(
                    position=updated_position,
                    sl_price=sl_price,
                    tp_price=tp_price
                )
                
                logger.info(f"✅ Позиция {ticker} обновлена и защищена новыми SL/TP")
        
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
    ) -> Tuple[Decimal, List[Tuple[Decimal, float]]]:
        """
        Расчет уровней для многоуровневого тейк-профита
        
        Args:
            position: Позиция
            instrument_settings: Настройки инструмента
            account_id: ID аккаунта для получения настроек из БД
            
        Returns:
            Tuple[Decimal, List[Tuple[Decimal, float]]]: (стоп-лосс, список уровней TP)
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
            elif self.config.multi_take_profit.enabled:
                multi_tp_levels = [(level.level_pct, level.volume_pct) for level in self.config.multi_take_profit.levels]
                logger.debug(f"_calculate_multi_tp_levels: Используются уровни Multi-TP из глобальных настроек для {position.ticker}")
        
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
