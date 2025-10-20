import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Type, TypeVar, Generic
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from sqlalchemy import update, delete

from src.storage.models import Base, Position, Order, Trade, MultiTakeProfitLevel, SystemEvent, Setting
from src.utils.logger import get_logger

logger = get_logger("storage.database")

T = TypeVar('T')


class Database:
    """
    Класс для работы с базой данных SQLite
    """
    
    def __init__(self, db_path: str = "data/trading.db"):
        """
        Инициализация базы данных
        
        Args:
            db_path: Путь к файлу базы данных
        """
        # Создаем директорию для базы данных, если она не существует
        db_dir = Path(db_path).parent
        os.makedirs(db_dir, exist_ok=True)
        
        # Создаем URL для подключения к базе данных
        self.db_url = f"sqlite+aiosqlite:///{db_path}"
        
        # Создаем асинхронный движок SQLAlchemy
        self.engine: AsyncEngine = create_async_engine(
            self.db_url,
            echo=False,  # Отключаем вывод SQL-запросов в консоль
            future=True  # Используем новый API SQLAlchemy
        )
        
        # Создаем фабрику сессий
        self.async_session = sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
        
        # Блокировка для синхронизации доступа к базе данных
        self._lock = asyncio.Lock()
        
        logger.info(f"База данных инициализирована: {db_path}")
    
    async def create_tables(self):
        """
        Создание таблиц в базе данных
        """
        async with self._lock:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Таблицы в базе данных созданы")
    
    def get_session(self) -> AsyncSession:
        """
        Получение сессии для работы с базой данных
        
        Returns:
            AsyncSession: Асинхронная сессия SQLAlchemy
        """
        return self.async_session()
    
    async def add(self, obj: Any):
        """
        Добавление объекта в базу данных
        
        Args:
            obj: Объект для добавления
        """
        async with self._lock:
            async with self.get_session() as session:
                session.add(obj)
                await session.commit()
    
    async def add_all(self, objects: List[Any]):
        """
        Добавление списка объектов в базу данных
        
        Args:
            objects: Список объектов для добавления
        """
        if not objects:
            return
            
        async with self._lock:
            async with self.get_session() as session:
                session.add_all(objects)
                await session.commit()
    
    async def get_by_id(self, model: Type[T], id: int) -> Optional[T]:
        """
        Получение объекта по ID
        
        Args:
            model: Класс модели
            id: ID объекта
            
        Returns:
            Optional[T]: Найденный объект или None
        """
        async with self.get_session() as session:
            result = await session.get(model, id)
            return result
    
    async def get_all(self, model: Type[T]) -> List[T]:
        """
        Получение всех объектов модели
        
        Args:
            model: Класс модели
            
        Returns:
            List[T]: Список объектов
        """
        async with self.get_session() as session:
            result = await session.execute(select(model))
            return result.scalars().all()
    
    async def update(self, model: Type[T], id: int, values: Dict[str, Any]) -> bool:
        """
        Обновление объекта по ID
        
        Args:
            model: Класс модели
            id: ID объекта
            values: Словарь с новыми значениями полей
            
        Returns:
            bool: True, если объект был обновлен
        """
        async with self._lock:
            async with self.get_session() as session:
                stmt = update(model).where(model.id == id).values(**values)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
    
    async def delete(self, model: Type[T], id: int) -> bool:
        """
        Удаление объекта по ID
        
        Args:
            model: Класс модели
            id: ID объекта
            
        Returns:
            bool: True, если объект был удален
        """
        async with self._lock:
            async with self.get_session() as session:
                stmt = delete(model).where(model.id == id)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
    
    async def execute(self, statement):
        """
        Выполнение произвольного SQL-запроса
        
        Args:
            statement: SQL-запрос
            
        Returns:
            Any: Результат выполнения запроса
        """
        async with self.get_session() as session:
            result = await session.execute(statement)
            return result
    
    async def execute_and_commit(self, statement):
        """
        Выполнение произвольного SQL-запроса с коммитом
        
        Args:
            statement: SQL-запрос
            
        Returns:
            Any: Результат выполнения запроса
        """
        async with self._lock:
            async with self.get_session() as session:
                result = await session.execute(statement)
                await session.commit()
                return result
    
    # Специализированные методы для работы с позициями
    
    async def get_position_by_figi(self, account_id: str, figi: str) -> Optional[Position]:
        """
        Получение позиции по FIGI и ID счета
        
        Args:
            account_id: ID счета
            figi: FIGI инструмента
            
        Returns:
            Optional[Position]: Найденная позиция или None
        """
        async with self.get_session() as session:
            stmt = select(Position).where(
                Position.account_id == account_id,
                Position.figi == figi
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    async def get_active_orders_by_position(self, position_id: int) -> List[Order]:
        """
        Получение активных ордеров для позиции
        
        Args:
            position_id: ID позиции
            
        Returns:
            List[Order]: Список активных ордеров
        """
        async with self.get_session() as session:
            stmt = select(Order).where(
                Order.position_id == position_id,
                Order.status.in_(["NEW", "PARTIALLY_FILLED"])
            )
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def get_order_by_order_id(self, order_id: str) -> Optional[Order]:
        """
        Получение ордера по ID ордера
        
        Args:
            order_id: ID ордера
            
        Returns:
            Optional[Order]: Найденный ордер или None
        """
        async with self.get_session() as session:
            stmt = select(Order).where(Order.order_id == order_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    async def get_multi_tp_levels_by_position(self, position_id: int) -> List[MultiTakeProfitLevel]:
        """
        Получение уровней многоуровневого тейк-профита для позиции
        
        Args:
            position_id: ID позиции
            
        Returns:
            List[MultiTakeProfitLevel]: Список уровней
        """
        async with self.get_session() as session:
            stmt = select(MultiTakeProfitLevel).where(
                MultiTakeProfitLevel.position_id == position_id
            ).order_by(MultiTakeProfitLevel.level_number)
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def clear_all_positions(self):
        """
        Очистка всех позиций и связанных данных из базы данных
        
        Удаляет:
        - Все позиции
        - Все ордера
        - Все уровни многоуровневого тейк-профита
        """
        async with self._lock:
            async with self.get_session() as session:
                # Удаляем уровни многоуровневого тейк-профита
                await session.execute(delete(MultiTakeProfitLevel))
                
                # Удаляем ордера
                await session.execute(delete(Order))
                
                # Удаляем позиции
                await session.execute(delete(Position))
                
                await session.commit()
                
        logger.info("Все позиции и связанные данные очищены из базы данных")
    
    async def log_event(self, event_type: str, account_id: Optional[str] = None,
                       figi: Optional[str] = None, ticker: Optional[str] = None,
                       description: Optional[str] = None, details: Optional[Dict] = None):
        """
        Логирование системного события
        
        Args:
            event_type: Тип события
            account_id: ID счета
            figi: FIGI инструмента
            ticker: Тикер инструмента
            description: Описание события
            details: Детали события в виде словаря
        """
        event = SystemEvent(
            event_type=event_type,
            account_id=account_id,
            figi=figi,
            ticker=ticker,
            description=description,
            details=json.dumps(details) if details else None
        )
        await self.add(event)
        logger.info(f"Событие {event_type} зарегистрировано: {description}")
    
    # Методы для Telegram Bot
    
    async def get_open_positions(self) -> List[Position]:
        """
        Получение всех открытых позиций
        
        Returns:
            List[Position]: Список открытых позиций
        """
        async with self.get_session() as session:
            stmt = select(Position).where(Position.quantity > 0)
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def get_total_trades_count(self) -> int:
        """
        Получение общего количества сделок
        
        Returns:
            int: Количество сделок
        """
        async with self.get_session() as session:
            stmt = select(Trade)
            result = await session.execute(stmt)
            return len(result.scalars().all())
    
    async def get_recent_events(self, limit: int = 10) -> List[SystemEvent]:
        """
        Получение последних системных событий
        
        Args:
            limit: Максимальное количество событий
            
        Returns:
            List[SystemEvent]: Список событий
        """
        async with self.get_session() as session:
            stmt = select(SystemEvent).order_by(
                SystemEvent.created_at.desc()
            ).limit(limit)
            result = await session.execute(stmt)
            return result.scalars().all()
    
    # Методы для работы с настройками
    
    async def get_setting(self, key: str) -> Optional[str]:
        """
        Получение значения настройки по ключу
        
        Args:
            key: Ключ настройки
            
        Returns:
            Optional[str]: Значение настройки или None
        """
        async with self.get_session() as session:
            stmt = select(Setting).where(Setting.key == key)
            result = await session.execute(stmt)
            setting = result.scalar_one_or_none()
            return setting.value if setting else None
    
    async def set_setting(self, key: str, value: str, description: Optional[str] = None):
        """
        Установка значения настройки
        
        Args:
            key: Ключ настройки
            value: Значение настройки
            description: Описание настройки
        """
        async with self._lock:
            async with self.get_session() as session:
                # Проверяем, существует ли настройка
                stmt = select(Setting).where(Setting.key == key)
                result = await session.execute(stmt)
                setting = result.scalar_one_or_none()
                
                if setting:
                    # Обновляем существующую настройку
                    setting.value = value
                    if description:
                        setting.description = description
                else:
                    # Создаем новую настройку
                    setting = Setting(
                        key=key,
                        value=value,
                        description=description
                    )
                    session.add(setting)
                
                await session.commit()
                logger.info(f"Настройка {key} обновлена")
