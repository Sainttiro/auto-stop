"""
Класс для размещения тейк-профит ордеров
"""
from typing import Optional
from decimal import Decimal

from tinkoff.invest import (
    StopOrderDirection,
    StopOrderExpirationType,
    StopOrderType
)

from src.storage.models import Order, Position
from src.core.utils.order_logger import log_take_profit_placed
from src.utils.converters import decimal_to_quotation
from src.utils.logger import get_logger
from src.core.orders.base_placer import BaseOrderPlacer

logger = get_logger("core.orders.take_profit_placer")


class TakeProfitPlacer(BaseOrderPlacer):
    """
    Класс для размещения тейк-профит ордеров
    """
    
    async def place(
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
            # Конвертируем количество из акций в лоты
            quantity_in_lots, lot_size = await self._convert_to_lots(position.figi, position.quantity)
            
            logger.info(
                f"Конвертация количества для {position.ticker}: "
                f"{position.quantity} акций → {quantity_in_lots} лотов (размер лота: {lot_size})"
            )
            
            # Выставляем ордер через API
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
            order = await self._create_order_record(
                order_id=response.stop_order_id,
                position=position,
                order_type="STOP",
                direction="SELL" if direction == StopOrderDirection.STOP_ORDER_DIRECTION_SELL else "BUY",
                quantity=position.quantity,
                price=float(take_price),
                stop_price=float(take_price),
                order_purpose="TAKE_PROFIT"
            )
            
            # Логируем событие
            await log_take_profit_placed(
                db=self.db,
                order=order,
                position=position,
                take_price=take_price
            )
            
            return order
        
        except Exception as e:
            logger.error(f"Ошибка при выставлении тейк-профита для {position.ticker}: {e}")
            
            # Логируем ошибку
            await self._log_order_error(
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                error=e,
                order_type="TAKE_PROFIT"
            )
            
            return None
