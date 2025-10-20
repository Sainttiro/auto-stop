from typing import Dict, Optional, Tuple, List
from decimal import Decimal

from src.storage.models import Position, Order, MultiTakeProfitLevel
from src.config.settings import InstrumentSettings, MultiTakeProfitLevel as TPLevelConfig
from src.core.risk_calculator import RiskCalculator
from src.core.order_executor import OrderExecutor
from src.strategies.base import BaseStrategy
from src.utils.logger import get_logger

logger = get_logger("strategies.multi_tp")


class MultiTakeProfitStrategy(BaseStrategy):
    """
    Стратегия управления многоуровневым тейк-профитом
    """
    
    async def process_position(
        self,
        position: Position,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> bool:
        """
        Обработка позиции - расчет и выставление SL и многоуровневых TP
        
        Args:
            position: Позиция
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            bool: True, если ордера успешно выставлены
        """
        try:
            # Получаем среднюю цену
            avg_price = Decimal(str(position.average_price))
            
            # Определяем уровни TP
            tp_levels = []
            
            if instrument_settings and instrument_settings.multi_tp and instrument_settings.multi_tp.enabled:
                # Используем индивидуальные настройки инструмента
                tp_levels = [(level.level_pct, level.volume_pct) for level in instrument_settings.multi_tp.levels]
            else:
                # Если нет индивидуальных настроек, выходим
                logger.warning(f"Для {position.ticker} не настроен многоуровневый TP, пропускаем")
                return False
            
            # Рассчитываем уровни
            sl_price, tp_prices = await self._calculate_multi_tp_levels(
                position=position,
                tp_levels=tp_levels,
                instrument_settings=instrument_settings
            )
            
            # Выставляем ордера
            sl_order, tp_orders = await self.order_executor.place_multi_tp_orders(
                position=position,
                sl_price=sl_price,
                tp_levels=tp_prices
            )
            
            # Проверяем результат
            if sl_order and tp_orders:
                logger.info(
                    f"Выставлены SL и многоуровневый TP для {position.ticker}: "
                    f"SL={sl_price}, TP уровней: {len(tp_orders)}"
                )
                
                # Сохраняем уровни в БД
                await self._save_tp_levels(position.id, tp_levels)
                
                return True
            else:
                logger.error(f"Не удалось выставить SL и многоуровневый TP для {position.ticker}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при обработке позиции {position.ticker} для многоуровневого TP: {e}")
            return False
    
    async def recalculate_levels(
        self,
        position: Position,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> bool:
        """
        Пересчет уровней SL и многоуровневых TP при изменении средней цены
        
        Args:
            position: Позиция
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            bool: True, если ордера успешно перевыставлены
        """
        try:
            # Получаем среднюю цену
            avg_price = Decimal(str(position.average_price))
            
            # Определяем уровни TP
            tp_levels = []
            
            if instrument_settings and instrument_settings.multi_tp and instrument_settings.multi_tp.enabled:
                # Используем индивидуальные настройки инструмента
                tp_levels = [(level.level_pct, level.volume_pct) for level in instrument_settings.multi_tp.levels]
            else:
                # Если нет индивидуальных настроек, выходим
                logger.warning(f"Для {position.ticker} не настроен многоуровневый TP, пропускаем")
                return False
            
            # Рассчитываем уровни
            sl_price, tp_prices = await self._calculate_multi_tp_levels(
                position=position,
                tp_levels=tp_levels,
                instrument_settings=instrument_settings
            )
            
            # Отменяем существующие ордера
            cancelled = await self.order_executor.cancel_all_position_orders(position.id)
            logger.info(f"Отменено {cancelled} ордеров для {position.ticker}")
            
            # Выставляем новые ордера
            sl_order, tp_orders = await self.order_executor.place_multi_tp_orders(
                position=position,
                sl_price=sl_price,
                tp_levels=tp_prices
            )
            
            # Проверяем результат
            if sl_order and tp_orders:
                logger.info(
                    f"Перевыставлены SL и многоуровневый TP для {position.ticker}: "
                    f"SL={sl_price}, TP уровней: {len(tp_orders)}"
                )
                
                # Обновляем уровни в БД
                await self._save_tp_levels(position.id, tp_levels)
                
                return True
            else:
                logger.error(f"Не удалось перевыставить SL и многоуровневый TP для {position.ticker}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при пересчете уровней для {position.ticker} для многоуровневого TP: {e}")
            return False
    
    async def handle_partial_close(
        self,
        position: Position,
        closed_quantity: int,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> bool:
        """
        Обработка частичного закрытия позиции для многоуровневого TP
        
        Args:
            position: Позиция
            closed_quantity: Закрытое количество
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            bool: True, если ордера успешно перевыставлены
        """
        try:
            # Получаем текущие уровни TP из БД
            # Здесь должна быть логика получения уровней из БД и определения,
            # какой уровень сработал и какие остались
            
            # Для простоты просто пересчитываем все уровни
            return await self.recalculate_levels(position, instrument_settings)
                
        except Exception as e:
            logger.error(f"Ошибка при обработке частичного закрытия для {position.ticker} для многоуровневого TP: {e}")
            return False
    
    async def _calculate_multi_tp_levels(
        self,
        position: Position,
        tp_levels: List[Tuple[float, float]],
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> Tuple[Decimal, List[Tuple[Decimal, float]]]:
        """
        Расчет уровней для многоуровневого тейк-профита
        
        Args:
            position: Позиция
            tp_levels: Список кортежей (уровень_в_процентах, процент_объема)
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            Tuple[Decimal, List[Tuple[Decimal, float]]]: (стоп-лосс, список уровней TP)
        """
        # Получаем среднюю цену
        avg_price = Decimal(str(position.average_price))
        
        # Рассчитываем стоп-лосс
        sl_price, _ = await self.risk_calculator.calculate_levels(
            figi=position.figi,
            ticker=position.ticker,
            instrument_type=position.instrument_type,
            avg_price=avg_price,
            direction=position.direction,
            instrument_settings=instrument_settings
        )
        
        # Рассчитываем цены уровней TP
        tp_prices = await self.risk_calculator.calculate_multi_tp_levels(
            figi=position.figi,
            ticker=position.ticker,
            instrument_type=position.instrument_type,
            avg_price=avg_price,
            direction=position.direction,
            levels=tp_levels
        )
        
        return sl_price, tp_prices
    
    async def _save_tp_levels(self, position_id: int, tp_levels: List[Tuple[float, float]]):
        """
        Сохранение уровней TP в БД
        
        Args:
            position_id: ID позиции
            tp_levels: Список кортежей (уровень_в_процентах, процент_объема)
        """
        # Здесь должна быть логика сохранения уровней в БД
        # Для этого нужен доступ к БД, который можно добавить в конструктор класса
        pass
