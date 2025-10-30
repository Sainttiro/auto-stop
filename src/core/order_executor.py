from typing import Optional, Dict, List, Tuple, Any
from decimal import Decimal
import asyncio
import uuid

from tinkoff.invest import (
    PostOrderRequest,
    OrderDirection,
    OrderType,
    StopOrderDirection,
    StopOrderExpirationType,
    StopOrderType,
    PostStopOrderRequest,
    Quotation
)

from src.config.settings_manager import SettingsManager

from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.storage.database import Database
from src.storage.models import Order, Position
from src.utils.converters import decimal_to_quotation, round_to_step
from src.utils.logger import get_logger

logger = get_logger("core.order_executor")


class OrderExecutor:
    """
    Выставление и управление ордерами
    """
    
    def __init__(
        self, 
        api_client: TinkoffAPIClient, 
        database: Database, 
        instrument_cache: InstrumentInfoCache,
        settings_manager: Optional[SettingsManager] = None,
        stream_handler = None  # Будет установлен позже для избежания циклических зависимостей
    ):
        """
        Инициализация исполнителя ордеров
        
        Args:
            api_client: Клиент API Tinkoff
            database: Объект для работы с базой данных
            instrument_cache: Кэш информации об инструментах
            settings_manager: Менеджер настроек
            stream_handler: Обработчик потоков (устанавливается позже)
        """
        self.api_client = api_client
        self.db = database
        self.instrument_cache = instrument_cache
        self.settings_manager = settings_manager
        self.stream_handler = stream_handler
        self._lock = asyncio.Lock()
    
    def set_stream_handler(self, stream_handler):
        """
        Установка обработчика потоков
        
        Args:
            stream_handler: Обработчик потоков
        """
        self.stream_handler = stream_handler
    
    async def place_stop_loss_order(
        self,
        position: Position,
        stop_price: Decimal,
        sl_pct: Optional[Decimal] = None
    ) -> Optional[Order]:
        """
        Выставление стоп-лосс ордера
        
        Args:
            position: Позиция
            stop_price: Цена стоп-лосса (цена активации)
            sl_pct: Размер стопа в процентах (для расчета цены исполнения)
            
        Returns:
            Optional[Order]: Созданный ордер или None в случае ошибки
        """
        # Определяем направление ордера (противоположное позиции)
        direction = StopOrderDirection.STOP_ORDER_DIRECTION_SELL \
            if position.direction == "LONG" else StopOrderDirection.STOP_ORDER_DIRECTION_BUY
        
        # Используем STOP_LIMIT для всех инструментов (акции и фьючерсы)
        # STOP_LIMIT гарантирует исполнение по указанной цене или лучше
        stop_order_type = StopOrderType.STOP_ORDER_TYPE_STOP_LIMIT
        
        try:
            # КРИТИЧНО: API принимает quantity в ЛОТАХ, а не в акциях!
            # Получаем размер лота для инструмента
            lot_size = await self.instrument_cache.get_lot_size(position.figi)
            
            # Конвертируем количество из акций в лоты
            quantity_in_lots = position.quantity // lot_size
            
            # Проверка: количество должно быть > 0
            if quantity_in_lots <= 0:
                logger.error(
                    f"Ошибка: количество в лотах = {quantity_in_lots} для {position.ticker}. "
                    f"Позиция: {position.quantity} акций, размер лота: {lot_size}"
                )
                return None
            
            logger.info(
                f"Конвертация количества для {position.ticker}: "
                f"{position.quantity} акций → {quantity_in_lots} лотов (размер лота: {lot_size})"
            )
            
            # Рассчитываем цену исполнения с пропорциональным смещением от цены активации
            # Смещение = 10% от размера стопа, но не менее 1 шага цены
            execution_price = stop_price
            if sl_pct is not None and sl_pct > Decimal('0'):
                # Получаем минимальный шаг цены
                min_price_increment, _ = await self.instrument_cache.get_price_step(position.figi)
                
                # Рассчитываем смещение (10% от размера стопа)
                execution_offset_pct = sl_pct * Decimal('0.1')
                
                # Минимальное смещение - 1 шаг цены
                min_offset_pct = min_price_increment / stop_price * Decimal('100')
                execution_offset_pct = max(execution_offset_pct, min_offset_pct)
                
                # Рассчитываем цену исполнения в зависимости от направления
                if direction == StopOrderDirection.STOP_ORDER_DIRECTION_SELL:  # LONG позиция
                    execution_price = stop_price * (Decimal('1') - execution_offset_pct / Decimal('100'))
                else:  # SHORT позиция
                    execution_price = stop_price * (Decimal('1') + execution_offset_pct / Decimal('100'))
                
                # Округляем до минимального шага цены
                execution_price = round_to_step(execution_price, min_price_increment)
                
                logger.info(
                    f"Рассчитана цена исполнения для {position.ticker}: "
                    f"stop_price={stop_price}, execution_price={execution_price} "
                    f"(смещение {execution_offset_pct:.3f}%)"
                )
            
            # Выставляем ордер через API (передаем параметры напрямую)
            response = await self.api_client.services.stop_orders.post_stop_order(
                figi=position.figi,
                quantity=quantity_in_lots,  # ВАЖНО: передаем в лотах!
                price=decimal_to_quotation(execution_price),  # Цена исполнения
                stop_price=decimal_to_quotation(stop_price),  # Цена активации
                direction=direction,
                account_id=position.account_id,
                stop_order_type=stop_order_type,
                expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL
            )
            
            # Создаем запись в БД
            order = Order(
                order_id=response.stop_order_id,
                position_id=position.id,
                account_id=position.account_id,
                figi=position.figi,
                order_type="STOP",
                direction="SELL" if direction == StopOrderDirection.STOP_ORDER_DIRECTION_SELL else "BUY",
                quantity=position.quantity,
                price=float(execution_price),  # Цена исполнения
                stop_price=float(stop_price),  # Цена активации
                status="NEW",
                order_purpose="STOP_LOSS"
            )
            
            await self.db.add(order)
            
            logger.info(
                f"Выставлен стоп-лосс (STOP_LIMIT) для {position.ticker} ({position.instrument_type}): "
                f"цена активации={stop_price}, цена исполнения={execution_price}, "
                f"количество={position.quantity}, ID={response.stop_order_id}"
            )
            
            # Логируем событие
            await self.db.log_event(
                event_type="STOP_LOSS_PLACED",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"Выставлен стоп-лосс для {position.ticker}: цена активации={stop_price}, цена исполнения={execution_price}",
                details={
                    "order_id": response.stop_order_id,
                    "price": float(stop_price),
                    "quantity": position.quantity
                }
            )
            
            return order
        except Exception as e:
            logger.error(f"Ошибка при выставлении стоп-лосса для {position.ticker}: {e}")
            
            # Логируем ошибку
            await self.db.log_event(
                event_type="ERROR",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"Ошибка при выставлении стоп-лосса: {str(e)}",
                details={"error": str(e)}
            )
            
            return None
    
    async def place_take_profit_order(
        self,
        position: Position,
        take_price: Decimal
    ) -> Optional[Order]:
        """
        Выставление тейк-профит ордера
        
        Args:
            position: Позиция
            take_price: Цена тейк-профита
            
        Returns:
            Optional[Order]: Созданный ордер или None в случае ошибки
        """
        # Определяем направление ордера (противоположное позиции)
        direction = StopOrderDirection.STOP_ORDER_DIRECTION_SELL \
            if position.direction == "LONG" else StopOrderDirection.STOP_ORDER_DIRECTION_BUY
        
        try:
            # КРИТИЧНО: API принимает quantity в ЛОТАХ, а не в акциях!
            # Получаем размер лота для инструмента
            lot_size = await self.instrument_cache.get_lot_size(position.figi)
            
            # Конвертируем количество из акций в лоты
            quantity_in_lots = position.quantity // lot_size
            
            # Проверка: количество должно быть > 0
            if quantity_in_lots <= 0:
                logger.error(
                    f"Ошибка: количество в лотах = {quantity_in_lots} для {position.ticker}. "
                    f"Позиция: {position.quantity} акций, размер лота: {lot_size}"
                )
                return None
            
            logger.info(
                f"Конвертация количества для {position.ticker}: "
                f"{position.quantity} акций → {quantity_in_lots} лотов (размер лота: {lot_size})"
            )
            
            # Выставляем ордер через API (передаем параметры напрямую)
            response = await self.api_client.services.stop_orders.post_stop_order(
                figi=position.figi,
                quantity=quantity_in_lots,  # ВАЖНО: передаем в лотах!
                price=decimal_to_quotation(take_price),
                stop_price=decimal_to_quotation(take_price),
                direction=direction,
                account_id=position.account_id,
                stop_order_type=StopOrderType.STOP_ORDER_TYPE_TAKE_PROFIT,
                expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL
            )
            
            # Создаем запись в БД
            order = Order(
                order_id=response.stop_order_id,
                position_id=position.id,
                account_id=position.account_id,
                figi=position.figi,
                order_type="STOP",
                direction="SELL" if direction == StopOrderDirection.STOP_ORDER_DIRECTION_SELL else "BUY",
                quantity=position.quantity,
                price=float(take_price),
                stop_price=float(take_price),
                status="NEW",
                order_purpose="TAKE_PROFIT"
            )
            
            await self.db.add(order)
            
            logger.info(
                f"Выставлен тейк-профит для {position.ticker}: "
                f"цена={take_price}, количество={position.quantity}, "
                f"ID={response.stop_order_id}"
            )
            
            # Логируем событие
            await self.db.log_event(
                event_type="TAKE_PROFIT_PLACED",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"Выставлен тейк-профит для {position.ticker}: цена={take_price}",
                details={
                    "order_id": response.stop_order_id,
                    "price": float(take_price),
                    "quantity": position.quantity
                }
            )
            
            return order
        except Exception as e:
            logger.error(f"Ошибка при выставлении тейк-профита для {position.ticker}: {e}")
            
            # Логируем ошибку
            await self.db.log_event(
                event_type="ERROR",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"Ошибка при выставлении тейк-профита: {str(e)}",
                details={"error": str(e)}
            )
            
            return None
    
    async def place_multi_tp_order(
        self,
        position: Position,
        price: Decimal,
        quantity: int,
        level_number: int
    ) -> Optional[Order]:
        """
        Выставление ордера для многоуровневого тейк-профита
        
        Args:
            position: Позиция
            price: Цена уровня
            quantity: Количество для закрытия на этом уровне (в акциях)
            level_number: Номер уровня
            
        Returns:
            Optional[Order]: Созданный ордер или None в случае ошибки
        """
        # Определяем направление ордера (противоположное позиции)
        direction = StopOrderDirection.STOP_ORDER_DIRECTION_SELL \
            if position.direction == "LONG" else StopOrderDirection.STOP_ORDER_DIRECTION_BUY
        
        try:
            # КРИТИЧНО: API принимает quantity в ЛОТАХ, а не в акциях!
            # Получаем размер лота для инструмента
            lot_size = await self.instrument_cache.get_lot_size(position.figi)
            
            # Конвертируем количество из акций в лоты
            quantity_in_lots = quantity // lot_size
            
            # Проверка: количество должно быть > 0
            if quantity_in_lots <= 0:
                logger.error(
                    f"Ошибка: количество в лотах = {quantity_in_lots} для {position.ticker} (уровень {level_number}). "
                    f"Количество: {quantity} акций, размер лота: {lot_size}"
                )
                return None
            
            logger.info(
                f"Конвертация количества для {position.ticker} (уровень {level_number}): "
                f"{quantity} акций → {quantity_in_lots} лотов (размер лота: {lot_size})"
            )
            
            # Выставляем ордер через API (передаем параметры напрямую)
            response = await self.api_client.services.stop_orders.post_stop_order(
                figi=position.figi,
                quantity=quantity_in_lots,  # ВАЖНО: передаем в лотах!
                price=decimal_to_quotation(price),
                stop_price=decimal_to_quotation(price),
                direction=direction,
                account_id=position.account_id,
                stop_order_type=StopOrderType.STOP_ORDER_TYPE_TAKE_PROFIT,
                expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_CANCEL
            )
            
            # Создаем запись в БД
            order = Order(
                order_id=response.stop_order_id,
                position_id=position.id,
                account_id=position.account_id,
                figi=position.figi,
                order_type="STOP",
                direction="SELL" if direction == StopOrderDirection.STOP_ORDER_DIRECTION_SELL else "BUY",
                quantity=quantity,
                price=float(price),
                stop_price=float(price),
                status="NEW",
                order_purpose=f"MULTI_TP_{level_number}"
            )
            
            await self.db.add(order)
            
            logger.info(
                f"Выставлен многоуровневый TP (уровень {level_number}) для {position.ticker}: "
                f"цена={price}, количество={quantity}, "
                f"ID={response.stop_order_id}"
            )
            
            # Логируем событие
            await self.db.log_event(
                event_type="MULTI_TP_PLACED",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"Выставлен многоуровневый TP (уровень {level_number}) для {position.ticker}: цена={price}",
                details={
                    "order_id": response.stop_order_id,
                    "price": float(price),
                    "quantity": quantity,
                    "level": level_number
                }
            )
            
            return order
        except Exception as e:
            logger.error(f"Ошибка при выставлении многоуровневого TP для {position.ticker}: {e}")
            
            # Логируем ошибку
            await self.db.log_event(
                event_type="ERROR",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"Ошибка при выставлении многоуровневого TP (уровень {level_number}): {str(e)}",
                details={"error": str(e), "level": level_number}
            )
            
            return None
    
    async def cancel_order(self, order: Order) -> bool:
        """
        Отмена ордера
        
        Args:
            order: Ордер для отмены
            
        Returns:
            bool: True, если ордер успешно отменен
        """
        try:
            # Отменяем ордер через API
            await self.api_client.services.stop_orders.cancel_stop_order(
                account_id=order.account_id,
                stop_order_id=order.order_id
            )
            
            # Обновляем статус в БД
            await self.db.update(Order, order.id, {"status": "CANCELLED"})
            
            logger.info(f"Отменен ордер {order.order_id} ({order.order_purpose}) для {order.figi}")
            
            # Логируем событие
            await self.db.log_event(
                event_type="ORDER_CANCELLED",
                account_id=order.account_id,
                figi=order.figi,
                description=f"Отменен ордер {order.order_purpose}",
                details={
                    "order_id": order.order_id,
                    "purpose": order.order_purpose
                }
            )
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при отмене ордера {order.order_id}: {e}")
            
            # Логируем ошибку
            await self.db.log_event(
                event_type="ERROR",
                account_id=order.account_id,
                figi=order.figi,
                description=f"Ошибка при отмене ордера {order.order_purpose}: {str(e)}",
                details={"error": str(e), "order_id": order.order_id}
            )
            
            return False
    
    async def cancel_all_position_orders(self, position_id: int) -> int:
        """
        Отмена всех ордеров для позиции
        
        Args:
            position_id: ID позиции
            
        Returns:
            int: Количество отмененных ордеров
        """
        # Получаем активные ордера для позиции
        active_orders = await self.db.get_active_orders_by_position(position_id)
        
        cancelled_count = 0
        for order in active_orders:
            if await self.cancel_order(order):
                cancelled_count += 1
        
        return cancelled_count
    
    async def check_activation_settings(
        self,
        position: Position,
        account_id: str
    ) -> Tuple[bool, Optional[float], Optional[float]]:
        """
        Проверка настроек активации для позиции
        
        Args:
            position: Позиция
            account_id: ID аккаунта
            
        Returns:
            Tuple[bool, Optional[float], Optional[float]]: (нужно_ли_ждать_активации, sl_activation_pct, tp_activation_pct)
        """
        if not self.settings_manager:
            return False, None, None
        
        # Получаем настройки для инструмента
        settings = await self.settings_manager.get_effective_settings(account_id, position.ticker)
        
        # Проверяем наличие настроек активации
        sl_activation_pct = settings.get('sl_activation_pct')
        tp_activation_pct = settings.get('tp_activation_pct')
        
        # Если хотя бы одна из настроек активации задана, нужно ждать активации
        need_activation = sl_activation_pct is not None or tp_activation_pct is not None
        
        return need_activation, sl_activation_pct, tp_activation_pct
    
    async def add_to_pending_activation(
        self,
        position: Position,
        sl_activation_pct: Optional[float],
        tp_activation_pct: Optional[float]
    ) -> bool:
        """
        Добавление позиции в список ожидающих активации
        
        Args:
            position: Позиция
            sl_activation_pct: Процент активации стоп-лосса
            tp_activation_pct: Процент активации тейк-профита
            
        Returns:
            bool: True, если позиция успешно добавлена
        """
        if not self.stream_handler:
            logger.error("Stream handler не установлен, невозможно добавить позицию в список ожидающих активации")
            return False
        
        # Рассчитываем цены активации
        sl_activation_price = None
        tp_activation_price = None
        
        if sl_activation_pct is not None or tp_activation_pct is not None:
            # Получаем цены активации
            from src.utils.converters import round_to_step
            
            avg_price = Decimal(str(position.average_price))
            min_price_increment, _ = await self.instrument_cache.get_price_step(position.figi)
            
            if sl_activation_pct is not None:
                if position.direction == "LONG":
                    # Для LONG: цена активации SL = средняя_цена * (1 - sl_activation_pct / 100)
                    sl_activation_price = avg_price * (1 - Decimal(str(sl_activation_pct)) / 100)
                else:  # SHORT
                    # Для SHORT: цена активации SL = средняя_цена * (1 + sl_activation_pct / 100)
                    sl_activation_price = avg_price * (1 + Decimal(str(sl_activation_pct)) / 100)
                
                # Округляем до минимального шага цены
                sl_activation_price = round_to_step(sl_activation_price, min_price_increment)
            
            if tp_activation_pct is not None:
                if position.direction == "LONG":
                    # Для LONG: цена активации TP = средняя_цена * (1 + tp_activation_pct / 100)
                    tp_activation_price = avg_price * (1 + Decimal(str(tp_activation_pct)) / 100)
                else:  # SHORT
                    # Для SHORT: цена активации TP = средняя_цена * (1 - tp_activation_pct / 100)
                    tp_activation_price = avg_price * (1 - Decimal(str(tp_activation_pct)) / 100)
                
                # Округляем до минимального шага цены
                tp_activation_price = round_to_step(tp_activation_price, min_price_increment)
        
        # Добавляем в список ожидающих активации
        self.stream_handler._pending_activations[position.figi] = {
            'position_id': position.id,
            'sl_activation_price': float(sl_activation_price) if sl_activation_price else None,
            'tp_activation_price': float(tp_activation_price) if tp_activation_price else None,
            'sl_activated': False,
            'tp_activated': False
        }
        
        logger.info(
            f"Позиция {position.ticker} добавлена в список ожидающих активации: "
            f"SL активация={sl_activation_price if sl_activation_price else 'Нет'}, "
            f"TP активация={tp_activation_price if tp_activation_price else 'Нет'}"
        )
        
        # Логируем событие
        await self.db.log_event(
            event_type="ACTIVATION_PENDING",
            account_id=position.account_id,
            figi=position.figi,
            ticker=position.ticker,
            description=f"Позиция {position.ticker} добавлена в список ожидающих активации",
            details={
                "sl_activation_price": float(sl_activation_price) if sl_activation_price else None,
                "tp_activation_price": float(tp_activation_price) if tp_activation_price else None,
                "position_id": position.id
            }
        )
        
        return True
    
    async def place_sl_tp_orders(
        self,
        position: Position,
        sl_price: Decimal,
        tp_price: Decimal,
        sl_pct: Optional[Decimal] = None
    ) -> Tuple[Optional[Order], Optional[Order]]:
        """
        Выставление стоп-лосс и тейк-профит ордеров для позиции
        
        Args:
            position: Позиция
            sl_price: Цена стоп-лосса
            tp_price: Цена тейк-профита
            sl_pct: Размер стопа в процентах (для расчета цены исполнения)
            
        Returns:
            Tuple[Optional[Order], Optional[Order]]: (стоп-лосс ордер, тейк-профит ордер)
        """
        async with self._lock:
            # Отменяем существующие ордера
            await self.cancel_all_position_orders(position.id)
            
            # Проверяем настройки активации
            need_activation, sl_activation_pct, tp_activation_pct = await self.check_activation_settings(
                position=position,
                account_id=position.account_id
            )
            
            # Если нужно ждать активации, добавляем в список ожидающих
            if need_activation:
                await self.add_to_pending_activation(
                    position=position,
                    sl_activation_pct=sl_activation_pct,
                    tp_activation_pct=tp_activation_pct
                )
                
                # Возвращаем None, так как ордера будут выставлены позже
                return None, None
            
            # Если не нужно ждать активации, выставляем ордера сразу
            sl_order = await self.place_stop_loss_order(position, sl_price, sl_pct)
            tp_order = await self.place_take_profit_order(position, tp_price)
            
            return sl_order, tp_order
    
    async def place_multi_tp_orders(
        self,
        position: Position,
        sl_price: Decimal,
        tp_levels: List[Tuple[Decimal, float]],
        sl_pct: Optional[Decimal] = None
    ) -> Tuple[Optional[Order], List[Optional[Order]]]:
        """
        Выставление стоп-лосс и многоуровневых тейк-профит ордеров
        
        Args:
            position: Позиция
            sl_price: Цена стоп-лосса
            tp_levels: Список кортежей (цена_уровня, процент_объема)
            
        Returns:
            Tuple[Optional[Order], List[Optional[Order]]]: (стоп-лосс ордер, список тейк-профит ордеров)
        """
        async with self._lock:
            # Отменяем существующие ордера
            await self.cancel_all_position_orders(position.id)
            
            # Проверяем настройки активации
            need_activation, sl_activation_pct, tp_activation_pct = await self.check_activation_settings(
                position=position,
                account_id=position.account_id
            )
            
            # Если нужно ждать активации, добавляем в список ожидающих
            if need_activation:
                await self.add_to_pending_activation(
                    position=position,
                    sl_activation_pct=sl_activation_pct,
                    tp_activation_pct=tp_activation_pct
                )
                
                # Возвращаем None, так как ордера будут выставлены позже
                return None, []
            
            # Если не нужно ждать активации, выставляем ордера сразу
            # Выставляем стоп-лосс
            sl_order = await self.place_stop_loss_order(position, sl_price, sl_pct)
            
            # Выставляем многоуровневые тейк-профиты
            tp_orders = []
            total_position_qty = position.quantity
            
            for i, (price, volume_pct) in enumerate(tp_levels, 1):
                # Рассчитываем количество для этого уровня
                level_qty = int(total_position_qty * volume_pct / 100)
                
                # Если количество > 0, выставляем ордер
                if level_qty > 0:
                    tp_order = await self.place_multi_tp_order(
                        position=position,
                        price=price,
                        quantity=level_qty,
                        level_number=i
                    )
                    tp_orders.append(tp_order)
            
            return sl_order, tp_orders
