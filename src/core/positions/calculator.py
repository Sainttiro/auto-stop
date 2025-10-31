"""
Расчет средней цены и других метрик позиций
"""
from typing import Tuple
from decimal import Decimal

from src.utils.logger import get_logger

logger = get_logger("core.positions.calculator")


class PositionCalculator:
    """
    Расчет средней цены и других метрик позиций
    
    Отвечает за расчет средней цены при усреднении позиции,
    расчет P&L и других метрик.
    """
    
    def calculate_average_price(
        self,
        old_qty: int,
        old_price: Decimal,
        new_qty: int,
        new_price: Decimal
    ) -> Decimal:
        """
        Расчет новой средней цены при усреднении позиции
        
        Args:
            old_qty: Старое количество лотов
            old_price: Старая средняя цена
            new_qty: Новое количество лотов
            new_price: Цена новых лотов
            
        Returns:
            Decimal: Новая средняя цена
        """
        if old_qty + new_qty == 0:
            return Decimal(0)
            
        total_cost = (old_qty * old_price) + (new_qty * new_price)
        total_qty = old_qty + new_qty
        
        avg_price = total_cost / total_qty
        
        logger.debug(
            f"Расчет средней цены: "
            f"({old_qty} * {old_price}) + ({new_qty} * {new_price}) = {total_cost} / {total_qty} = {avg_price}"
        )
        
        return avg_price
    
    def calculate_pnl(
        self,
        entry_price: Decimal,
        current_price: Decimal,
        quantity: int,
        direction: str
    ) -> Decimal:
        """
        Расчет P&L (прибыли/убытка) позиции
        
        Args:
            entry_price: Цена входа (средняя цена)
            current_price: Текущая цена
            quantity: Количество лотов
            direction: Направление позиции ("LONG" или "SHORT")
            
        Returns:
            Decimal: P&L в абсолютном выражении
        """
        if quantity == 0:
            return Decimal(0)
        
        if direction == "LONG":
            pnl = (current_price - entry_price) * quantity
        else:  # SHORT
            pnl = (entry_price - current_price) * quantity
        
        logger.debug(
            f"Расчет P&L ({direction}): "
            f"({current_price} - {entry_price}) * {quantity} = {pnl}"
        )
        
        return pnl
    
    def calculate_pnl_percent(
        self,
        entry_price: Decimal,
        current_price: Decimal,
        direction: str
    ) -> Decimal:
        """
        Расчет P&L в процентах
        
        Args:
            entry_price: Цена входа (средняя цена)
            current_price: Текущая цена
            direction: Направление позиции ("LONG" или "SHORT")
            
        Returns:
            Decimal: P&L в процентах
        """
        if entry_price == 0:
            return Decimal(0)
        
        if direction == "LONG":
            pnl_pct = (current_price - entry_price) / entry_price * 100
        else:  # SHORT
            pnl_pct = (entry_price - current_price) / entry_price * 100
        
        logger.debug(
            f"Расчет P&L% ({direction}): "
            f"({current_price} - {entry_price}) / {entry_price} * 100 = {pnl_pct}%"
        )
        
        return pnl_pct
    
    def calculate_risk_reward(
        self,
        entry_price: Decimal,
        sl_price: Decimal,
        tp_price: Decimal
    ) -> Decimal:
        """
        Расчет соотношения риск/доходность
        
        Args:
            entry_price: Цена входа (средняя цена)
            sl_price: Цена стоп-лосса
            tp_price: Цена тейк-профита
            
        Returns:
            Decimal: Соотношение риск/доходность (R/R)
        """
        if entry_price == 0 or sl_price == 0:
            return Decimal(0)
        
        risk = abs(entry_price - sl_price)
        reward = abs(tp_price - entry_price)
        
        if risk == 0:
            return Decimal(0)
        
        rr = reward / risk
        
        logger.debug(
            f"Расчет R/R: "
            f"{reward} / {risk} = {rr}"
        )
        
        return rr
    
    def validate_quantity(self, quantity: int, lot_size: int) -> Tuple[bool, str]:
        """
        Валидация количества лотов
        
        Args:
            quantity: Количество лотов
            lot_size: Размер лота
            
        Returns:
            Tuple[bool, str]: (валидно, сообщение об ошибке)
        """
        if quantity <= 0:
            return False, "Количество должно быть положительным"
        
        if quantity % lot_size != 0:
            return False, f"Количество должно быть кратно размеру лота ({lot_size})"
        
        return True, ""
