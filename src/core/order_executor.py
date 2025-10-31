"""
Координатор размещения и отмены ордеров
"""
from typing import Optional, List, Tuple
from decimal import Decimal

from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.storage.database import Database
from src.storage.models import Order, Position
from src.utils.logger import get_logger

# Импортируем компоненты для работы с ордерами
from src.core.orders.stop_loss_placer import StopLossPlacer
from src.core.orders.take_profit_placer import TakeProfitPlacer
from src.core.orders.multi_tp_placer import MultiTakeProfitPlacer
from src.core.orders.order_canceller import OrderCanceller

logger = get_logger("core.order_executor")


class OrderExecutor:
    """
    Координатор размещения и отмены ордеров
    
    Управляет жизненным циклом ордеров и делегирует размещение специализированным компонентам.
    """
    
    def __init__(
        self,
        api_client: TinkoffAPIClient,
        database: Database,
        instrument_cache: InstrumentInfoCache
    ):
        """
        Инициализация координатора ордеров
        
        Args:
            api_client: Клиент API Tinkoff
            database: Объект для работы с базой данных
            instrument_cache: Кэш информации об инструментах
        """
        self.api_client = api_client
        self.db = database
        self.instrument_cache = instrument_cache
        
        # Создаем компоненты для работы с ордерами
        self._stop_loss_placer = StopLossPlacer(
            api_client=api_client,
            database=database,
            instrument_cache=instrument_cache
        )
        
        self._take_profit_placer = TakeProfitPlacer(
            api_client=api_client,
            database=database,
            instrument_cache=instrument_cache
        )
        
        self._multi_tp_placer = MultiTakeProfitPlacer(
            api_client=api_client,
            database=database,
            instrument_cache=instrument_cache
        )
        
        self._order_canceller = OrderCanceller(
            api_client=api_client,
            database=database,
            instrument_cache=instrument_cache
        )
    
    async def place_stop_loss_order(
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
        logger.info(f"Выставление стоп-лосса для {position.ticker} по цене {stop_price}")
        return await self._stop_loss_placer.place(
            position=position,
            stop_price=stop_price,
            sl_pct=sl_pct
        )
    
    async def place_take_profit_order(
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
        logger.info(f"Выставление тейк-профита для {position.ticker} по цене {take_price}")
        return await self._take_profit_placer.place(
            position=position,
            take_price=take_price
        )
    
    async def place_multi_tp_orders(
        self,
        position: Position,
        sl_price: Decimal,
        tp_levels: List[Tuple[Decimal, float]],
        sl_pct: Optional[Decimal] = None
    ) -> Tuple[Optional[Order], List[Optional[Order]]]:
        """
        Выставление стоп-лосса и многоуровневых тейк-профит ордеров
        
        Args:
            position: Позиция
            sl_price: Цена стоп-лосса
            tp_levels: Список уровней TP в формате [(цена, процент_объема), ...]
            sl_pct: Размер стопа в процентах (для расчета цены исполнения)
            
        Returns:
            Tuple[Optional[Order], List[Optional[Order]]]: (стоп-лосс ордер, список тейк-профит ордеров)
        """
        logger.info(
            f"Выставление многоуровневых ордеров для {position.ticker}: "
            f"SL={sl_price}, TP уровней={len(tp_levels)}"
        )
        
        # Выставляем стоп-лосс
        sl_order = await self._stop_loss_placer.place(
            position=position,
            stop_price=sl_price,
            sl_pct=sl_pct
        )
        
        # Выставляем многоуровневые тейк-профиты
        tp_orders = await self._multi_tp_placer.place(
            position=position,
            tp_levels=tp_levels
        )
        
        return sl_order, tp_orders
    
    async def place_sl_tp_orders(
        self,
        position: Position,
        sl_price: Decimal,
        tp_price: Decimal,
        sl_pct: Optional[Decimal] = None
    ) -> Tuple[Optional[Order], Optional[Order]]:
        """
        Выставление стоп-лосс и тейк-профит ордеров
        
        Args:
            position: Позиция
            sl_price: Цена стоп-лосса
            tp_price: Цена тейк-профита
            sl_pct: Размер стопа в процентах (для расчета цены исполнения)
            
        Returns:
            Tuple[Optional[Order], Optional[Order]]: (стоп-лосс ордер, тейк-профит ордер)
        """
        logger.info(
            f"Выставление ордеров для {position.ticker}: "
            f"SL={sl_price}, TP={tp_price}"
        )
        
        # Выставляем стоп-лосс
        sl_order = await self._stop_loss_placer.place(
            position=position,
            stop_price=sl_price,
            sl_pct=sl_pct
        )
        
        # Выставляем тейк-профит
        tp_order = await self._take_profit_placer.place(
            position=position,
            take_price=tp_price
        )
        
        return sl_order, tp_order
    
    async def cancel_order(self, order: Order) -> bool:
        """
        Отмена ордера
        
        Args:
            order: Ордер для отмены
            
        Returns:
            bool: True, если ордер успешно отменен
        """
        logger.info(f"Отмена ордера {order.order_id} ({order.order_purpose})")
        return await self._order_canceller.cancel_order(order)
    
    async def cancel_all_position_orders(self, position_id: int) -> int:
        """
        Отмена всех ордеров для позиции
        
        Args:
            position_id: ID позиции
            
        Returns:
            int: Количество отмененных ордеров
        """
        logger.info(f"Отмена всех ордеров для позиции {position_id}")
        return await self._order_canceller.cancel_position_orders(position_id)
    
    async def cancel_all_account_orders(self, account_id: str) -> int:
        """
        Отмена всех ордеров для аккаунта
        
        Args:
            account_id: ID аккаунта
            
        Returns:
            int: Количество отмененных ордеров
        """
        logger.info(f"Отмена всех ордеров для аккаунта {account_id}")
        return await self._order_canceller.cancel_account_orders(account_id)
