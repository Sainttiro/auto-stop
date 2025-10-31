"""
Класс для размещения многоуровневых тейк-профит ордеров
"""
from typing import Optional, List, Tuple
from decimal import Decimal

from tinkoff.invest import (
    StopOrderDirection,
    StopOrderExpirationType,
    StopOrderType
)

from src.storage.models import Order, Position
from src.core.utils.order_logger import log_multi_tp_placed
from src.utils.converters import decimal_to_quotation
from src.utils.logger import get_logger
from src.core.orders.base_placer import BaseOrderPlacer

logger = get_logger("core.orders.multi_tp_placer")


class MultiTakeProfitPlacer(BaseOrderPlacer):
    """
    Класс для размещения многоуровневых тейк-профит ордеров
    """
    
    async def place(
        self,
        position: Position,
        tp_levels: List[Tuple[Decimal, float]]
    ) -> List[Optional[Order]]:
        """
        Выставление многоуровневых тейк-профит ордеров
        
        Args:
            position: Позиция
            tp_levels: Список уровней TP в формате [(цена, процент_объема), ...]
            
        Returns:
            List[Optional[Order]]: Список созданных ордеров
        """
        # Определяем направление ордера (противоположное позиции)
        direction = StopOrderDirection.STOP_ORDER_DIRECTION_SELL \
            if position.direction == "LONG" else StopOrderDirection.STOP_ORDER_DIRECTION_BUY
        
        orders = []
        
        # Получаем размер лота для конвертации
        _, lot_size = await self._convert_to_lots(position.figi, 1)
        
        # Выставляем ордера для каждого уровня
        for level_idx, (price, volume_pct) in enumerate(tp_levels, start=1):
            try:
                # Рассчитываем количество для этого уровня
                quantity = int(position.quantity * volume_pct / 100)
                
                # Если количество меньше размера лота, пропускаем уровень
                if quantity < lot_size:
                    logger.warning(
                        f"Пропуск уровня TP {level_idx} для {position.ticker}: "
                        f"количество {quantity} меньше размера лота {lot_size}"
                    )
                    orders.append(None)
                    continue
                
                # Конвертируем количество из акций в лоты
                quantity_in_lots, _ = await self._convert_to_lots(position.figi, quantity)
                
                logger.info(
                    f"Конвертация количества для {position.ticker} (уровень {level_idx}): "
                    f"{quantity} акций → {quantity_in_lots} лотов (размер лота: {lot_size})"
                )
                
                # Выставляем ордер через API
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
                order = await self._create_order_record(
                    order_id=response.stop_order_id,
                    position=position,
                    order_type="STOP",
                    direction="SELL" if direction == StopOrderDirection.STOP_ORDER_DIRECTION_SELL else "BUY",
                    quantity=quantity,
                    price=float(price),
                    stop_price=float(price),
                    order_purpose=f"MULTI_TP_LEVEL_{level_idx}"
                )
                
                # Логируем событие
                await log_multi_tp_placed(
                    db=self.db,
                    order=order,
                    position=position,
                    price=price,
                    quantity=quantity,
                    level_number=level_idx
                )
                
                orders.append(order)
                
            except Exception as e:
                logger.error(f"Ошибка при выставлении TP уровня {level_idx} для {position.ticker}: {e}")
                
                # Логируем ошибку
                await self._log_order_error(
                    account_id=position.account_id,
                    figi=position.figi,
                    ticker=position.ticker,
                    error=e,
                    order_type=f"MULTI_TP_LEVEL_{level_idx}"
                )
                
                orders.append(None)
        
        return orders
