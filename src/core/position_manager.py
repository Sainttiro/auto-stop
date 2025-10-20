from typing import Optional, Dict, List, Tuple
from decimal import Decimal
import asyncio
from sqlalchemy.future import select

from src.storage.database import Database
from src.storage.models import Position, Order, MultiTakeProfitLevel
from src.api.instrument_info import InstrumentInfoCache
from src.utils.logger import get_logger

logger = get_logger("core.position_manager")


class PositionManager:
    """
    Управление позициями и расчет средней цены
    """
    
    def __init__(self, database: Database, instrument_cache: InstrumentInfoCache):
        """
        Инициализация менеджера позиций
        
        Args:
            database: Объект для работы с базой данных
            instrument_cache: Кэш информации об инструментах
        """
        self.db = database
        self.instrument_cache = instrument_cache
        self._lock = asyncio.Lock()
        self._positions_cache: Dict[str, Dict[str, Position]] = {}  # account_id -> {figi -> Position}
    
    async def initialize(self):
        """
        Инициализация менеджера позиций - загрузка позиций из БД
        """
        positions = await self.db.get_all(Position)
        
        for position in positions:
            account_id = position.account_id
            figi = position.figi
            
            if account_id not in self._positions_cache:
                self._positions_cache[account_id] = {}
                
            self._positions_cache[account_id][figi] = position
            
        logger.info(f"Загружено {len(positions)} позиций из базы данных")
    
    def clear_cache(self):
        """
        Очистка кэша позиций
        
        Используется после очистки БД для синхронизации состояния кэша
        """
        self._positions_cache.clear()
        logger.info("Кэш позиций очищен")
    
    async def sync_positions_from_broker(self, account_id: str, api_client) -> int:
        """
        Синхронизация позиций из брокера при запуске системы
        
        Запрашивает текущие позиции через API и сохраняет их в БД.
        Это позволяет системе подхватить позиции, открытые до запуска.
        
        Args:
            account_id: ID счета
            api_client: Клиент API для запроса позиций
            
        Returns:
            int: Количество синхронизированных позиций
        """
        logger.info(f"Начало синхронизации позиций из брокера для счета {account_id}")
        
        try:
            # Запрашиваем текущие позиции через API
            positions_response = await api_client.get_positions(account_id)
            
            synced_count = 0
            
            # Обрабатываем позиции по ценным бумагам
            for security in positions_response.securities:
                try:
                    figi = security.figi
                    balance = security.balance
                    
                    # Пропускаем позиции с нулевым балансом
                    if balance == 0:
                        continue
                    
                    # Проверяем, есть ли уже позиция в БД
                    existing_position = await self.get_position(account_id, figi)
                    if existing_position:
                        logger.debug(f"Позиция {figi} уже существует в БД, пропускаем")
                        continue
                    
                    # Получаем информацию об инструменте
                    instrument = await self.instrument_cache.get_instrument_by_figi(figi)
                    if not instrument:
                        logger.warning(f"Не удалось получить информацию об инструменте {figi}")
                        continue
                    
                    ticker = instrument.ticker
                    instrument_type = "stock" if instrument.instrument_type.lower().startswith("share") else "futures"
                    
                    # Определяем направление позиции
                    # balance > 0 = LONG, balance < 0 = SHORT (для фьючерсов)
                    # Для акций balance всегда > 0, SHORT определяется по blocked
                    if balance > 0:
                        direction = "LONG"
                        quantity = balance
                    else:
                        direction = "SHORT"
                        quantity = abs(balance)
                    
                    # Получаем среднюю цену из API
                    # Для акций используем average_position_price
                    avg_price = Decimal(0)
                    if hasattr(security, 'average_position_price') and security.average_position_price:
                        avg_price = Decimal(str(security.average_position_price.units)) + \
                                   Decimal(str(security.average_position_price.nano)) / Decimal(1_000_000_000)
                    
                    # Если средняя цена не доступна, используем заглушку
                    # SL/TP не будут выставлены, но позиция будет синхронизирована
                    # При первой сделке средняя цена обновится и SL/TP выставятся
                    if avg_price == 0:
                        avg_price = Decimal(1)
                        logger.warning(
                            f"Средняя цена для {ticker} недоступна из API. "
                            f"Позиция будет синхронизирована с заглушкой (цена=1). "
                            f"SL/TP будут выставлены при первой сделке."
                        )
                    
                    # Создаем позицию в БД
                    logger.info(
                        f"Синхронизация позиции: {ticker} ({figi}), "
                        f"направление={direction}, количество={quantity}, цена={avg_price}"
                    )
                    
                    position = Position(
                        account_id=account_id,
                        figi=figi,
                        ticker=ticker,
                        instrument_type=instrument_type,
                        quantity=quantity,
                        average_price=float(avg_price),
                        direction=direction
                    )
                    
                    await self.db.add(position)
                    
                    # Обновляем кэш
                    if account_id not in self._positions_cache:
                        self._positions_cache[account_id] = {}
                    self._positions_cache[account_id][figi] = position
                    
                    # Логируем событие
                    await self.db.log_event(
                        event_type="POSITION_SYNCED",
                        account_id=account_id,
                        figi=figi,
                        ticker=ticker,
                        description=f"Синхронизирована позиция {ticker} из брокера",
                        details={
                            "quantity": quantity,
                            "price": float(avg_price),
                            "direction": direction
                        }
                    )
                    
                    synced_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка при синхронизации позиции {security.figi}: {e}")
                    continue
            
            logger.info(f"Синхронизировано {synced_count} позиций из брокера")
            return synced_count
            
        except Exception as e:
            logger.error(f"Ошибка при синхронизации позиций из брокера: {e}")
            return 0
    
    async def get_position(self, account_id: str, figi: str) -> Optional[Position]:
        """
        Получение позиции по FIGI и ID счета
        
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
            if account_id not in self._positions_cache:
                self._positions_cache[account_id] = {}
            self._positions_cache[account_id][figi] = position
            
        return position
    
    async def _create_position_unlocked(self, account_id: str, figi: str, ticker: str, 
                                       instrument_type: str, quantity: int, price: Decimal, 
                                       direction: str) -> Position:
        """
        Внутренний метод создания новой позиции БЕЗ блокировки
        Используется когда блокировка уже получена вызывающим методом
        
        Args:
            account_id: ID счета
            figi: FIGI инструмента
            ticker: Тикер инструмента
            instrument_type: Тип инструмента ("stock" или "futures")
            quantity: Количество лотов
            price: Цена входа
            direction: Направление ("LONG" или "SHORT")
            
        Returns:
            Position: Созданная позиция
        """
        logger.debug(f"_create_position_unlocked: Начало создания позиции для {ticker}")
        
        # Проверяем, не существует ли уже позиция
        logger.debug(f"_create_position_unlocked: Проверка существующей позиции для {ticker}")
        existing = await self.get_position(account_id, figi)
        if existing:
            logger.warning(f"Позиция для {ticker} ({figi}) уже существует, обновляем")
            return await self._update_position_unlocked(existing.id, quantity, price)
        
        logger.debug(f"_create_position_unlocked: Создание объекта Position для {ticker}")
        # Создаем новую позицию
        position = Position(
            account_id=account_id,
            figi=figi,
            ticker=ticker,
            instrument_type=instrument_type,
            quantity=quantity,
            average_price=float(price),
            direction=direction
        )
        
        logger.debug(f"_create_position_unlocked: Сохранение позиции в БД для {ticker}")
        # Сохраняем в БД
        await self.db.add(position)
        logger.debug(f"_create_position_unlocked: Позиция сохранена в БД для {ticker}, id={position.id}")
        
        # Обновляем кэш
        logger.debug(f"_create_position_unlocked: Обновление кэша для {ticker}")
        if account_id not in self._positions_cache:
            self._positions_cache[account_id] = {}
        self._positions_cache[account_id][figi] = position
        
        logger.info(f"Создана новая позиция: {ticker} ({figi}), количество: {quantity}, цена: {price}")
        
        # Логируем событие
        logger.debug(f"_create_position_unlocked: Логирование события для {ticker}")
        await self.db.log_event(
            event_type="POSITION_CREATED",
            account_id=account_id,
            figi=figi,
            ticker=ticker,
            description=f"Создана позиция {ticker}, количество: {quantity}, цена: {price}",
            details={
                "quantity": quantity,
                "price": float(price),
                "direction": direction
            }
        )
        logger.debug(f"_create_position_unlocked: Завершение создания позиции для {ticker}")
        
        return position
    
    async def create_position(self, account_id: str, figi: str, ticker: str, 
                             instrument_type: str, quantity: int, price: Decimal, 
                             direction: str) -> Position:
        """
        Создание новой позиции (публичный метод с блокировкой)
        
        Args:
            account_id: ID счета
            figi: FIGI инструмента
            ticker: Тикер инструмента
            instrument_type: Тип инструмента ("stock" или "futures")
            quantity: Количество лотов
            price: Цена входа
            direction: Направление ("LONG" или "SHORT")
            
        Returns:
            Position: Созданная позиция
        """
        logger.debug(f"create_position: Начало создания позиции для {ticker}")
        
        async with self._lock:
            logger.debug(f"create_position: Получена блокировка для {ticker}")
            return await self._create_position_unlocked(account_id, figi, ticker, instrument_type, quantity, price, direction)
    
    async def _update_position_unlocked(self, position_id: int, new_quantity: int, 
                                       new_price: Optional[Decimal] = None) -> Position:
        """
        Внутренний метод обновления позиции БЕЗ блокировки
        Используется когда блокировка уже получена вызывающим методом
        
        Args:
            position_id: ID позиции
            new_quantity: Новое количество лотов
            new_price: Новая цена (если None, то цена не меняется)
            
        Returns:
            Position: Обновленная позиция
        """
        # Получаем позицию из БД
        position = await self.db.get_by_id(Position, position_id)
        if not position:
            raise ValueError(f"Позиция с ID {position_id} не найдена")
        
        # Обновляем поля
        old_quantity = position.quantity
        old_price = position.average_price
        
        position.quantity = new_quantity
        
        if new_price is not None:
            position.average_price = float(new_price)
        
        # Сохраняем в БД
        await self.db.update(
            Position, 
            position_id, 
            {
                "quantity": new_quantity,
                "average_price": float(new_price) if new_price is not None else position.average_price
            }
        )
        
        # Обновляем кэш
        if position.account_id in self._positions_cache and position.figi in self._positions_cache[position.account_id]:
            self._positions_cache[position.account_id][position.figi] = position
        
        logger.info(
            f"Обновлена позиция: {position.ticker} ({position.figi}), "
            f"количество: {old_quantity} -> {new_quantity}, "
            f"цена: {old_price} -> {position.average_price}"
        )
        
        # Логируем событие
        await self.db.log_event(
            event_type="POSITION_UPDATED",
            account_id=position.account_id,
            figi=position.figi,
            ticker=position.ticker,
            description=f"Обновлена позиция {position.ticker}, количество: {old_quantity} -> {new_quantity}",
            details={
                "old_quantity": old_quantity,
                "new_quantity": new_quantity,
                "old_price": old_price,
                "new_price": position.average_price
            }
        )
        
        return position
    
    async def update_position(self, position_id: int, new_quantity: int, 
                             new_price: Optional[Decimal] = None) -> Position:
        """
        Обновление существующей позиции (публичный метод с блокировкой)
        
        Args:
            position_id: ID позиции
            new_quantity: Новое количество лотов
            new_price: Новая цена (если None, то цена не меняется)
            
        Returns:
            Position: Обновленная позиция
        """
        async with self._lock:
            return await self._update_position_unlocked(position_id, new_quantity, new_price)
    
    async def close_position(self, position_id: int):
        """
        Закрытие позиции
        
        Args:
            position_id: ID позиции
        """
        async with self._lock:
            # Получаем позицию из БД
            position = await self.db.get_by_id(Position, position_id)
            if not position:
                raise ValueError(f"Позиция с ID {position_id} не найдена")
            
            # Получаем активные ордера для позиции
            active_orders = await self.db.get_active_orders_by_position(position_id)
            
            # Отмечаем ордера как отмененные
            for order in active_orders:
                await self.db.update(Order, order.id, {"status": "CANCELLED"})
            
            # Удаляем позицию из кэша
            if position.account_id in self._positions_cache and position.figi in self._positions_cache[position.account_id]:
                del self._positions_cache[position.account_id][position.figi]
            
            # Логируем событие
            await self.db.log_event(
                event_type="POSITION_CLOSED",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"Закрыта позиция {position.ticker}, количество: {position.quantity}",
                details={
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "cancelled_orders": len(active_orders)
                }
            )
            
            # Удаляем позицию из БД
            await self.db.delete(Position, position_id)
            
            logger.info(f"Закрыта позиция: {position.ticker} ({position.figi}), количество: {position.quantity}")
    
    async def calculate_average_price(self, old_qty: int, old_price: Decimal, 
                                     new_qty: int, new_price: Decimal) -> Decimal:
        """
        Расчет новой средней цены при усреднении позиции
        
        Args:
            old_qty: Старое количество лотов
            old_price: Старая средняя цена
            new_qty: Новое количество лотов
            new_price: Цена новых лотов
            
        Returns:
            Decimal: Новая средняя цена
        """
        if old_qty + new_qty == 0:
            return Decimal(0)
            
        total_cost = (old_qty * old_price) + (new_qty * new_price)
        total_qty = old_qty + new_qty
        
        return total_cost / total_qty
    
    async def update_position_on_trade(self, account_id: str, figi: str, ticker: str,
                                      instrument_type: str, quantity: int, price: Decimal,
                                      direction: str) -> Position:
        """
        Обновление позиции при исполнении сделки
        
        Args:
            account_id: ID счета
            figi: FIGI инструмента
            ticker: Тикер инструмента
            instrument_type: Тип инструмента ("stock" или "futures")
            quantity: Количество лотов в сделке
            price: Цена сделки
            direction: Направление сделки ("BUY" или "SELL")
            
        Returns:
            Position: Обновленная или созданная позиция
        """
        logger.debug(f"update_position_on_trade: Начало обработки для {ticker}, direction={direction}, quantity={quantity}")
        
        async with self._lock:
            logger.debug(f"update_position_on_trade: Получена блокировка для {ticker}")
            
            # Получаем текущую позицию
            logger.debug(f"update_position_on_trade: Получение текущей позиции для {ticker}")
            position = await self.get_position(account_id, figi)
            logger.debug(f"update_position_on_trade: Позиция {'найдена' if position else 'не найдена'} для {ticker}")
            
            # Если позиции нет, создаем новую
            if not position:
                # Если это продажа без позиции - это продажа старых акций, не отслеживаемых системой
                # НЕ создаем SHORT позицию
                if direction == "SELL":
                    logger.info(
                        f"Продажа {ticker} без позиции в системе. "
                        f"Это продажа акций, не отслеживаемых системой. Пропускаем."
                    )
                    return None
                
                logger.debug(f"update_position_on_trade: Создание новой позиции для {ticker}")
                # Создаем только LONG позицию при покупке
                position_direction = "LONG"
                logger.debug(f"update_position_on_trade: Направление позиции: {position_direction}")
                
                # Используем внутренний метод БЕЗ блокировки (блокировка уже получена)
                new_position = await self._create_position_unlocked(
                    account_id=account_id,
                    figi=figi,
                    ticker=ticker,
                    instrument_type=instrument_type,
                    quantity=quantity,
                    price=price,
                    direction=position_direction
                )
                logger.debug(f"update_position_on_trade: Позиция создана для {ticker}, id={new_position.id if new_position else None}")
                return new_position
            
            # Если позиция уже есть, обновляем ее
            logger.debug(f"update_position_on_trade: Обновление существующей позиции для {ticker}")
            old_quantity = position.quantity
            old_price = Decimal(str(position.average_price))
            
            # Определяем, увеличивается или уменьшается позиция
            is_increasing = (position.direction == "LONG" and direction == "BUY") or \
                           (position.direction == "SHORT" and direction == "SELL")
            
            logger.debug(f"update_position_on_trade: is_increasing={is_increasing} для {ticker}")
            
            if is_increasing:
                # Увеличение позиции - рассчитываем новую среднюю цену
                logger.debug(f"update_position_on_trade: Увеличение позиции для {ticker}")
                new_quantity = old_quantity + quantity
                new_price = await self.calculate_average_price(old_quantity, old_price, quantity, price)
                logger.debug(f"update_position_on_trade: Новая средняя цена для {ticker}: {new_price}")
                # Используем внутренний метод БЕЗ блокировки (блокировка уже получена)
                return await self._update_position_unlocked(position.id, new_quantity, new_price)
            else:
                # Уменьшение позиции - средняя цена не меняется
                logger.debug(f"update_position_on_trade: Уменьшение позиции для {ticker}")
                new_quantity = old_quantity - quantity
                
                # Если новое количество <= 0, закрываем позицию
                if new_quantity <= 0:
                    logger.debug(f"update_position_on_trade: Закрытие позиции для {ticker}")
                    await self.close_position(position.id)
                    # Если новое количество < 0, создаем позицию в противоположном направлении
                    if new_quantity < 0:
                        logger.debug(f"update_position_on_trade: Создание позиции в противоположном направлении для {ticker}")
                        new_direction = "SHORT" if position.direction == "LONG" else "LONG"
                        # Используем внутренний метод БЕЗ блокировки (блокировка уже получена)
                        return await self._create_position_unlocked(
                            account_id=account_id,
                            figi=figi,
                            ticker=ticker,
                            instrument_type=instrument_type,
                            quantity=abs(new_quantity),
                            price=price,
                            direction=new_direction
                        )
                    return None
                else:
                    # Просто уменьшаем количество
                    logger.debug(f"update_position_on_trade: Уменьшение количества для {ticker}")
                    # Используем внутренний метод БЕЗ блокировки (блокировка уже получена)
                    return await self._update_position_unlocked(position.id, new_quantity)
    
    async def setup_multi_tp_levels(self, position_id: int, levels: List[Tuple[float, float]]):
        """
        Настройка уровней многоуровневого тейк-профита
        
        Args:
            position_id: ID позиции
            levels: Список кортежей (уровень_цены_в_процентах, процент_объема)
        """
        async with self._lock:
            # Получаем позицию
            position = await self.db.get_by_id(Position, position_id)
            if not position:
                raise ValueError(f"Позиция с ID {position_id} не найдена")
            
            # Удаляем существующие уровни
            async with self.db.get_session() as session:
                stmt = select(MultiTakeProfitLevel).where(
                    MultiTakeProfitLevel.position_id == position_id
                )
                result = await session.execute(stmt)
                existing_levels = result.scalars().all()
                
                for level in existing_levels:
                    await self.db.delete(MultiTakeProfitLevel, level.id)
            
            # Создаем новые уровни
            new_levels = []
            base_price = Decimal(str(position.average_price))
            
            for i, (level_pct, volume_pct) in enumerate(levels, 1):
                # Рассчитываем целевую цену
                if position.direction == "LONG":
                    price_level = base_price * (1 + Decimal(str(level_pct)) / 100)
                else:  # SHORT
                    price_level = base_price * (1 - Decimal(str(level_pct)) / 100)
                
                level = MultiTakeProfitLevel(
                    position_id=position_id,
                    level_number=i,
                    price_level=float(price_level),
                    volume_percent=volume_pct,
                    is_triggered=False
                )
                new_levels.append(level)
            
            # Сохраняем в БД
            await self.db.add_all(new_levels)
            
            logger.info(f"Настроены уровни многоуровневого TP для позиции {position.ticker}: {len(levels)} уровней")
            
            # Логируем событие
            await self.db.log_event(
                event_type="MULTI_TP_SETUP",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"Настроены уровни многоуровневого TP для {position.ticker}: {len(levels)} уровней",
                details={
                    "levels": [{"level_pct": l[0], "volume_pct": l[1]} for l in levels]
                }
            )
