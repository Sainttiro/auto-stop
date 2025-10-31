"""
Базовый класс для размещения ордеров
"""
from typing import Optional, Dict, Any
from decimal import Decimal

from tinkoff.invest import (
    OrderDirection,
    OrderType,
    StopOrderDirection,
    StopOrderExpirationType,
    StopOrderType
)

from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.storage.database import Database
from src.storage.models import Order, Position
from src.core.utils.lot_converter import convert_to_lots
from src.core.utils.order_logger import log_order_event, log_order_error
from src.utils.converters import decimal_to_quotation
from src.utils.logger import get_logger

logger = get_logger("core.orders.base_placer")


class BaseOrderPlacer:
    """
    Базовый класс для размещения ордеров
    """
    
    def __init__(
        self,
        api_client: TinkoffAPIClient,
        database: Database,
        instrument_cache: InstrumentInfoCache
    ):
        """
        Инициализация базового класса
        
        Args:
            api_client: Клиент API Tinkoff
            database: Объект для работы с базой данных
            instrument_cache: Кэш информации об инструментах
        """
        self.api_client = api_client
        self.db = database
        self.instrument_cache = instrument_cache
    
    async def _convert_to_lots(self, figi: str, quantity: int) -> tuple[int, int]:
        """
        Конвертация количества из акций в лоты
        
        Args:
            figi: FIGI инструмента
            quantity: Количество в акциях
            
        Returns:
            tuple[int, int]: (количество в лотах, размер лота)
        """
        return await convert_to_lots(self.instrument_cache, figi, quantity)
    
    async def _create_order_record(
        self,
        order_id: str,
        position: Position,
        order_type: str,
        direction: str,
        quantity: int,
        price: float,
        stop_price: Optional[float] = None,
        order_purpose: str = "UNKNOWN"
    ) -> Order:
        """
        Создание записи ордера в БД
        
        Args:
            order_id: ID ордера
            position: Позиция
            order_type: Тип ордера
            direction: Направление
            quantity: Количество
            price: Цена
            stop_price: Цена активации (для стоп-ордеров)
            order_purpose: Назначение ордера
            
        Returns:
            Order: Созданный ордер
        """
        order = Order(
            order_id=order_id,
            position_id=position.id,
            account_id=position.account_id,
            figi=position.figi,
            order_type=order_type,
            direction=direction,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            status="NEW",
            order_purpose=order_purpose
        )
        
        await self.db.add(order)
        return order
    
    async def _log_order_error(
        self,
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
            account_id: ID счета
            figi: FIGI инструмента
            ticker: Тикер инструмента
            error: Объект исключения
            order_type: Тип ордера
            order_id: ID ордера (если есть)
        """
        await log_order_error(
            db=self.db,
            account_id=account_id,
            figi=figi,
            ticker=ticker,
            error=error,
            order_type=order_type,
            order_id=order_id
        )
