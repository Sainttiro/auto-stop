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
        
        # Получаем размер лота напрямую из кэша
        lot_size = await self.instrument_cache.get_lot_size(position.figi)
        
        # ВАЖНО: Конвертируем общее количество акций в лоты
        total_shares = position.quantity
        total_lots = total_shares // lot_size
        
        # Проверка: если лотов меньше, чем уровней TP
        if total_lots < len(tp_levels):
            logger.warning(
                f"⚠️ Недостаточно лотов для распределения по всем уровням TP для {position.ticker}: "
                f"{total_lots} лотов на {len(tp_levels)} уровней. "
                f"Некоторые уровни будут пропущены."
            )
        
        # Шаг 1: Расширяем tp_levels, добавляя точное (дробное) количество ЛОТОВ для каждого уровня
        tp_levels_extended = []
        for level_idx, (price, volume_pct) in enumerate(tp_levels, start=1):
            exact_lots = total_lots * volume_pct / 100
            tp_levels_extended.append((price, volume_pct, exact_lots))
        
        # Шаг 2: Умное распределение ЛОТОВ
        allocated_lots = 0
        
        # Сначала округляем вниз и считаем, сколько лотов "потеряли"
        quantities_in_lots = []
        for price, volume_pct, exact_lots in tp_levels_extended:
            # Округляем вниз до ближайшего целого
            rounded_lots = int(exact_lots)
            quantities_in_lots.append(rounded_lots)
            allocated_lots += rounded_lots
        
        # Распределяем оставшиеся лоты по уровням, начиная с тех, у которых была наибольшая дробная часть
        remaining_lots = total_lots - allocated_lots
        
        if remaining_lots > 0:
            # Сортируем уровни по убыванию дробной части
            fractional_parts = [(i, tp_levels_extended[i][2] - quantities_in_lots[i]) 
                               for i in range(len(tp_levels_extended))]
            fractional_parts.sort(key=lambda x: x[1], reverse=True)
            
            # Распределяем оставшиеся лоты
            for i in range(min(remaining_lots, len(fractional_parts))):
                level_idx = fractional_parts[i][0]
                quantities_in_lots[level_idx] += 1
        
        # Проверяем, что сумма распределенных лотов равна общему количеству лотов
        assert sum(quantities_in_lots) == total_lots, f"Ошибка распределения лотов: {sum(quantities_in_lots)} != {total_lots}"
        
        # Конвертируем лоты обратно в акции для логирования и API
        quantities_in_shares = [lots * lot_size for lots in quantities_in_lots]
        
        logger.info(f"Умное распределение лотов для {position.ticker}: {quantities_in_lots} лотов = {quantities_in_shares} акций (всего {total_lots} лотов = {total_shares} акций)")
        
        # Выставляем ордера для каждого уровня
        for level_idx, ((price, volume_pct, _), lots, shares) in enumerate(zip(tp_levels_extended, quantities_in_lots, quantities_in_shares), start=1):
            try:
                # Если количество лотов равно 0, пропускаем уровень
                if lots == 0:
                    logger.warning(
                        f"Пропуск уровня TP {level_idx} для {position.ticker}: "
                        f"0 лотов (0 акций)"
                    )
                    orders.append(None)
                    continue
                
                logger.info(
                    f"Конвертация количества для {position.ticker} (уровень {level_idx}): "
                    f"{shares} акций → {lots} лотов (размер лота: {lot_size})"
                )
                
                # Используем количество в лотах напрямую
                quantity_in_lots = lots
                quantity = shares  # Для записи в БД и логирования
                
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
