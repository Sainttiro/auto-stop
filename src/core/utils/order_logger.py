"""
Централизованное логирование ордеров
"""
from typing import Dict, Any, Optional
from decimal import Decimal

from src.storage.database import Database
from src.storage.models import Position, Order
from src.utils.logger import get_logger

logger = get_logger("core.utils.order_logger")


async def log_order_event(
    db: Database,
    event_type: str,
    account_id: str,
    figi: str,
    ticker: Optional[str] = None,
    description: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Логирование события, связанного с ордером
    
    Args:
        db: Объект для работы с базой данных
        event_type: Тип события (STOP_LOSS_PLACED, TAKE_PROFIT_PLACED, ORDER_CANCELLED, и т.д.)
        account_id: ID счета
        figi: FIGI инструмента
        ticker: Тикер инструмента (опционально)
        description: Описание события (опционально)
        details: Дополнительные детали события (опционально)
    """
    try:
        await db.log_event(
            event_type=event_type,
            account_id=account_id,
            figi=figi,
            ticker=ticker,
            description=description,
            details=details
        )
    except Exception as e:
        logger.error(f"Ошибка при логировании события {event_type}: {e}")


async def log_stop_loss_placed(
    db: Database,
    order: Order,
    position: Position,
    stop_price: Decimal,
    execution_price: Decimal
) -> None:
    """
    Логирование выставления стоп-лосса
    
    Args:
        db: Объект для работы с базой данных
        order: Объект ордера
        position: Объект позиции
        stop_price: Цена активации стоп-лосса
        execution_price: Цена исполнения стоп-лосса
    """
    description = f"Выставлен стоп-лосс для {position.ticker}: цена активации={stop_price}, цена исполнения={execution_price}"
    details = {
        "order_id": order.order_id,
        "stop_price": float(stop_price),
        "execution_price": float(execution_price),
        "quantity": position.quantity
    }
    
    await log_order_event(
        db=db,
        event_type="STOP_LOSS_PLACED",
        account_id=position.account_id,
        figi=position.figi,
        ticker=position.ticker,
        description=description,
        details=details
    )
    
    logger.info(
        f"Выставлен стоп-лосс (STOP_LIMIT) для {position.ticker} ({position.instrument_type}): "
        f"цена активации={stop_price}, цена исполнения={execution_price}, "
        f"количество={position.quantity}, ID={order.order_id}"
    )


async def log_take_profit_placed(
    db: Database,
    order: Order,
    position: Position,
    take_price: Decimal
) -> None:
    """
    Логирование выставления тейк-профита
    
    Args:
        db: Объект для работы с базой данных
        order: Объект ордера
        position: Объект позиции
        take_price: Цена тейк-профита
    """
    description = f"Выставлен тейк-профит для {position.ticker}: цена={take_price}"
    details = {
        "order_id": order.order_id,
        "price": float(take_price),
        "quantity": position.quantity
    }
    
    await log_order_event(
        db=db,
        event_type="TAKE_PROFIT_PLACED",
        account_id=position.account_id,
        figi=position.figi,
        ticker=position.ticker,
        description=description,
        details=details
    )
    
    logger.info(
        f"Выставлен тейк-профит для {position.ticker}: "
        f"цена={take_price}, количество={position.quantity}, "
        f"ID={order.order_id}"
    )


async def log_multi_tp_placed(
    db: Database,
    order: Order,
    position: Position,
    price: Decimal,
    quantity: int,
    level_number: int
) -> None:
    """
    Логирование выставления многоуровневого тейк-профита
    
    Args:
        db: Объект для работы с базой данных
        order: Объект ордера
        position: Объект позиции
        price: Цена уровня
        quantity: Количество для закрытия на этом уровне
        level_number: Номер уровня
    """
    description = f"Выставлен многоуровневый TP (уровень {level_number}) для {position.ticker}: цена={price}"
    details = {
        "order_id": order.order_id,
        "price": float(price),
        "quantity": quantity,
        "level": level_number
    }
    
    await log_order_event(
        db=db,
        event_type="MULTI_TP_PLACED",
        account_id=position.account_id,
        figi=position.figi,
        ticker=position.ticker,
        description=description,
        details=details
    )
    
    logger.info(
        f"Выставлен многоуровневый TP (уровень {level_number}) для {position.ticker}: "
        f"цена={price}, количество={quantity}, "
        f"ID={order.order_id}"
    )


async def log_order_cancelled(
    db: Database,
    order: Order
) -> None:
    """
    Логирование отмены ордера
    
    Args:
        db: Объект для работы с базой данных
        order: Объект ордера
    """
    description = f"Отменен ордер {order.order_purpose}"
    details = {
        "order_id": order.order_id,
        "purpose": order.order_purpose
    }
    
    await log_order_event(
        db=db,
        event_type="ORDER_CANCELLED",
        account_id=order.account_id,
        figi=order.figi,
        description=description,
        details=details
    )
    
    logger.info(f"Отменен ордер {order.order_id} ({order.order_purpose}) для {order.figi}")


async def log_order_error(
    db: Database,
    account_id: str,
    figi: str,
    ticker: Optional[str],
    error: Exception,
    order_type: str = "UNKNOWN",
    order_id: Optional[str] = None
) -> None:
    """
    Логирование ошибки при работе с ордером
    
    Args:
        db: Объект для работы с базой данных
        account_id: ID счета
        figi: FIGI инструмента
        ticker: Тикер инструмента
        error: Объект исключения
        order_type: Тип ордера (STOP_LOSS, TAKE_PROFIT, и т.д.)
        order_id: ID ордера (если есть)
    """
    description = f"Ошибка при работе с ордером {order_type}: {str(error)}"
    details = {
        "error": str(error),
        "order_type": order_type
    }
    
    if order_id:
        details["order_id"] = order_id
    
    await log_order_event(
        db=db,
        event_type="ORDER_ERROR",
        account_id=account_id,
        figi=figi,
        ticker=ticker,
        description=description,
        details=details
    )
    
    logger.error(f"Ошибка при работе с ордером {order_type} для {ticker if ticker else figi}: {error}")
