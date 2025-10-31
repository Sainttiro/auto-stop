from abc import ABC, abstractmethod
from typing import Optional

from src.storage.models import Position
from src.config.settings import InstrumentSettings
from src.core.risk_calculator import RiskCalculator
from src.core.order_executor import OrderExecutor
from src.utils.logger import get_logger

logger = get_logger("strategies.base")


class BaseStrategy(ABC):
    """
    Базовый класс для стратегий управления стоп-лоссами и тейк-профитами
    """
    
    def __init__(
        self,
        risk_calculator: RiskCalculator,
        order_executor: OrderExecutor
    ):
        """
        Инициализация базовой стратегии
        
        Args:
            risk_calculator: Калькулятор рисков
            order_executor: Исполнитель ордеров
        """
        self.risk_calculator = risk_calculator
        self.order_executor = order_executor
    
    @abstractmethod
    async def process_position(
        self,
        position: Position,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> bool:
        """
        Обработка позиции - расчет и выставление SL/TP
        
        Args:
            position: Позиция
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            bool: True, если ордера успешно выставлены
        """
        pass
    
    @abstractmethod
    async def recalculate_levels(
        self,
        position: Position,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> bool:
        """
        Пересчет уровней SL/TP при изменении средней цены
        
        Args:
            position: Позиция
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            bool: True, если ордера успешно перевыставлены
        """
        pass
    
    @abstractmethod
    async def handle_partial_close(
        self,
        position: Position,
        closed_quantity: int,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> bool:
        """
        Обработка частичного закрытия позиции
        
        Args:
            position: Позиция
            closed_quantity: Закрытое количество
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            bool: True, если ордера успешно перевыставлены
        """
        pass
