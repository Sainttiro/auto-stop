from typing import Dict, Optional, Tuple
from decimal import Decimal
import asyncio
from tinkoff.invest import Instrument

from src.api.client import TinkoffAPIClient
from src.utils.logger import get_logger
from src.utils.converters import quotation_to_decimal

logger = get_logger("api.instrument_info")


class InstrumentInfoCache:
    """
    Кэш информации об инструментах
    """
    
    def __init__(self, api_client: TinkoffAPIClient):
        """
        Инициализация кэша
        
        Args:
            api_client: Клиент API Tinkoff
        """
        self.api_client = api_client
        self._cache: Dict[str, Instrument] = {}  # figi -> Instrument
        self._ticker_to_figi: Dict[str, str] = {}  # ticker -> figi
        self._lock = asyncio.Lock()
    
    async def get_instrument_by_figi(self, figi: str) -> Optional[Instrument]:
        """
        Получение информации об инструменте по FIGI
        
        Args:
            figi: FIGI инструмента
            
        Returns:
            Optional[Instrument]: Информация об инструменте или None, если не найден
        """
        # Проверяем кэш
        if figi in self._cache:
            return self._cache[figi]
        
        # Если нет в кэше, запрашиваем через API
        async with self._lock:
            # Повторная проверка после получения блокировки
            if figi in self._cache:
                return self._cache[figi]
            
            try:
                instrument = await self.api_client.get_instrument_by_figi(figi)
                self._cache[figi] = instrument
                self._ticker_to_figi[instrument.ticker] = figi
                logger.debug(f"Получена информация об инструменте {instrument.ticker} ({figi})")
                return instrument
            except Exception as e:
                logger.error(f"Ошибка при получении информации об инструменте {figi}: {e}")
                return None
    
    async def get_instrument_by_ticker(self, ticker: str, class_code: str = "TQBR") -> Optional[Instrument]:
        """
        Получение информации об инструменте по тикеру
        
        Args:
            ticker: Тикер инструмента
            class_code: Код класса инструмента
            
        Returns:
            Optional[Instrument]: Информация об инструменте или None, если не найден
        """
        # Проверяем маппинг тикер -> figi
        if ticker in self._ticker_to_figi:
            figi = self._ticker_to_figi[ticker]
            return await self.get_instrument_by_figi(figi)
        
        # Если нет в кэше, запрашиваем через API
        async with self._lock:
            # Повторная проверка после получения блокировки
            if ticker in self._ticker_to_figi:
                figi = self._ticker_to_figi[ticker]
                return await self.get_instrument_by_figi(figi)
            
            try:
                instrument = await self.api_client.get_instrument_by_ticker(ticker, class_code)
                figi = instrument.figi
                self._cache[figi] = instrument
                self._ticker_to_figi[ticker] = figi
                logger.debug(f"Получена информация об инструменте {ticker} ({figi})")
                return instrument
            except Exception as e:
                logger.error(f"Ошибка при получении информации об инструменте {ticker}: {e}")
                return None
    
    async def get_price_step(self, figi: str) -> Tuple[Decimal, Decimal]:
        """
        Получение минимального шага цены и его стоимости для инструмента
        
        Args:
            figi: FIGI инструмента
            
        Returns:
            Tuple[Decimal, Decimal]: (минимальный шаг цены, стоимость шага)
        """
        instrument = await self.get_instrument_by_figi(figi)
        if not instrument:
            logger.warning(f"Не удалось получить информацию об инструменте {figi}, используем шаг цены 0.01")
            return Decimal("0.01"), Decimal("0.01")
        
        min_price_increment = quotation_to_decimal(instrument.min_price_increment)
        
        # Для фьючерсов получаем стоимость шага цены
        if hasattr(instrument, "min_price_increment_amount") and instrument.min_price_increment_amount:
            step_price = quotation_to_decimal(instrument.min_price_increment_amount)
        else:
            # Для акций стоимость шага равна самому шагу
            step_price = min_price_increment
        
        return min_price_increment, step_price
    
    async def get_ticker_by_figi(self, figi: str) -> str:
        """
        Получение тикера по FIGI
        
        Args:
            figi: FIGI инструмента
            
        Returns:
            str: Тикер инструмента
        """
        instrument = await self.get_instrument_by_figi(figi)
        if not instrument:
            return figi  # Возвращаем FIGI, если не удалось получить тикер
        return instrument.ticker
    
    async def get_lot_size(self, figi: str) -> int:
        """
        Получение размера лота для инструмента
        
        Args:
            figi: FIGI инструмента
            
        Returns:
            int: Размер лота (количество акций в одном лоте)
        """
        instrument = await self.get_instrument_by_figi(figi)
        if not instrument:
            logger.warning(f"Не удалось получить информацию об инструменте {figi}, используем размер лота 1")
            return 1
        
        lot_size = instrument.lot
        logger.debug(f"Размер лота для {instrument.ticker}: {lot_size}")
        return lot_size
    
    def clear_cache(self):
        """
        Очистка кэша
        """
        self._cache.clear()
        self._ticker_to_figi.clear()
        logger.debug("Кэш инструментов очищен")
