from typing import Optional
import asyncio
from tinkoff.invest import AsyncClient, InstrumentIdType
from tinkoff.invest.exceptions import AioRequestError

from src.utils.logger import get_logger

logger = get_logger("api.client")


class TinkoffAPIClient:
    """
    Обертка над AsyncClient из tinkoff.invest для работы с API
    """
    
    def __init__(self, token: str, app_name: str = "AutoStopSystem"):
        """
        Инициализация клиента API
        
        Args:
            token: Токен доступа к API
            app_name: Название приложения
        """
        self.token = token
        self.app_name = app_name
        self.client: Optional[AsyncClient] = None
        self._retry_count = 3
        self._retry_delay = 1.0  # секунды
        
    async def __aenter__(self):
        """
        Асинхронный контекстный менеджер - вход
        """
        self.client = AsyncClient(token=self.token, app_name=self.app_name)
        self.client = await self.client.__aenter__()
        logger.info("Соединение с Tinkoff Invest API установлено")
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Асинхронный контекстный менеджер - выход
        """
        if self.client:
            # После __aenter__ self.client становится AsyncServices, у которого нет метода __aexit__
            # Просто логируем закрытие соединения
            logger.info("Соединение с Tinkoff Invest API закрыто")
    
    @property
    def services(self):
        """
        Доступ к gRPC сервисам
        
        Returns:
            AsyncServices: Объект сервисов API
        """
        if not self.client:
            raise ValueError("Клиент API не инициализирован")
        return self.client
    
    async def with_retry(self, coro):
        """
        Выполнение запроса с автоматическими повторами при ошибках
        
        Args:
            coro: Корутина для выполнения
            
        Returns:
            Any: Результат выполнения корутины
            
        Raises:
            AioRequestError: Если все попытки завершились ошибкой
        """
        for attempt in range(self._retry_count):
            try:
                return await coro
            except AioRequestError as e:
                if attempt == self._retry_count - 1:
                    logger.error(f"Ошибка API после {self._retry_count} попыток: {e}")
                    raise
                
                delay = self._retry_delay * (2 ** attempt)  # Экспоненциальная задержка
                logger.warning(f"Ошибка API: {e}. Повтор через {delay} сек...")
                await asyncio.sleep(delay)
    
    async def get_instrument_by_ticker(self, ticker: str, class_code: str = "TQBR"):
        """
        Получение информации об инструменте по тикеру
        
        Args:
            ticker: Тикер инструмента
            class_code: Код класса инструмента (по умолчанию TQBR - акции МосБиржи)
            
        Returns:
            Instrument: Информация об инструменте
        """
        response = await self.with_retry(
            self.services.instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_TICKER,
                class_code=class_code,
                id=ticker
            )
        )
        return response.instrument
    
    async def get_instrument_by_figi(self, figi: str):
        """
        Получение информации об инструменте по FIGI
        
        Args:
            figi: FIGI инструмента
            
        Returns:
            Instrument: Информация об инструменте
        """
        response = await self.with_retry(
            self.services.instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI,
                id=figi
            )
        )
        return response.instrument
    
    async def get_accounts(self):
        """
        Получение списка счетов пользователя
        
        Returns:
            List[Account]: Список счетов
        """
        response = await self.with_retry(
            self.services.users.get_accounts()
        )
        return response.accounts
    
    async def get_positions(self, account_id: str):
        """
        Получение текущих позиций по счету
        
        Args:
            account_id: ID счета
            
        Returns:
            PositionsResponse: Информация о позициях
        """
        response = await self.with_retry(
            self.services.operations.get_positions(account_id=account_id)
        )
        return response
    
    async def get_portfolio(self, account_id: str):
        """
        Получение портфеля по счету
        
        Args:
            account_id: ID счета
            
        Returns:
            PortfolioResponse: Информация о портфеле
        """
        response = await self.with_retry(
            self.services.operations.get_portfolio(account_id=account_id)
        )
        return response
