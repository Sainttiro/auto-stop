"""
Утилиты для конвертации количества акций в лоты и обратно
"""
from typing import Tuple
from decimal import Decimal

from src.api.instrument_info import InstrumentInfoCache
from src.utils.logger import get_logger

logger = get_logger("core.utils.lot_converter")


async def convert_to_lots(
    instrument_cache: InstrumentInfoCache,
    figi: str,
    quantity: int
) -> Tuple[int, int]:
    """
    Конвертация количества из акций в лоты
    
    Args:
        instrument_cache: Кэш информации об инструментах
        figi: FIGI инструмента
        quantity: Количество в акциях
        
    Returns:
        Tuple[int, int]: (количество в лотах, размер лота)
    """
    # Получаем размер лота для инструмента
    lot_size = await instrument_cache.get_lot_size(figi)
    
    # Конвертируем количество из акций в лоты
    quantity_in_lots = quantity // lot_size
    
    # Проверка: количество должно быть > 0
    if quantity_in_lots <= 0:
        logger.error(
            f"Ошибка: количество в лотах = {quantity_in_lots} для {figi}. "
            f"Позиция: {quantity} акций, размер лота: {lot_size}"
        )
        raise ValueError(f"Количество в лотах должно быть > 0 (получено {quantity_in_lots})")
    
    logger.debug(
        f"Конвертация количества для {figi}: "
        f"{quantity} акций → {quantity_in_lots} лотов (размер лота: {lot_size})"
    )
    
    return quantity_in_lots, lot_size


async def convert_from_lots(
    instrument_cache: InstrumentInfoCache,
    figi: str,
    lots: int
) -> int:
    """
    Конвертация количества из лотов в акции
    
    Args:
        instrument_cache: Кэш информации об инструментах
        figi: FIGI инструмента
        lots: Количество в лотах
        
    Returns:
        int: Количество в акциях
    """
    # Получаем размер лота для инструмента
    lot_size = await instrument_cache.get_lot_size(figi)
    
    # Конвертируем количество из лотов в акции
    quantity = lots * lot_size
    
    logger.debug(
        f"Конвертация количества для {figi}: "
        f"{lots} лотов → {quantity} акций (размер лота: {lot_size})"
    )
    
    return quantity
