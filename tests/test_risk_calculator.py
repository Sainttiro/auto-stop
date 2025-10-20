import unittest
import asyncio
from decimal import Decimal

from src.core.risk_calculator import RiskCalculator
from src.api.instrument_info import InstrumentInfoCache
from src.config.settings import DefaultSettings, StockSettings, FuturesSettings


class MockInstrumentCache:
    """
    Мок для InstrumentInfoCache для тестирования
    """
    
    async def get_price_step(self, figi: str):
        """
        Возвращает фиксированные значения для тестирования
        """
        if figi == "stock_figi":
            return Decimal("0.01"), Decimal("0.01")  # Шаг цены и стоимость шага для акций
        elif figi == "futures_figi":
            return Decimal("10"), Decimal("12.5")  # Шаг цены и стоимость шага для фьючерсов
        elif figi == "futures_pct_figi":
            return Decimal("10"), Decimal("12.5")  # Для тестирования процентного подхода
        else:
            return Decimal("0.01"), Decimal("0.01")


class TestRiskCalculator(unittest.TestCase):
    """
    Тесты для RiskCalculator
    """
    
    def setUp(self):
        """
        Настройка тестового окружения
        """
        # Создаем настройки по умолчанию
        stock_settings = StockSettings(stop_loss_pct=2.0, take_profit_pct=5.0)
        futures_settings = FuturesSettings(
            stop_loss_steps=10, 
            take_profit_steps=30,
            stop_loss_pct=2.0,
            take_profit_pct=5.0
        )
        self.default_settings = DefaultSettings(stocks=stock_settings, futures=futures_settings)
        
        # Создаем мок для кэша инструментов
        self.instrument_cache = MockInstrumentCache()
        
        # Создаем тестируемый объект
        self.risk_calculator = RiskCalculator(
            default_settings=self.default_settings,
            instrument_cache=self.instrument_cache
        )
    
    def test_calculate_stock_levels_long(self):
        """
        Тест расчета уровней для акций в лонг позиции
        """
        # Параметры
        figi = "stock_figi"
        ticker = "AAPL"
        instrument_type = "stock"
        avg_price = Decimal("150.00")
        direction = "LONG"
        
        # Запускаем асинхронный метод в синхронном контексте
        loop = asyncio.get_event_loop()
        sl_price, tp_price = loop.run_until_complete(
            self.risk_calculator.calculate_levels(
                figi=figi,
                ticker=ticker,
                instrument_type=instrument_type,
                avg_price=avg_price,
                direction=direction
            )
        )
        
        # Проверяем результаты
        # SL = 150 * (1 - 2/100) = 147
        # TP = 150 * (1 + 5/100) = 157.5
        self.assertEqual(sl_price, Decimal("147.00"))
        self.assertEqual(tp_price, Decimal("157.50"))
    
    def test_calculate_stock_levels_short(self):
        """
        Тест расчета уровней для акций в шорт позиции
        """
        # Параметры
        figi = "stock_figi"
        ticker = "AAPL"
        instrument_type = "stock"
        avg_price = Decimal("150.00")
        direction = "SHORT"
        
        # Запускаем асинхронный метод в синхронном контексте
        loop = asyncio.get_event_loop()
        sl_price, tp_price = loop.run_until_complete(
            self.risk_calculator.calculate_levels(
                figi=figi,
                ticker=ticker,
                instrument_type=instrument_type,
                avg_price=avg_price,
                direction=direction
            )
        )
        
        # Проверяем результаты
        # SL = 150 * (1 + 2/100) = 153
        # TP = 150 * (1 - 5/100) = 142.5
        self.assertEqual(sl_price, Decimal("153.00"))
        self.assertEqual(tp_price, Decimal("142.50"))
    
    def test_calculate_futures_levels_long(self):
        """
        Тест расчета уровней для фьючерсов в лонг позиции
        """
        # Параметры
        figi = "futures_figi"
        ticker = "SiH5"
        instrument_type = "futures"
        avg_price = Decimal("100000.00")  # 100,000 руб
        direction = "LONG"
        
        # Запускаем асинхронный метод в синхронном контексте
        loop = asyncio.get_event_loop()
        sl_price, tp_price = loop.run_until_complete(
            self.risk_calculator.calculate_levels(
                figi=figi,
                ticker=ticker,
                instrument_type=instrument_type,
                avg_price=avg_price,
                direction=direction
            )
        )
        
        # Проверяем результаты
        # SL = 100000 - (10 * 10) = 99900
        # TP = 100000 + (30 * 10) = 100300
        self.assertEqual(sl_price, Decimal("99900.00"))
        self.assertEqual(tp_price, Decimal("100300.00"))
    
    def test_calculate_futures_levels_short(self):
        """
        Тест расчета уровней для фьючерсов в шорт позиции (с использованием шагов)
        """
        # Параметры
        figi = "futures_figi"
        ticker = "SiH5"
        instrument_type = "futures"
        avg_price = Decimal("100000.00")  # 100,000 руб
        direction = "SHORT"
        
        # Запускаем асинхронный метод в синхронном контексте
        loop = asyncio.get_event_loop()
        sl_price, tp_price = loop.run_until_complete(
            self.risk_calculator.calculate_levels(
                figi=figi,
                ticker=ticker,
                instrument_type=instrument_type,
                avg_price=avg_price,
                direction=direction
            )
        )
        
        # Проверяем результаты
        # SL = 100000 + (10 * 10) = 100100
        # TP = 100000 - (30 * 10) = 99700
        self.assertEqual(sl_price, Decimal("100100.00"))
        self.assertEqual(tp_price, Decimal("99700.00"))
    
    def test_calculate_futures_levels_long_with_pct(self):
        """
        Тест расчета уровней для фьючерсов в лонг позиции (с использованием процентов)
        """
        # Параметры
        figi = "futures_pct_figi"
        ticker = "RIH5"
        instrument_type = "futures"
        avg_price = Decimal("100000.00")  # 100,000 руб
        direction = "LONG"
        
        # Создаем настройки инструмента с процентными значениями
        instrument_settings = InstrumentSettings(
            type="futures",
            stop_loss_pct=1.5,
            take_profit_pct=3.0
        )
        
        # Запускаем асинхронный метод в синхронном контексте
        loop = asyncio.get_event_loop()
        sl_price, tp_price = loop.run_until_complete(
            self.risk_calculator.calculate_levels(
                figi=figi,
                ticker=ticker,
                instrument_type=instrument_type,
                avg_price=avg_price,
                direction=direction,
                instrument_settings=instrument_settings
            )
        )
        
        # Проверяем результаты
        # SL = 100000 * (1 - 1.5/100) = 98500
        # TP = 100000 * (1 + 3.0/100) = 103000
        self.assertEqual(sl_price, Decimal("98500.00"))
        self.assertEqual(tp_price, Decimal("103000.00"))
    
    def test_calculate_futures_levels_short_with_pct(self):
        """
        Тест расчета уровней для фьючерсов в шорт позиции (с использованием процентов)
        """
        # Параметры
        figi = "futures_pct_figi"
        ticker = "RIH5"
        instrument_type = "futures"
        avg_price = Decimal("100000.00")  # 100,000 руб
        direction = "SHORT"
        
        # Создаем настройки инструмента с процентными значениями
        instrument_settings = InstrumentSettings(
            type="futures",
            stop_loss_pct=1.5,
            take_profit_pct=3.0
        )
        
        # Запускаем асинхронный метод в синхронном контексте
        loop = asyncio.get_event_loop()
        sl_price, tp_price = loop.run_until_complete(
            self.risk_calculator.calculate_levels(
                figi=figi,
                ticker=ticker,
                instrument_type=instrument_type,
                avg_price=avg_price,
                direction=direction,
                instrument_settings=instrument_settings
            )
        )
        
        # Проверяем результаты
        # SL = 100000 * (1 + 1.5/100) = 101500
        # TP = 100000 * (1 - 3.0/100) = 97000
        self.assertEqual(sl_price, Decimal("101500.00"))
        self.assertEqual(tp_price, Decimal("97000.00"))
    
    def test_calculate_multi_tp_levels(self):
        """
        Тест расчета уровней для многоуровневого тейк-профита
        """
        # Параметры
        figi = "stock_figi"
        ticker = "AAPL"
        instrument_type = "stock"
        avg_price = Decimal("150.00")
        direction = "LONG"
        levels = [(1.0, 25.0), (2.0, 25.0), (3.0, 50.0)]  # (процент, объем в процентах)
        
        # Запускаем асинхронный метод в синхронном контексте
        loop = asyncio.get_event_loop()
        tp_levels = loop.run_until_complete(
            self.risk_calculator.calculate_multi_tp_levels(
                figi=figi,
                ticker=ticker,
                instrument_type=instrument_type,
                avg_price=avg_price,
                direction=direction,
                levels=levels
            )
        )
        
        # Проверяем результаты
        # TP1 = 150 * (1 + 1/100) = 151.5
        # TP2 = 150 * (1 + 2/100) = 153
        # TP3 = 150 * (1 + 3/100) = 154.5
        self.assertEqual(len(tp_levels), 3)
        self.assertEqual(tp_levels[0][0], Decimal("151.50"))
        self.assertEqual(tp_levels[0][1], 25.0)
        self.assertEqual(tp_levels[1][0], Decimal("153.00"))
        self.assertEqual(tp_levels[1][1], 25.0)
        self.assertEqual(tp_levels[2][0], Decimal("154.50"))
        self.assertEqual(tp_levels[2][1], 50.0)


if __name__ == "__main__":
    unittest.main()
