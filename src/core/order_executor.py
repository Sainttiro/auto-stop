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

from src.api.client import TinkoffAPIClient
from src.storage.database import Database
from src.storage.models import Order, Position
from src.utils.converters import decimal_to_quotation
from src.utils.logger import get_logger

logger = get_logger("core.order_executor")


class OrderExecutor:
    """
    Выставление и управление ордерами
    """
    
    def __init__(self, api_client: TinkoffAPIClient, database: Database):
        """
        Инициализация исполнителя ордеров
        
        Args:
            api_client: Клиент API Tinkoff
            database: Объект для работы с базой данных
        """
        self.api_client = api_client
        self.db = database
        self._lock = asyncio.Lock()
    
    async def place_stop_loss_order(
        self,
        position: Position,
        stop_price: Decimal
    ) -> Optional[Order]:
        """
        Выставление стоп-лосс ордера
        
        Args:
            position: Позиция
            stop_price: Цена стоп-лосса
            
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
            # Выставляем ордер через API (передаем параметры напрямую)
            response = await self.api_client.services.stop_orders.post_stop_order(
                figi=position.figi,
                quantity=position.quantity,
                price=decimal_to_quotation(stop_price),
                stop_price=decimal_to_quotation(stop_price),
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
                price=float(stop_price),
                stop_price=float(stop_price),
                status="NEW",
                order_purpose="STOP_LOSS"
            )
            
            await self.db.add(order)
            
            logger.info(
                f"Выставлен стоп-лосс (STOP_LIMIT) для {position.ticker} ({position.instrument_type}): "
                f"цена={stop_price}, количество={position.quantity}, "
                f"ID={response.stop_order_id}"
            )
            
            # Логируем событие
            await self.db.log_event(
                event_type="STOP_LOSS_PLACED",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"Выставлен стоп-лосс для {position.ticker}: цена={stop_price}",
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
            # Выставляем ордер через API (передаем параметры напрямую)
            response = await self.api_client.services.stop_orders.post_stop_order(
                figi=position.figi,
                quantity=position.quantity,
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
            quantity: Количество для закрытия на этом уровне
            level_number: Номер уровня
            
        Returns:
            Optional[Order]: Созданный ордер или None в случае ошибки
        """
        # Определяем направление ордера (противоположное позиции)
        direction = StopOrderDirection.STOP_ORDER_DIRECTION_SELL \
            if position.direction == "LONG" else StopOrderDirection.STOP_ORDER_DIRECTION_BUY
        
        try:
            # Выставляем ордер через API (передаем параметры напрямую)
            response = await self.api_client.services.stop_orders.post_stop_order(
                figi=position.figi,
                quantity=quantity,
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
    
    async def place_sl_tp_orders(
        self,
        position: Position,
        sl_price: Decimal,
        tp_price: Decimal
    ) -> Tuple[Optional[Order], Optional[Order]]:
        """
        Выставление стоп-лосс и тейк-профит ордеров для позиции
        
        Args:
            position: Позиция
            sl_price: Цена стоп-лосса
            tp_price: Цена тейк-профита
            
        Returns:
            Tuple[Optional[Order], Optional[Order]]: (стоп-лосс ордер, тейк-профит ордер)
        """
        async with self._lock:
            # Отменяем существующие ордера
            await self.cancel_all_position_orders(position.id)
            
            # Выставляем новые ордера
            sl_order = await self.place_stop_loss_order(position, sl_price)
            tp_order = await self.place_take_profit_order(position, tp_price)
            
            return sl_order, tp_order
    
    async def place_multi_tp_orders(
        self,
        position: Position,
        sl_price: Decimal,
        tp_levels: List[Tuple[Decimal, float]]
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
            
            # Выставляем стоп-лосс
            sl_order = await self.place_stop_loss_order(position, sl_price)
            
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
