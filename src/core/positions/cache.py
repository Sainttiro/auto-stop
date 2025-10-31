"""
Управление кэшем позиций в памяти
"""
from typing import Dict, Optional
import asyncio

from src.storage.models import Position
from src.storage.database import Database
from src.utils.logger import get_logger

logger = get_logger("core.positions.cache")


class PositionCache:
    """
    Управление кэшем позиций в памяти
    
    Обеспечивает быстрый доступ к позициям по FIGI и синхронизацию с БД
    """
    
    def __init__(self, database: Database):
        """
        Инициализация кэша позиций
        
        Args:
            database: Объект для работы с базой данных
        """
        self.db = database
        self._lock = asyncio.Lock()
        self._positions_cache: Dict[str, Dict[str, Position]] = {}  # account_id -> {figi -> Position}
    
    async def initialize(self):
        """
        Инициализация кэша - загрузка позиций из БД
        """
        async with self._lock:
            positions = await self.db.get_all(Position)
            
            for position in positions:
                account_id = position.account_id
                figi = position.figi
                
                if account_id not in self._positions_cache:
                    self._positions_cache[account_id] = {}
                    
                self._positions_cache[account_id][figi] = position
                
            logger.info(f"Загружено {len(positions)} позиций в кэш из базы данных")
    
    def clear(self):
        """
        Очистка кэша позиций
        
        Используется после очистки БД для синхронизации состояния кэша
        """
        self._positions_cache.clear()
        logger.info("Кэш позиций очищен")
    
    async def get(self, account_id: str, figi: str) -> Optional[Position]:
        """
        Получение позиции из кэша или БД
        
        Args:
            account_id: ID счета
            figi: FIGI инструмента
            
        Returns:
            Optional[Position]: Найденная позиция или None
        """
        # Проверяем кэш
        if account_id in self._positions_cache and figi in self._positions_cache[account_id]:
            return self._positions_cache[account_id][figi]
        
        # Если нет в кэше, запрашиваем из БД
        position = await self.db.get_position_by_figi(account_id, figi)
        
        # Обновляем кэш, если позиция найдена
        if position:
            await self.add(position)
            
        return position
    
    async def add(self, position: Position):
        """
        Добавление позиции в кэш
        
        Args:
            position: Объект позиции
        """
        async with self._lock:
            account_id = position.account_id
            figi = position.figi
            
            if account_id not in self._positions_cache:
                self._positions_cache[account_id] = {}
                
            self._positions_cache[account_id][figi] = position
            
            logger.debug(f"Позиция {position.ticker} ({figi}) добавлена в кэш")
    
    async def update(self, position: Position):
        """
        Обновление позиции в кэше
        
        Args:
            position: Обновленный объект позиции
        """
        await self.add(position)
    
    async def remove(self, account_id: str, figi: str):
        """
        Удаление позиции из кэша
        
        Args:
            account_id: ID счета
            figi: FIGI инструмента
        """
        async with self._lock:
            if account_id in self._positions_cache and figi in self._positions_cache[account_id]:
                position = self._positions_cache[account_id][figi]
                del self._positions_cache[account_id][figi]
                logger.debug(f"Позиция {position.ticker} ({figi}) удалена из кэша")
    
    async def get_all_for_account(self, account_id: str) -> Dict[str, Position]:
        """
        Получение всех позиций для аккаунта
        
        Args:
            account_id: ID счета
            
        Returns:
            Dict[str, Position]: Словарь позиций {figi -> Position}
        """
        if account_id in self._positions_cache:
            return self._positions_cache[account_id].copy()
        return {}
    
    async def get_all(self) -> Dict[str, Dict[str, Position]]:
        """
        Получение всех позиций
        
        Returns:
            Dict[str, Dict[str, Position]]: Словарь позиций {account_id -> {figi -> Position}}
        """
        return self._positions_cache.copy()
