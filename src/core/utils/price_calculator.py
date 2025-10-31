"""
Утилиты для расчета цен исполнения ордеров
"""
from typing import Tuple, Optional
from decimal import Decimal

from src.api.instrument_info import InstrumentInfoCache
from src.utils.converters import round_to_step
from src.utils.logger import get_logger

logger = get_logger("core.utils.price_calculator")


async def calculate_execution_price(
    stop_price: Decimal,
    sl_pct: Decimal,
    direction: str,
    figi: str,
    instrument_cache: InstrumentInfoCache
) -> Decimal:
    """
    Расчет цены исполнения для стоп-лосса
    
    Смещение = 10% от размера стопа, но не менее 1 шага цены
    
    Args:
        stop_price: Цена активации стоп-лосса
        sl_pct: Размер стопа в процентах
        direction: Направление позиции ("LONG" или "SHORT")
        figi: FIGI инструмента
        instrument_cache: Кэш информации об инструментах
        
    Returns:
        Decimal: Цена исполнения
    """
    # Получаем минимальный шаг цены
    min_price_increment, _ = await instrument_cache.get_price_step(figi)
    
    # Рассчитываем смещение (10% от размера стопа)
    execution_offset_pct = sl_pct * Decimal('0.1')
    
    # Минимальное смещение - 1 шаг цены
    min_offset_pct = min_price_increment / stop_price * Decimal('100')
    execution_offset_pct = max(execution_offset_pct, min_offset_pct)
    
    # Рассчитываем цену исполнения в зависимости от направления
    if direction == "LONG":  # SELL для LONG позиции
        execution_price = stop_price * (Decimal('1') - execution_offset_pct / Decimal('100'))
    else:  # BUY для SHORT позиции
        execution_price = stop_price * (Decimal('1') + execution_offset_pct / Decimal('100'))
    
    # Округляем до минимального шага цены
    execution_price = round_to_step(execution_price, min_price_increment)
    
    logger.debug(
        f"Рассчитана цена исполнения: "
        f"stop_price={stop_price}, execution_price={execution_price} "
        f"(смещение {execution_offset_pct:.3f}%)"
    )
    
    return execution_price


async def calculate_sl_tp_prices(
    avg_price: Decimal,
    direction: str,
    sl_pct: Decimal,
    tp_pct: Decimal,
    figi: str,
    instrument_cache: InstrumentInfoCache
) -> Tuple[Decimal, Decimal]:
    """
    Расчет цен стоп-лосса и тейк-профита
    
    Args:
        avg_price: Средняя цена позиции
        direction: Направление позиции ("LONG" или "SHORT")
        sl_pct: Размер стопа в процентах
        tp_pct: Размер тейка в процентах
        figi: FIGI инструмента
        instrument_cache: Кэш информации об инструментах
        
    Returns:
        Tuple[Decimal, Decimal]: (цена стоп-лосса, цена тейк-профита)
    """
    # Получаем минимальный шаг цены
    min_price_increment, _ = await instrument_cache.get_price_step(figi)
    
    # Рассчитываем уровни
    if direction == "LONG":
        sl_price = avg_price * (1 - sl_pct / 100)
        tp_price = avg_price * (1 + tp_pct / 100)
    else:  # SHORT
        sl_price = avg_price * (1 + sl_pct / 100)
        tp_price = avg_price * (1 - tp_pct / 100)
    
    # Округляем до минимального шага цены
    sl_price = round_to_step(sl_price, min_price_increment)
    tp_price = round_to_step(tp_price, min_price_increment)
    
    logger.debug(
        f"Рассчитаны уровни: "
        f"SL={sl_price} ({sl_pct}%), TP={tp_price} ({tp_pct}%)"
    )
    
    return sl_price, tp_price


async def calculate_activation_prices(
    avg_price: Decimal,
    direction: str,
    sl_activation_pct: Optional[float],
    tp_activation_pct: Optional[float],
    figi: str,
    instrument_cache: InstrumentInfoCache
) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Расчет цен активации для SL и TP
    
    Args:
        avg_price: Средняя цена позиции
        direction: Направление позиции ("LONG" или "SHORT")
        sl_activation_pct: Процент активации стоп-лосса
        tp_activation_pct: Процент активации тейк-профита
        figi: FIGI инструмента
        instrument_cache: Кэш информации об инструментах
        
    Returns:
        Tuple[Optional[Decimal], Optional[Decimal]]: (цена_активации_SL, цена_активации_TP)
    """
    # Получаем минимальный шаг цены
    min_price_increment, _ = await instrument_cache.get_price_step(figi)
    
    sl_activation_price = None
    tp_activation_price = None
    
    # Расчет цены активации SL
    if sl_activation_pct is not None:
        if direction == "LONG":
            # Для LONG: цена активации SL = средняя_цена * (1 - sl_activation_pct / 100)
            sl_activation_price = avg_price * (1 - Decimal(str(sl_activation_pct)) / 100)
        else:  # SHORT
            # Для SHORT: цена активации SL = средняя_цена * (1 + sl_activation_pct / 100)
            sl_activation_price = avg_price * (1 + Decimal(str(sl_activation_pct)) / 100)
        
        # Округляем до минимального шага цены
        sl_activation_price = round_to_step(sl_activation_price, min_price_increment)
        
        logger.debug(
            f"Рассчитана цена активации SL: "
            f"{sl_activation_price} ({sl_activation_pct}%)"
        )
    
    # Расчет цены активации TP
    if tp_activation_pct is not None:
        if direction == "LONG":
            # Для LONG: цена активации TP = средняя_цена * (1 + tp_activation_pct / 100)
            tp_activation_price = avg_price * (1 + Decimal(str(tp_activation_pct)) / 100)
        else:  # SHORT
            # Для SHORT: цена активации TP = средняя_цена * (1 - tp_activation_pct / 100)
            tp_activation_price = avg_price * (1 - Decimal(str(tp_activation_pct)) / 100)
        
        # Округляем до минимального шага цены
        tp_activation_price = round_to_step(tp_activation_price, min_price_increment)
        
        logger.debug(
            f"Рассчитана цена активации TP: "
            f"{tp_activation_price} ({tp_activation_pct}%)"
        )
    
    return sl_activation_price, tp_activation_price
