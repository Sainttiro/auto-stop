from typing import Dict, Tuple, Optional, List
from decimal import Decimal

from src.config.settings import InstrumentSettings, DefaultSettings
from src.config.settings_manager import SettingsManager
from src.api.instrument_info import InstrumentInfoCache
from src.utils.converters import round_to_step
from src.utils.logger import get_logger

logger = get_logger("core.risk_calculator")


class RiskCalculator:
    """
    Расчет уровней стоп-лосса и тейк-профита
    """
    
    def __init__(
        self, 
        default_settings: DefaultSettings, 
        instrument_cache: InstrumentInfoCache,
        settings_manager: Optional[SettingsManager] = None
    ):
        """
        Инициализация калькулятора рисков
        
        Args:
            default_settings: Настройки по умолчанию (fallback)
            instrument_cache: Кэш информации об инструментах
            settings_manager: Менеджер настроек из БД (опционально)
        """
        self.default_settings = default_settings
        self.instrument_cache = instrument_cache
        self.settings_manager = settings_manager
    
    async def calculate_levels(
        self,
        figi: str,
        ticker: str,
        instrument_type: str,
        avg_price: Decimal,
        direction: str,
        instrument_settings: Optional[InstrumentSettings] = None,
        account_id: Optional[str] = None
    ) -> Tuple[Decimal, Decimal]:
        """
        Расчет уровней стоп-лосса и тейк-профита
        
        Args:
            figi: FIGI инструмента
            ticker: Тикер инструмента
            instrument_type: Тип инструмента ("stock" или "futures")
            avg_price: Средняя цена позиции
            direction: Направление позиции ("LONG" или "SHORT")
            instrument_settings: Индивидуальные настройки инструмента (YAML, deprecated)
            account_id: ID аккаунта для получения настроек из БД
            
        Returns:
            Tuple[Decimal, Decimal]: (стоп-лосс, тейк-профит)
        """
        # Приоритет: БД > YAML > defaults
        effective_settings = None
        
        # Попытка получить настройки из БД
        if self.settings_manager and account_id:
            try:
                db_settings = await self.settings_manager.get_effective_settings(account_id, ticker)
                if db_settings:
                    # Конвертируем в формат InstrumentSettings для совместимости
                    effective_settings = type('Settings', (), {
                        'stop_loss_pct': db_settings.get('stop_loss_pct'),
                        'take_profit_pct': db_settings.get('take_profit_pct'),
                        'stop_loss_steps': None,
                        'take_profit_steps': None
                    })()
                    logger.debug(f"Используются настройки из БД для {ticker}: SL={db_settings.get('stop_loss_pct')}%, TP={db_settings.get('take_profit_pct')}%")
            except Exception as e:
                logger.warning(f"Ошибка при получении настроек из БД для {ticker}: {e}, используем fallback")
        
        # Fallback на YAML настройки
        if effective_settings is None:
            effective_settings = instrument_settings
            if effective_settings:
                logger.debug(f"Используются настройки из YAML для {ticker}")
        
        # Получаем шаг цены инструмента
        min_price_increment, step_price = await self.instrument_cache.get_price_step(figi)
        
        if instrument_type == "stock":
            return await self._calculate_stock_levels(
                ticker=ticker,
                avg_price=avg_price,
                direction=direction,
                min_price_increment=min_price_increment,
                instrument_settings=effective_settings
            )
        elif instrument_type == "futures":
            return await self._calculate_futures_levels(
                ticker=ticker,
                avg_price=avg_price,
                direction=direction,
                min_price_increment=min_price_increment,
                step_price=step_price,
                instrument_settings=effective_settings
            )
        else:
            raise ValueError(f"Неизвестный тип инструмента: {instrument_type}")
    
    async def _calculate_stock_levels(
        self,
        ticker: str,
        avg_price: Decimal,
        direction: str,
        min_price_increment: Decimal,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> Tuple[Decimal, Decimal]:
        """
        Расчет уровней для акций (в процентах от средней цены)
        
        Args:
            ticker: Тикер инструмента
            avg_price: Средняя цена позиции
            direction: Направление позиции ("LONG" или "SHORT")
            min_price_increment: Минимальный шаг цены
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            Tuple[Decimal, Decimal]: (стоп-лосс, тейк-профит)
        """
        # Определяем проценты SL/TP
        if instrument_settings and instrument_settings.stop_loss_pct is not None:
            sl_pct = Decimal(str(instrument_settings.stop_loss_pct))
        else:
            sl_pct = Decimal(str(self.default_settings.stocks.stop_loss_pct))
            
        if instrument_settings and instrument_settings.take_profit_pct is not None:
            tp_pct = Decimal(str(instrument_settings.take_profit_pct))
        else:
            tp_pct = Decimal(str(self.default_settings.stocks.take_profit_pct))
        
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
            f"Рассчитаны уровни для {ticker} (акция): "
            f"SL={sl_price} ({sl_pct}%), TP={tp_price} ({tp_pct}%)"
        )
        
        return sl_price, tp_price
    
    async def _calculate_futures_levels(
        self,
        ticker: str,
        avg_price: Decimal,
        direction: str,
        min_price_increment: Decimal,
        step_price: Decimal,
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> Tuple[Decimal, Decimal]:
        """
        Расчет уровней для фьючерсов (в процентах от средней цены или в шагах цены)
        
        Args:
            ticker: Тикер инструмента
            avg_price: Средняя цена позиции
            direction: Направление позиции ("LONG" или "SHORT")
            min_price_increment: Минимальный шаг цены
            step_price: Стоимость шага цены
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            Tuple[Decimal, Decimal]: (стоп-лосс, тейк-профит)
        """
        # Проверяем, указаны ли процентные значения в настройках инструмента
        use_percentage = False
        sl_pct = None
        tp_pct = None
        
        if instrument_settings:
            if instrument_settings.stop_loss_pct is not None and instrument_settings.take_profit_pct is not None:
                use_percentage = True
                sl_pct = Decimal(str(instrument_settings.stop_loss_pct))
                tp_pct = Decimal(str(instrument_settings.take_profit_pct))
        
        # Если в настройках инструмента не указаны проценты, проверяем настройки по умолчанию
        if not use_percentage:
            if hasattr(self.default_settings.futures, 'stop_loss_pct') and hasattr(self.default_settings.futures, 'take_profit_pct'):
                if self.default_settings.futures.stop_loss_pct is not None and self.default_settings.futures.take_profit_pct is not None:
                    use_percentage = True
                    sl_pct = Decimal(str(self.default_settings.futures.stop_loss_pct))
                    tp_pct = Decimal(str(self.default_settings.futures.take_profit_pct))
        
        # Если используем проценты
        if use_percentage:
            # Рассчитываем уровни в процентах от средней цены (как для акций)
            if direction == "LONG":
                sl_price = avg_price * (1 - sl_pct / 100)
                tp_price = avg_price * (1 + tp_pct / 100)
            else:  # SHORT
                sl_price = avg_price * (1 + sl_pct / 100)
                tp_price = avg_price * (1 - tp_pct / 100)
                
            # Округляем до минимального шага цены
            sl_price = round_to_step(sl_price, min_price_increment)
            tp_price = round_to_step(tp_price, min_price_increment)
            
            # Рассчитываем риск в валюте
            sl_risk = abs(avg_price - sl_price) * step_price / min_price_increment
            tp_profit = abs(avg_price - tp_price) * step_price / min_price_increment
            
            logger.debug(
                f"Рассчитаны уровни для {ticker} (фьючерс, в процентах): "
                f"SL={sl_price} ({sl_pct}%, риск={sl_risk}), "
                f"TP={tp_price} ({tp_pct}%, профит={tp_profit})"
            )
        else:
            # Используем старый подход с шагами цены (для обратной совместимости)
            # Определяем количество шагов для SL/TP
            if instrument_settings and instrument_settings.stop_loss_steps is not None:
                sl_steps = instrument_settings.stop_loss_steps
            else:
                sl_steps = self.default_settings.futures.stop_loss_steps
                
            if instrument_settings and instrument_settings.take_profit_steps is not None:
                tp_steps = instrument_settings.take_profit_steps
            else:
                tp_steps = self.default_settings.futures.take_profit_steps
            
            # Рассчитываем уровни
            if direction == "LONG":
                sl_price = avg_price - (Decimal(sl_steps) * min_price_increment)
                tp_price = avg_price + (Decimal(tp_steps) * min_price_increment)
            else:  # SHORT
                sl_price = avg_price + (Decimal(sl_steps) * min_price_increment)
                tp_price = avg_price - (Decimal(tp_steps) * min_price_increment)
            
            # Округляем до минимального шага цены (для уверенности)
            sl_price = round_to_step(sl_price, min_price_increment)
            tp_price = round_to_step(tp_price, min_price_increment)
            
            # Рассчитываем риск в валюте
            sl_risk = abs(avg_price - sl_price) * step_price / min_price_increment
            tp_profit = abs(avg_price - tp_price) * step_price / min_price_increment
            
            logger.debug(
                f"Рассчитаны уровни для {ticker} (фьючерс, в шагах): "
                f"SL={sl_price} ({sl_steps} шагов, риск={sl_risk}), "
                f"TP={tp_price} ({tp_steps} шагов, профит={tp_profit})"
            )
        
        return sl_price, tp_price
    
    async def calculate_multi_tp_levels(
        self,
        figi: str,
        ticker: str,
        instrument_type: str,
        avg_price: Decimal,
        direction: str,
        levels: List[Tuple[float, float]]
    ) -> List[Tuple[Decimal, float]]:
        """
        Расчет уровней многоуровневого тейк-профита
        
        Args:
            figi: FIGI инструмента
            ticker: Тикер инструмента
            instrument_type: Тип инструмента ("stock" или "futures")
            avg_price: Средняя цена позиции
            direction: Направление позиции ("LONG" или "SHORT")
            levels: Список кортежей (уровень_в_процентах, процент_объема)
            
        Returns:
            List[Tuple[Decimal, float]]: Список кортежей (цена_уровня, процент_объема)
        """
        # Получаем шаг цены инструмента
        min_price_increment, _ = await self.instrument_cache.get_price_step(figi)
        
        result = []
        
        for level_pct, volume_pct in levels:
            # Рассчитываем цену уровня
            if direction == "LONG":
                price_level = avg_price * (1 + Decimal(str(level_pct)) / 100)
            else:  # SHORT
                price_level = avg_price * (1 - Decimal(str(level_pct)) / 100)
            
            # Округляем до минимального шага цены
            price_level = round_to_step(price_level, min_price_increment)
            
            result.append((price_level, volume_pct))
        
        logger.debug(
            f"Рассчитаны уровни многоуровневого TP для {ticker}: "
            f"{[(float(price), vol) for price, vol in result]}"
        )
        
        return result
    
    async def recalculate_on_partial_close(
        self,
        figi: str,
        ticker: str,
        instrument_type: str,
        avg_price: Decimal,
        direction: str,
        remaining_levels: List[Tuple[float, float]],
        instrument_settings: Optional[InstrumentSettings] = None
    ) -> Tuple[Decimal, List[Tuple[Decimal, float]]]:
        """
        Пересчет уровней после частичного закрытия позиции
        
        Args:
            figi: FIGI инструмента
            ticker: Тикер инструмента
            instrument_type: Тип инструмента ("stock" или "futures")
            avg_price: Средняя цена позиции
            direction: Направление позиции ("LONG" или "SHORT")
            remaining_levels: Список оставшихся уровней TP (уровень_в_процентах, процент_объема)
            instrument_settings: Индивидуальные настройки инструмента
            
        Returns:
            Tuple[Decimal, List[Tuple[Decimal, float]]]: (новый_стоп_лосс, новые_уровни_TP)
        """
        # Рассчитываем новый стоп-лосс
        sl_price, _ = await self.calculate_levels(
            figi=figi,
            ticker=ticker,
            instrument_type=instrument_type,
            avg_price=avg_price,
            direction=direction,
            instrument_settings=instrument_settings
        )
        
        # Рассчитываем новые уровни TP
        tp_levels = await self.calculate_multi_tp_levels(
            figi=figi,
            ticker=ticker,
            instrument_type=instrument_type,
            avg_price=avg_price,
            direction=direction,
            levels=remaining_levels
        )
        
        logger.info(
            f"Пересчитаны уровни после частичного закрытия для {ticker}: "
            f"SL={sl_price}, TP={[(float(price), vol) for price, vol in tp_levels]}"
        )
        
        return sl_price, tp_levels
