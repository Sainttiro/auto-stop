from typing import Optional
from decimal import Decimal

from src.storage.models import Position
from src.config.settings import InstrumentSettings
from src.strategies.base import BaseStrategy
from src.utils.logger import get_logger

logger = get_logger("strategies.futures_sl_tp")


class FuturesStrategy(BaseStrategy):
    """
    Стратегия управления стоп-лоссами и тейк-профитами для фьючерсов
    """
    
    async def process_position(
        self,
        position: Position,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> bool:
        """
        Обработка позиции - расчет и выставление SL/TP для фьючерсов
        
        Args:
            position: Позиция
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            bool: True, если ордера успешно выставлены
        """
        try:
            # Проверяем, что это фьючерс
            if position.instrument_type != "futures":
                logger.warning(f"Позиция {position.ticker} не является фьючерсом, пропускаем")
                return False
            
            # Получаем среднюю цену
            avg_price = Decimal(str(position.average_price))
            
            # Рассчитываем уровни SL/TP
            sl_price, tp_price = await self.risk_calculator.calculate_levels(
                figi=position.figi,
                ticker=position.ticker,
                instrument_type=position.instrument_type,
                avg_price=avg_price,
                direction=position.direction,
                instrument_settings=instrument_settings
            )
            
            # Получаем размер стопа в процентах для расчета цены исполнения
            sl_pct = None
            if instrument_settings and instrument_settings.stop_loss_pct is not None:
                sl_pct = Decimal(str(instrument_settings.stop_loss_pct))
            elif hasattr(self.risk_calculator.default_settings.futures, 'stop_loss_pct') and self.risk_calculator.default_settings.futures.stop_loss_pct is not None:
                sl_pct = Decimal(str(self.risk_calculator.default_settings.futures.stop_loss_pct))
            
            # Выставляем ордера
            sl_order, tp_order = await self.order_executor.place_sl_tp_orders(
                position=position,
                sl_price=sl_price,
                tp_price=tp_price,
                sl_pct=sl_pct
            )
            
            # Проверяем результат
            if sl_order and tp_order:
                logger.info(
                    f"Выставлены SL/TP для фьючерса {position.ticker}: "
                    f"SL={sl_price} ({sl_order.order_id}), "
                    f"TP={tp_price} ({tp_order.order_id})"
                )
                return True
            else:
                logger.error(f"Не удалось выставить SL/TP для фьючерса {position.ticker}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при обработке позиции фьючерса {position.ticker}: {e}")
            return False
    
    async def recalculate_levels(
        self,
        position: Position,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> bool:
        """
        Пересчет уровней SL/TP при изменении средней цены для фьючерсов
        
        Args:
            position: Позиция
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            bool: True, если ордера успешно перевыставлены
        """
        try:
            # Проверяем, что это фьючерс
            if position.instrument_type != "futures":
                logger.warning(f"Позиция {position.ticker} не является фьючерсом, пропускаем")
                return False
            
            # Получаем среднюю цену
            avg_price = Decimal(str(position.average_price))
            
            # Рассчитываем уровни SL/TP
            sl_price, tp_price = await self.risk_calculator.calculate_levels(
                figi=position.figi,
                ticker=position.ticker,
                instrument_type=position.instrument_type,
                avg_price=avg_price,
                direction=position.direction,
                instrument_settings=instrument_settings
            )
            
            # Получаем размер стопа в процентах для расчета цены исполнения
            sl_pct = None
            if instrument_settings and instrument_settings.stop_loss_pct is not None:
                sl_pct = Decimal(str(instrument_settings.stop_loss_pct))
            elif hasattr(self.risk_calculator.default_settings.futures, 'stop_loss_pct') and self.risk_calculator.default_settings.futures.stop_loss_pct is not None:
                sl_pct = Decimal(str(self.risk_calculator.default_settings.futures.stop_loss_pct))
            
            # Отменяем существующие ордера и выставляем новые
            cancelled = await self.order_executor.cancel_all_position_orders(position.id)
            logger.info(f"Отменено {cancelled} ордеров для фьючерса {position.ticker}")
            
            # Выставляем новые ордера
            sl_order, tp_order = await self.order_executor.place_sl_tp_orders(
                position=position,
                sl_price=sl_price,
                tp_price=tp_price,
                sl_pct=sl_pct
            )
            
            # Проверяем результат
            if sl_order and tp_order:
                logger.info(
                    f"Перевыставлены SL/TP для фьючерса {position.ticker}: "
                    f"SL={sl_price} ({sl_order.order_id}), "
                    f"TP={tp_price} ({tp_order.order_id})"
                )
                return True
            else:
                logger.error(f"Не удалось перевыставить SL/TP для фьючерса {position.ticker}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при пересчете уровней для фьючерса {position.ticker}: {e}")
            return False
    
    async def handle_partial_close(
        self,
        position: Position,
        closed_quantity: int,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> bool:
        """
        Обработка частичного закрытия позиции для фьючерсов
        
        Args:
            position: Позиция
            closed_quantity: Закрытое количество
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            bool: True, если ордера успешно перевыставлены
        """
        try:
            # Проверяем, что это фьючерс
            if position.instrument_type != "futures":
                logger.warning(f"Позиция {position.ticker} не является фьючерсом, пропускаем")
                return False
            
            # Для фьючерсов просто пересчитываем уровни с новым количеством
            # Для фьючерсов важно учитывать гарантийное обеспечение, которое меняется
            # пропорционально количеству контрактов
            return await self.recalculate_levels(position, instrument_settings)
                
        except Exception as e:
            logger.error(f"Ошибка при обработке частичного закрытия для фьючерса {position.ticker}: {e}")
            return False
