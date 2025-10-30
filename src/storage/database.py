import os
import json
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any, Type, TypeVar, Generic
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from sqlalchemy import update, delete

from src.storage.models import Base, Position, Order, Trade, MultiTakeProfitLevel, SystemEvent, Setting, Account
from src.utils.logger import get_logger
from datetime import datetime

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
    
    async def get_position_by_ticker(self, account_id: str, ticker: str) -> Optional[Position]:
        """
        Получение позиции по тикеру и ID счета
        
        Args:
            account_id: ID счета
            ticker: Тикер инструмента
            
        Returns:
            Optional[Position]: Найденная позиция или None
        """
        async with self.get_session() as session:
            stmt = select(Position).where(
                Position.account_id == account_id,
                Position.ticker == ticker
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
    
    # Методы для работы с аккаунтами
    
    async def get_all_accounts(self) -> List[Account]:
        """
        Получение всех аккаунтов
        
        Returns:
            List[Account]: Список всех аккаунтов
        """
        async with self.get_session() as session:
            stmt = select(Account).order_by(Account.created_at)
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def get_active_account(self) -> Optional[Account]:
        """
        Получение активного аккаунта
        
        Returns:
            Optional[Account]: Активный аккаунт или None
        """
        async with self.get_session() as session:
            stmt = select(Account).where(Account.is_active == True)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    async def get_account_by_name(self, name: str) -> Optional[Account]:
        """
        Получение аккаунта по имени
        
        Args:
            name: Название аккаунта
            
        Returns:
            Optional[Account]: Найденный аккаунт или None
        """
        async with self.get_session() as session:
            stmt = select(Account).where(Account.name == name)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    async def add_account(self, name: str, token: str, account_id: str, 
                         description: Optional[str] = None) -> Account:
        """
        Добавление нового аккаунта
        
        Args:
            name: Название аккаунта (уникальное)
            token: Токен API
            account_id: ID счета в Tinkoff
            description: Описание аккаунта
            
        Returns:
            Account: Созданный аккаунт
            
        Raises:
            ValueError: Если аккаунт с таким именем уже существует
        """
        async with self._lock:
            async with self.get_session() as session:
                # Проверяем, существует ли аккаунт с таким именем
                stmt = select(Account).where(Account.name == name)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    raise ValueError(f"Аккаунт с именем '{name}' уже существует")
                
                # Создаем новый аккаунт
                account = Account(
                    name=name,
                    token=token,
                    account_id=account_id,
                    description=description,
                    is_active=False  # По умолчанию не активный
                )
                
                session.add(account)
                await session.commit()
                await session.refresh(account)
                
                logger.info(f"Аккаунт '{name}' добавлен (ID: {account_id})")
                return account
    
    async def remove_account(self, name: str) -> bool:
        """
        Удаление аккаунта по имени
        
        Args:
            name: Название аккаунта
            
        Returns:
            bool: True, если аккаунт был удален
            
        Raises:
            ValueError: Если пытаемся удалить активный аккаунт
        """
        async with self._lock:
            async with self.get_session() as session:
                # Получаем аккаунт
                stmt = select(Account).where(Account.name == name)
                result = await session.execute(stmt)
                account = result.scalar_one_or_none()
                
                if not account:
                    logger.warning(f"Аккаунт '{name}' не найден")
                    return False
                
                # Проверяем, не активный ли это аккаунт
                if account.is_active:
                    raise ValueError(f"Нельзя удалить активный аккаунт '{name}'. Сначала переключитесь на другой аккаунт.")
                
                # Удаляем аккаунт
                await session.delete(account)
                await session.commit()
                
                logger.info(f"Аккаунт '{name}' удален")
                return True
    
    async def switch_account(self, name: str) -> bool:
        """
        Переключение активного аккаунта
        
        Args:
            name: Название аккаунта для активации
            
        Returns:
            bool: True, если переключение успешно
            
        Raises:
            ValueError: Если аккаунт не найден
        """
        async with self._lock:
            async with self.get_session() as session:
                # Получаем аккаунт для активации
                stmt = select(Account).where(Account.name == name)
                result = await session.execute(stmt)
                account = result.scalar_one_or_none()
                
                if not account:
                    raise ValueError(f"Аккаунт '{name}' не найден")
                
                # Деактивируем все аккаунты
                stmt = update(Account).values(is_active=False)
                await session.execute(stmt)
                
                # Активируем выбранный аккаунт
                account.is_active = True
                account.updated_at = datetime.utcnow()
                
                await session.commit()
                
                logger.info(f"Активный аккаунт переключен на '{name}'")
                return True
    
    async def update_account_last_used(self, account_id: str):
        """
        Обновление времени последнего использования аккаунта
        
        Args:
            account_id: ID счета в Tinkoff
        """
        async with self._lock:
            async with self.get_session() as session:
                stmt = update(Account).where(
                    Account.account_id == account_id
                ).values(
                    last_used_at=datetime.utcnow()
                )
                await session.execute(stmt)
                await session.commit()
                
                logger.debug(f"Обновлено время использования для аккаунта {account_id}")
    
    async def run_migrations(self):
        """
        Выполнение необходимых миграций базы данных
        
        Автоматически проверяет и применяет миграции при запуске приложения.
        Текущие миграции:
        - Добавление полей sl_activation_pct и tp_activation_pct в таблицы global_settings и instrument_settings
        
        Returns:
            bool: True, если миграции выполнены успешно
        """
        logger.info("Проверка необходимости миграций базы данных...")
        
        try:
            # Получаем путь к файлу БД из URL
            db_path = self.db_url.replace("sqlite+aiosqlite:///", "")
            
            # Подключение к БД напрямую через sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Проверка существования колонок
            cursor.execute("PRAGMA table_info(global_settings)")
            global_columns = [col[1] for col in cursor.fetchall()]
            
            cursor.execute("PRAGMA table_info(instrument_settings)")
            instrument_columns = [col[1] for col in cursor.fetchall()]
            
            # Проверяем, нужна ли миграция
            need_migration = False
            
            if "sl_activation_pct" not in global_columns or "tp_activation_pct" not in global_columns:
                need_migration = True
                logger.info("Требуется миграция для таблицы global_settings")
            
            if "sl_activation_pct" not in instrument_columns or "tp_activation_pct" not in instrument_columns:
                need_migration = True
                logger.info("Требуется миграция для таблицы instrument_settings")
            
            if not need_migration:
                logger.info("Миграции не требуются, структура БД актуальна")
                conn.close()
                return True
            
            # Выполняем миграцию
            logger.info("Выполнение миграции для добавления полей активации SL/TP...")
            
            # Добавление колонок, если они еще не существуют
            if "sl_activation_pct" not in global_columns:
                logger.info("Добавление sl_activation_pct в global_settings")
                cursor.execute("ALTER TABLE global_settings ADD COLUMN sl_activation_pct FLOAT NULL")
            
            if "tp_activation_pct" not in global_columns:
                logger.info("Добавление tp_activation_pct в global_settings")
                cursor.execute("ALTER TABLE global_settings ADD COLUMN tp_activation_pct FLOAT NULL")
            
            if "sl_activation_pct" not in instrument_columns:
                logger.info("Добавление sl_activation_pct в instrument_settings")
                cursor.execute("ALTER TABLE instrument_settings ADD COLUMN sl_activation_pct FLOAT NULL")
            
            if "tp_activation_pct" not in instrument_columns:
                logger.info("Добавление tp_activation_pct в instrument_settings")
                cursor.execute("ALTER TABLE instrument_settings ADD COLUMN tp_activation_pct FLOAT NULL")
            
            # Сохранение изменений
            conn.commit()
            conn.close()
            
            logger.info("✅ Миграция успешно выполнена")
            
            # Логируем событие в БД
            await self.log_event(
                event_type="MIGRATION",
                description="Выполнена миграция для добавления полей активации SL/TP",
                details={"tables": ["global_settings", "instrument_settings"]}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при выполнении миграции: {e}")
            return False
