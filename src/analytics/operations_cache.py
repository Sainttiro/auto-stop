"""
Модуль для кэширования операций в базе данных
"""

from typing import List, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_, delete
from sqlalchemy.future import select

from src.storage.database import Database
from src.storage.models import OperationCache
from src.analytics.operations_fetcher import OperationsFetcher
from src.utils.logger import get_logger

logger = get_logger("analytics.operations_cache")


class OperationsCache:
    """
    Класс для управления кэшем операций
    """
    
    def __init__(self, database: Database, fetcher: OperationsFetcher):
        """
        Инициализация
        
        Args:
            database: Объект базы данных
            fetcher: Объект для получения операций из API
        """
        self.db = database
        self.fetcher = fetcher
    
    async def get_operations(
        self,
        account_id: str,
        from_date: datetime,
        to_date: datetime
    ) -> List[OperationCache]:
        """
        Получение операций с умным кэшированием
        
        Логика:
        1. Операции до вчерашнего дня - из кэша
        2. Пропущенные дни - запрос из API + кэширование
        3. Сегодняшний день - всегда из API (не кэшируется)
        
        Args:
            account_id: ID счета
            from_date: Начало периода
            to_date: Конец периода
            
        Returns:
            List[OperationCache]: Список операций
        """
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        
        logger.info(
            f"Получение операций для {account_id} "
            f"с {from_date.date()} по {to_date.date()}"
        )
        
        all_operations = []
        
        # 1. Получить кэшированные операции (до вчерашнего дня включительно)
        cache_to_date = min(to_date, yesterday + timedelta(days=1) - timedelta(microseconds=1))
        
        if from_date < today:
            logger.debug("Получение кэшированных операций...")
            cached_ops = await self._get_cached_operations(
                account_id,
                from_date,
                cache_to_date
            )
            all_operations.extend(cached_ops)
            logger.info(f"Получено из кэша: {len(cached_ops)} операций")
        
        # 2. Проверить пропущенные дни и запросить из API
        if from_date < today:
            last_cached_date = await self._get_last_cached_date(account_id)
            
            if last_cached_date:
                # Есть кэш - проверяем пропущенные дни
                gap_start = last_cached_date + timedelta(days=1)
                gap_end = yesterday
                
                if gap_start <= gap_end:
                    logger.info(
                        f"Обнаружены пропущенные дни: "
                        f"{gap_start.date()} - {gap_end.date()}"
                    )
                    
                    # Запросить пропущенные дни
                    gap_ops = await self.fetcher.fetch_operations(
                        account_id,
                        gap_start,
                        gap_end + timedelta(days=1) - timedelta(microseconds=1)
                    )
                    
                    # Кэшировать
                    if gap_ops:
                        await self._cache_operations(account_id, gap_ops)
                        logger.info(f"Закэшировано пропущенных операций: {len(gap_ops)}")
                        
                        # Добавить к результату
                        for op_dict in gap_ops:
                            op = self._dict_to_model(account_id, op_dict)
                            all_operations.append(op)
            else:
                # Кэша нет - запросить весь период до вчера
                logger.info("Кэш пуст, запрашиваем весь период до вчера...")
                
                hist_ops = await self.fetcher.fetch_operations(
                    account_id,
                    from_date,
                    cache_to_date
                )
                
                # Кэшировать
                if hist_ops:
                    await self._cache_operations(account_id, hist_ops)
                    logger.info(f"Закэшировано операций: {len(hist_ops)}")
                    
                    # Добавить к результату (если еще не добавлены из кэша)
                    if not cached_ops:
                        for op_dict in hist_ops:
                            op = self._dict_to_model(account_id, op_dict)
                            all_operations.append(op)
        
        # 3. Запросить сегодняшний день (не кэшировать)
        if to_date >= today:
            logger.debug("Запрос операций за сегодня...")
            today_ops = await self.fetcher.fetch_operations(
                account_id,
                today,
                to_date
            )
            
            logger.info(f"Получено операций за сегодня: {len(today_ops)}")
            
            # Добавить к результату
            for op_dict in today_ops:
                op = self._dict_to_model(account_id, op_dict)
                all_operations.append(op)
        
        logger.info(f"Всего операций: {len(all_operations)}")
        return all_operations
    
    async def _get_cached_operations(
        self,
        account_id: str,
        from_date: datetime,
        to_date: datetime
    ) -> List[OperationCache]:
        """
        Получение операций из кэша
        
        Args:
            account_id: ID счета
            from_date: Начало периода
            to_date: Конец периода
            
        Returns:
            List[OperationCache]: Список операций из кэша
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(OperationCache).where(
                    and_(
                        OperationCache.account_id == account_id,
                        OperationCache.date >= from_date,
                        OperationCache.date <= to_date
                    )
                ).order_by(OperationCache.date)
            )
            return result.scalars().all()
    
    async def _get_last_cached_date(self, account_id: str) -> Optional[datetime]:
        """
        Получение даты последней закэшированной операции
        
        Args:
            account_id: ID счета
            
        Returns:
            Optional[datetime]: Дата последней операции или None
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(OperationCache.date)
                .where(OperationCache.account_id == account_id)
                .order_by(OperationCache.date.desc())
                .limit(1)
            )
            last_date = result.scalar()
            
            if last_date:
                # Возвращаем дату без времени
                return last_date.replace(hour=0, minute=0, second=0, microsecond=0)
            
            return None
    
    async def _cache_operations(self, account_id: str, operations: List[dict]):
        """
        Кэширование операций в БД
        
        Args:
            account_id: ID счета
            operations: Список операций для кэширования
        """
        if not operations:
            return
        
        async with self.db.get_session() as session:
            for op_dict in operations:
                # Проверка существования
                existing = await session.execute(
                    select(OperationCache).where(
                        OperationCache.operation_id == op_dict['operation_id']
                    )
                )
                
                if existing.scalar():
                    continue  # Уже есть в кэше
                
                # Создание записи
                op = OperationCache(
                    operation_id=op_dict['operation_id'],
                    account_id=account_id,
                    date=op_dict['date'],
                    type=op_dict['type'],
                    state=op_dict['state'],
                    instrument_uid=op_dict.get('instrument_uid'),
                    ticker=op_dict.get('ticker'),
                    figi=op_dict.get('figi'),
                    instrument_type=op_dict.get('instrument_type'),
                    quantity=op_dict.get('quantity'),
                    price=op_dict.get('price'),
                    payment=op_dict.get('payment'),
                    commission=op_dict.get('commission'),
                    yield_value=op_dict.get('yield_value'),
                    currency=op_dict.get('currency')
                )
                
                session.add(op)
            
            await session.commit()
    
    def _dict_to_model(self, account_id: str, op_dict: dict) -> OperationCache:
        """
        Конвертация словаря в модель OperationCache
        
        Args:
            account_id: ID счета
            op_dict: Словарь с данными операции
            
        Returns:
            OperationCache: Модель операции
        """
        return OperationCache(
            operation_id=op_dict['operation_id'],
            account_id=account_id,
            date=op_dict['date'],
            type=op_dict['type'],
            state=op_dict['state'],
            instrument_uid=op_dict.get('instrument_uid'),
            ticker=op_dict.get('ticker'),
            figi=op_dict.get('figi'),
            instrument_type=op_dict.get('instrument_type'),
            quantity=op_dict.get('quantity'),
            price=op_dict.get('price'),
            payment=op_dict.get('payment'),
            commission=op_dict.get('commission'),
            yield_value=op_dict.get('yield_value'),
            currency=op_dict.get('currency')
        )
    
    async def clear_cache(self, account_id: Optional[str] = None):
        """
        Очистка кэша операций
        
        Args:
            account_id: ID счета (если None - очистить весь кэш)
        """
        async with self.db.get_session() as session:
            if account_id:
                await session.execute(
                    delete(OperationCache).where(
                        OperationCache.account_id == account_id
                    )
                )
            else:
                await session.execute(delete(OperationCache))
            
            await session.commit()
        
        logger.info(f"Кэш операций очищен для {account_id if account_id else 'всех счетов'}")
