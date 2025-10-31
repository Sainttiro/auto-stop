"""
Класс для размещения стоп-лосс ордеров
"""
from typing import Optional
from decimal import Decimal

from tinkoff.invest import (
    StopOrderDirection,
    StopOrderExpirationType,
    StopOrderType
)

from src.storage.models import Order, Position
from src.core.utils.price_calculator import calculate_execution_price
from src.core.utils.order_logger import log_stop_loss_placed
from src.utils.converters import decimal_to_quotation
from src.utils.logger import get_logger
from src.core.orders.base_placer import BaseOrderPlacer

logger = get_logger("core.orders.stop_loss_placer")


class StopLossPlacer(BaseOrderPlacer):
    """
    Класс для размещения стоп-лосс ордеров
    """
    
    async def place(
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
            # Конвертируем количество из акций в лоты
            quantity_in_lots, lot_size = await self._convert_to_lots(position.figi, position.quantity)
            
            logger.info(
                f"Конвертация количества для {position.ticker}: "
                f"{position.quantity} акций → {quantity_in_lots} лотов (размер лота: {lot_size})"
            )
            
            # Рассчитываем цену исполнения с пропорциональным смещением от цены активации
            execution_price = await calculate_execution_price(
                stop_price=stop_price,
                sl_pct=sl_pct or Decimal('0.5'),  # Если sl_pct не указан, используем 0.5%
                direction=position.direction,
                figi=position.figi,
                instrument_cache=self.instrument_cache
            )
            
            logger.info(
                f"Рассчитана цена исполнения для {position.ticker}: "
                f"stop_price={stop_price}, execution_price={execution_price}"
            )
            
            # Выставляем ордер через API
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
            order = await self._create_order_record(
                order_id=response.stop_order_id,
                position=position,
                order_type="STOP",
                direction="SELL" if direction == StopOrderDirection.STOP_ORDER_DIRECTION_SELL else "BUY",
                quantity=position.quantity,
                price=float(execution_price),
                stop_price=float(stop_price),
                order_purpose="STOP_LOSS"
            )
            
            # Логируем событие
            await log_stop_loss_placed(
                db=self.db,
                order=order,
                position=position,
                stop_price=stop_price,
                execution_price=execution_price
            )
            
            return order
        
        except Exception as e:
            logger.error(f"Ошибка при выставлении стоп-лосса для {position.ticker}: {e}")
            
            # Логируем ошибку
            await self._log_order_error(
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                error=e,
                order_type="STOP_LOSS"
            )
            
            return None
