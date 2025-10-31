"""
Утилиты для работы с ордерами, позициями и ценами
"""

# Экспорт функций для конвертации лотов
from src.core.utils.lot_converter import (
    convert_to_lots,
    convert_from_lots
)

# Экспорт функций для логирования ордеров
from src.core.utils.order_logger import (
    log_order_event,
    log_stop_loss_placed,
    log_take_profit_placed,
    log_multi_tp_placed,
    log_order_cancelled,
    log_order_error
)

# Экспорт функций для расчета цен
from src.core.utils.price_calculator import (
    calculate_execution_price,
    calculate_sl_tp_prices,
    calculate_activation_prices
)

__all__ = [
    # Конвертация лотов
    'convert_to_lots',
    'convert_from_lots',
    
    # Логирование ордеров
    'log_order_event',
    'log_stop_loss_placed',
    'log_take_profit_placed',
    'log_multi_tp_placed',
    'log_order_cancelled',
    'log_order_error',
    
    # Расчет цен
    'calculate_execution_price',
    'calculate_sl_tp_prices',
    'calculate_activation_prices'
]
