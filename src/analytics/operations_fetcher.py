"""
Модуль для получения операций из Tinkoff API
"""

from typing import List, Optional
from datetime import datetime, timezone
from tinkoff.invest import OperationType, OperationState, GetOperationsByCursorRequest

from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.utils.logger import get_logger

logger = get_logger("analytics.operations_fetcher")


class OperationsFetcher:
    """
    Класс для получения операций из Tinkoff API
    """
    
    def __init__(self, api_client: TinkoffAPIClient, instrument_cache: Optional[InstrumentInfoCache] = None):
        """
        Инициализация
        
        Args:
            api_client: Клиент API Tinkoff
            instrument_cache: Кэш информации об инструментах (опционально)
        """
        self.api_client = api_client
        self.instrument_cache = instrument_cache
    
    async def fetch_operations(
        self,
        account_id: str,
        from_date: datetime,
        to_date: datetime,
        operation_types: Optional[List[OperationType]] = None
    ) -> List[dict]:
        """
        Получение операций из API с пагинацией
        
        Args:
            account_id: ID счета
            from_date: Начало периода (UTC)
            to_date: Конец периода (UTC)
            operation_types: Типы операций для фильтрации
            
        Returns:
            List[dict]: Список операций
        """
        # По умолчанию получаем только покупки и продажи
        if operation_types is None:
            operation_types = [
                OperationType.OPERATION_TYPE_BUY,
                OperationType.OPERATION_TYPE_SELL,
                OperationType.OPERATION_TYPE_BUY_CARD,
                OperationType.OPERATION_TYPE_SELL_CARD
            ]
        
        operations = []
        cursor = None
        page = 0
        
        logger.info(
            f"Начинаем получение операций для счета {account_id} "
            f"с {from_date.date()} по {to_date.date()}"
        )
        
        try:
            while True:
                page += 1
                logger.debug(f"Запрос страницы {page}, cursor={cursor}")
                
                # Создание запроса
                request = GetOperationsByCursorRequest(
                    account_id=account_id,
                    from_=from_date,
                    to=to_date,
                    cursor=cursor if cursor else "",
                    limit=1000,  # Максимум за запрос
                    operation_types=operation_types,
                    state=OperationState.OPERATION_STATE_EXECUTED,  # Только исполненные
                    without_commissions=False,
                    without_trades=False,
                    without_overnights=True
                )
                
                # Запрос к API
                response = await self.api_client.services.operations.get_operations_by_cursor(
                    request=request
                )
                
                # Обработка операций
                for item in response.items:
                    operation = await self._parse_operation(item)
                    if operation:
                        operations.append(operation)
                
                logger.debug(f"Получено операций на странице {page}: {len(response.items)}")
                
                # Проверка наличия следующей страницы
                if not response.has_next:
                    break
                
                cursor = response.next_cursor
            
            logger.info(f"Всего получено операций: {len(operations)}")
            return operations
            
        except Exception as e:
            logger.error(f"Ошибка при получении операций: {e}")
            raise
    
    async def _parse_operation(self, item) -> Optional[dict]:
        """
        Парсинг операции из ответа API
        
        Args:
            item: Объект OperationItem из API
            
        Returns:
            Optional[dict]: Словарь с данными операции или None
        """
        try:
            # Извлекаем данные
            operation_id = item.id
            date = item.date
            op_type = item.type
            state = item.state
            
            # Инструмент
            instrument_uid = item.instrument_uid if item.instrument_uid else None
            ticker = None
            figi = item.figi if item.figi else None
            instrument_type = item.instrument_type if item.instrument_type else None
            
            # Получаем тикер по FIGI, если доступен кэш инструментов
            if figi and self.instrument_cache:
                try:
                    ticker = await self.instrument_cache.get_ticker_by_figi(figi)
                    logger.debug(f"Получен тикер {ticker} для FIGI {figi}")
                except Exception as e:
                    logger.warning(f"Не удалось получить тикер для FIGI {figi}: {e}")
            
            # Запасной вариант: пытаемся извлечь тикер из названия операции
            if not ticker and item.name:
                # Название обычно в формате "Покупка SBER" или "Продажа GAZP"
                parts = item.name.split()
                if len(parts) >= 2:
                    ticker = parts[-1]
                    logger.debug(f"Извлечен тикер {ticker} из названия операции: {item.name}")
            
            # Количество и цена
            quantity = item.quantity if item.quantity else 0
            price = None
            if item.price:
                price = float(item.price.units) + float(item.price.nano) / 1e9
            
            # Сумма операции
            payment = None
            if item.payment:
                payment = float(item.payment.units) + float(item.payment.nano) / 1e9
            
            # Комиссия
            commission = None
            if item.commission:
                commission = float(item.commission.units) + float(item.commission.nano) / 1e9
            
            # Доходность
            yield_value = None
            if item.yield_:
                yield_value = float(item.yield_.units) + float(item.yield_.nano) / 1e9
            
            # Валюта
            currency = None
            if item.payment and item.payment.currency:
                currency = item.payment.currency
            
            return {
                'operation_id': operation_id,
                'date': date,
                'type': op_type.name if hasattr(op_type, 'name') else str(op_type),
                'state': state.name if hasattr(state, 'name') else str(state),
                'instrument_uid': instrument_uid,
                'ticker': ticker,
                'figi': figi,
                'instrument_type': instrument_type,
                'quantity': quantity,
                'price': price,
                'payment': payment,
                'commission': commission,
                'yield_value': yield_value,
                'currency': currency
            }
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге операции {item.id}: {e}")
            return None
    
    async def fetch_operations_for_period(
        self,
        account_id: str,
        start_year: int = 2025
    ) -> List[dict]:
        """
        Получение всех операций с начала указанного года до текущего момента
        
        Args:
            account_id: ID счета
            start_year: Год начала периода (по умолчанию 2025)
            
        Returns:
            List[dict]: Список операций
        """
        from_date = datetime(start_year, 1, 1, tzinfo=timezone.utc)
        to_date = datetime.now(timezone.utc)
        
        return await self.fetch_operations(account_id, from_date, to_date)
