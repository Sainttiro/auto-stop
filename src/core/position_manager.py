"""
Координатор управления позициями
"""
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
import asyncio

from src.storage.database import Database
from src.storage.models import Position, Order
from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.utils.logger import get_logger

# Импортируем компоненты для работы с позициями
from src.core.positions.cache import PositionCache
from src.core.positions.sync import PositionSynchronizer
from src.core.positions.calculator import PositionCalculator
from src.core.positions.multi_tp import MultiTakeProfitManager

logger = get_logger("core.position_manager")


class PositionManager:
    """
    Координатор управления позициями
    
    Делегирует задачи специализированным компонентам и предоставляет
    единый интерфейс для работы с позициями.
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
        
        # Создаем компоненты
        self.cache = PositionCache(database)
        self.synchronizer = PositionSynchronizer(database, self.cache, instrument_cache)
        self.calculator = PositionCalculator()
        self.multi_tp_manager = MultiTakeProfitManager(database)
    
    async def initialize(self):
        """
        Инициализация менеджера позиций - загрузка позиций из БД
        """
        await self.cache.initialize()
    
    def clear_cache(self):
        """
        Очистка кэша позиций
        
        Используется после очистки БД для синхронизации состояния кэша
        """
        self.cache.clear()
    
    async def sync_positions_from_broker(self, account_id: str, api_client: TinkoffAPIClient) -> int:
        """
        Синхронизация позиций из брокера при запуске системы
        
        Args:
            account_id: ID счета
            api_client: Клиент API для запроса позиций
            
        Returns:
            int: Количество синхронизированных позиций
        """
        return await self.synchronizer.sync_from_broker(account_id, api_client)
    
    async def detect_discrepancies(self, account_id: str, api_client: TinkoffAPIClient) -> Dict:
        """
        Обнаружение расхождений между позициями в системе и у брокера
        
        Args:
            account_id: ID счета
            api_client: Клиент API для запроса позиций
            
        Returns:
            Dict: Информация о расхождениях
        """
        return await self.synchronizer.detect_discrepancies(account_id, api_client)
    
    async def resolve_discrepancies(self, account_id: str, api_client: TinkoffAPIClient) -> Dict:
        """
        Устранение расхождений между позициями в системе и у брокера
        
        Args:
            account_id: ID счета
            api_client: Клиент API для запроса позиций
            
        Returns:
            Dict: Результаты устранения расхождений
        """
        return await self.synchronizer.resolve_discrepancies(account_id, api_client)
    
    async def get_position(self, account_id: str, figi: str) -> Optional[Position]:
        """
        Получение позиции по FIGI и ID счета
        
        Args:
            account_id: ID счета
            figi: FIGI инструмента
            
        Returns:
            Optional[Position]: Найденная позиция или None
        """
        return await self.cache.get(account_id, figi)
    
    async def create_position(
        self,
        account_id: str,
        figi: str,
        ticker: str,
        instrument_type: str,
        quantity: int,
        price: Decimal,
        direction: str
    ) -> Position:
        """
        Создание новой позиции
        
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
        # Проверяем, вызывается ли метод из update_position_on_trade (где блокировка уже захвачена)
        if self._lock.locked():
            return await self._create_position_unlocked(
                account_id=account_id,
                figi=figi,
                ticker=ticker,
                instrument_type=instrument_type,
                quantity=quantity,
                price=price,
                direction=direction
            )
        else:
            # Если вызывается напрямую, захватываем блокировку
            async with self._lock:
                return await self._create_position_unlocked(
                    account_id=account_id,
                    figi=figi,
                    ticker=ticker,
                    instrument_type=instrument_type,
                    quantity=quantity,
                    price=price,
                    direction=direction
                )
    
    async def _create_position_unlocked(
        self,
        account_id: str,
        figi: str,
        ticker: str,
        instrument_type: str,
        quantity: int,
        price: Decimal,
        direction: str
    ) -> Position:
        """
        Внутренний метод для создания позиции без захвата блокировки.
        Используется из update_position_on_trade, где блокировка уже захвачена.
        
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
        try:
            # Проверяем, не существует ли уже позиция
            existing = await self.get_position(account_id, figi)
            if existing:
                logger.warning(f"Позиция для {ticker} ({figi}) уже существует, обновляем")
                return await self.update_position(existing.id, quantity, price)
            
            # Проверяем, не была ли недавно создана позиция с тем же FIGI
            # Это нужно для объединения последовательных сделок (например, 3 фьючерса по 1 лоту)
            recent_positions = await self.db.get_recent_positions_by_figi(account_id, figi, seconds=5)
            if recent_positions:
                recent_position = recent_positions[0]  # Берем самую свежую позицию
                
                # Проверяем, что направление совпадает
                if recent_position.direction == direction:
                    logger.warning(
                        f"Найдена недавно созданная позиция для {ticker} ({figi}), "
                        f"объединяем сделки: {recent_position.quantity} + {quantity} лотов"
                    )
                    
                    # Рассчитываем новую среднюю цену
                    old_qty = recent_position.quantity
                    old_price = Decimal(str(recent_position.average_price))
                    new_price = self.calculator.calculate_average_price(old_qty, old_price, quantity, price)
                    
                    # Обновляем позицию
                    return await self.update_position(recent_position.id, old_qty + quantity, new_price)
            
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
            
            # Сохраняем в БД
            await self.db.add(position)
            
            # Обновляем кэш
            await self.cache.add(position)
            
            logger.info(f"Создана новая позиция: {ticker} ({figi}), количество: {quantity}, цена: {price}")
            
            # Логируем событие
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
            
            logger.debug(f"_create_position_unlocked: Позиция {ticker} успешно создана, id={position.id}")
            return position
        except Exception as e:
            logger.error(f"Ошибка при создании позиции {ticker}: {e}", exc_info=True)
            # Логируем ошибку
            await self.db.log_event(
                event_type="ERROR",
                account_id=account_id,
                figi=figi,
                ticker=ticker,
                description=f"Ошибка при создании позиции {ticker}: {str(e)}",
                details={"error": str(e)}
            )
            raise
    
    async def update_position(
        self,
        position_id: int,
        new_quantity: int,
        new_price: Optional[Decimal] = None
    ) -> Position:
        """
        Обновление существующей позиции
        
        Args:
            position_id: ID позиции
            new_quantity: Новое количество лотов
            new_price: Новая цена (если None, то цена не меняется)
            
        Returns:
            Position: Обновленная позиция
        """
        # Проверяем, вызывается ли метод из update_position_on_trade (где блокировка уже захвачена)
        if self._lock.locked():
            return await self._update_position_unlocked(
                position_id=position_id,
                new_quantity=new_quantity,
                new_price=new_price
            )
        else:
            # Если вызывается напрямую, захватываем блокировку
            async with self._lock:
                return await self._update_position_unlocked(
                    position_id=position_id,
                    new_quantity=new_quantity,
                    new_price=new_price
                )
    
    async def _update_position_unlocked(
        self,
        position_id: int,
        new_quantity: int,
        new_price: Optional[Decimal] = None
    ) -> Position:
        """
        Внутренний метод для обновления позиции без захвата блокировки.
        Используется из update_position_on_trade, где блокировка уже захвачена.
        
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
        await self.cache.update(position)
        
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
            await self.cache.remove(position.account_id, position.figi)
            
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
    
    async def calculate_average_price(
        self,
        old_qty: int,
        old_price: Decimal,
        new_qty: int,
        new_price: Decimal
    ) -> Decimal:
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
        return self.calculator.calculate_average_price(old_qty, old_price, new_qty, new_price)
    
    async def calculate_pnl(
        self,
        entry_price: Decimal,
        current_price: Decimal,
        quantity: int,
        direction: str
    ) -> Decimal:
        """
        Расчет P&L (прибыли/убытка) позиции
        
        Args:
            entry_price: Цена входа (средняя цена)
            current_price: Текущая цена
            quantity: Количество лотов
            direction: Направление позиции ("LONG" или "SHORT")
            
        Returns:
            Decimal: P&L в абсолютном выражении
        """
        return self.calculator.calculate_pnl(entry_price, current_price, quantity, direction)
    
    async def calculate_pnl_percent(
        self,
        entry_price: Decimal,
        current_price: Decimal,
        direction: str
    ) -> Decimal:
        """
        Расчет P&L в процентах
        
        Args:
            entry_price: Цена входа (средняя цена)
            current_price: Текущая цена
            direction: Направление позиции ("LONG" или "SHORT")
            
        Returns:
            Decimal: P&L в процентах
        """
        return self.calculator.calculate_pnl_percent(entry_price, current_price, direction)
    
    async def update_position_on_trade(
        self,
        account_id: str,
        figi: str,
        ticker: str,
        instrument_type: str,
        quantity: int,
        price: Decimal,
        direction: str
    ) -> Optional[Position]:
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
            Optional[Position]: Обновленная или созданная позиция
        """
        logger.debug(
            f"update_position_on_trade: Начало обработки сделки {ticker}, "
            f"direction={direction}, quantity={quantity}, price={price}"
        )
        
        async with self._lock:
            # Получаем текущую позицию
            position = await self.get_position(account_id, figi)
            
            # Логируем состояние позиции
            if position:
                logger.debug(
                    f"update_position_on_trade: Найдена существующая позиция {ticker}: "
                    f"id={position.id}, quantity={position.quantity}, "
                    f"avg_price={position.average_price}, direction={position.direction}"
                )
            else:
                logger.debug(f"update_position_on_trade: Позиция {ticker} не найдена в БД")
            
            # Если позиции нет, создаем новую
            if not position:
                # Определяем направление позиции в зависимости от направления сделки
                if direction == "BUY":
                    position_direction = "LONG"
                    logger.debug(f"update_position_on_trade: Создаем новую LONG позицию для {ticker}, quantity={quantity}, price={price}")
                else:  # SELL
                    position_direction = "SHORT"
                    logger.debug(f"update_position_on_trade: Создаем новую SHORT позицию для {ticker}, quantity={quantity}, price={price}")
                
                try:
                    # Используем _create_position_unlocked напрямую, так как блокировка уже захвачена
                    new_position = await self._create_position_unlocked(
                        account_id=account_id,
                        figi=figi,
                        ticker=ticker,
                        instrument_type=instrument_type,
                        quantity=quantity,
                        price=price,
                        direction=position_direction
                    )
                    
                    logger.debug(
                        f"update_position_on_trade: Создана новая позиция {ticker}: "
                        f"id={new_position.id}, quantity={new_position.quantity}, "
                        f"avg_price={new_position.average_price}"
                    )
                    
                    return new_position
                except Exception as e:
                    logger.error(f"Ошибка при создании позиции в update_position_on_trade: {e}", exc_info=True)
                    # Логируем ошибку
                    await self.db.log_event(
                        event_type="ERROR",
                        account_id=account_id,
                        figi=figi,
                        ticker=ticker,
                        description=f"Ошибка при создании позиции в update_position_on_trade: {str(e)}",
                        details={"error": str(e)}
                    )
                    # Пробрасываем исключение дальше
                    raise
            
            # Если позиция уже есть, обновляем ее
            old_quantity = position.quantity
            old_price = Decimal(str(position.average_price))
            
            # Определяем, увеличивается или уменьшается позиция
            is_increasing = (position.direction == "LONG" and direction == "BUY") or \
                           (position.direction == "SHORT" and direction == "SELL")
            
            logger.debug(
                f"update_position_on_trade: Обновление существующей позиции {ticker}: "
                f"old_quantity={old_quantity}, old_price={old_price}, "
                f"is_increasing={is_increasing}, direction={direction}"
            )
            
            if is_increasing:
                # Увеличение позиции - рассчитываем новую среднюю цену
                new_quantity = old_quantity + quantity
                new_price = await self.calculate_average_price(old_quantity, old_price, quantity, price)
                
                logger.debug(
                    f"update_position_on_trade: Увеличение позиции {ticker}: "
                    f"new_quantity={new_quantity}, new_price={new_price}"
                )
                
                updated_position = await self.update_position(position.id, new_quantity, new_price)
                
                logger.debug(
                    f"update_position_on_trade: Позиция {ticker} увеличена: "
                    f"id={updated_position.id}, quantity={updated_position.quantity}, "
                    f"avg_price={updated_position.average_price}"
                )
                
                return updated_position
            else:
                # Уменьшение позиции - средняя цена не меняется
                new_quantity = old_quantity - quantity
                
                # Если новое количество <= 0, закрываем позицию
                if new_quantity <= 0:
                    # Если новое количество < 0, это попытка переворота позиции
                    if new_quantity < 0:
                        logger.error(
                            f"⚠️ КРИТИЧНО: Попытка переворота позиции {ticker}! "
                            f"Продано {quantity} при наличии {old_quantity}. "
                            f"Это приведет к SHORT позиции на {abs(new_quantity)} лотов. "
                            f"Закрываем позицию БЕЗ создания SHORT."
                        )
                        
                        # Логируем критическое событие
                        await self.db.log_event(
                            event_type="POSITION_REVERSAL_PREVENTED",
                            account_id=account_id,
                            figi=figi,
                            ticker=ticker,
                            description=(
                                f"Предотвращен переворот позиции {ticker}: "
                                f"продано {quantity} при наличии {old_quantity}. "
                                f"Позиция закрыта без создания SHORT."
                            ),
                            details={
                                "old_quantity": old_quantity,
                                "sold_quantity": quantity,
                                "would_be_short": abs(new_quantity),
                                "prevented": True
                            }
                        )
                    
                    # Закрываем позицию (без создания SHORT)
                    logger.debug(f"update_position_on_trade: Закрываем позицию {ticker} (new_quantity <= 0)")
                    await self.close_position(position.id)
                    logger.debug(f"update_position_on_trade: Возвращаем None для {ticker} (позиция закрыта)")
                    return None
                else:
                    # Просто уменьшаем количество
                    logger.debug(
                        f"update_position_on_trade: Уменьшение позиции {ticker}: "
                        f"new_quantity={new_quantity}"
                    )
                    
                    updated_position = await self.update_position(position.id, new_quantity)
                    
                    logger.debug(
                        f"update_position_on_trade: Позиция {ticker} уменьшена: "
                        f"id={updated_position.id}, quantity={updated_position.quantity}, "
                        f"avg_price={updated_position.average_price}"
                    )
                    
                    return updated_position
    
    async def setup_multi_tp_levels(
        self,
        position_id: int,
        levels: List[Tuple[float, float]]
    ):
        """
        Настройка уровней многоуровневого тейк-профита
        
        Args:
            position_id: ID позиции
            levels: Список кортежей (уровень_цены_в_процентах, процент_объема)
        """
        await self.multi_tp_manager.setup_levels(position_id, levels)
    
    async def get_multi_tp_levels(self, position_id: int):
        """
        Получение уровней многоуровневого тейк-профита
        
        Args:
            position_id: ID позиции
            
        Returns:
            List[MultiTakeProfitLevel]: Список уровней
        """
        return await self.multi_tp_manager.get_levels(position_id)
    
    async def mark_multi_tp_level_triggered(self, level_id: int):
        """
        Отметка уровня многоуровневого тейк-профита как сработавшего
        
        Args:
            level_id: ID уровня
        """
        await self.multi_tp_manager.mark_level_triggered(level_id)
    
    async def get_multi_tp_remaining_volume(self, position_id: int) -> float:
        """
        Получение оставшегося объема для многоуровневого тейк-профита
        
        Args:
            position_id: ID позиции
            
        Returns:
            float: Оставшийся объем в процентах (0-100)
        """
        return await self.multi_tp_manager.get_remaining_volume(position_id)
    
    def validate_multi_tp_levels(self, levels: List[Tuple[float, float]]) -> Tuple[bool, str]:
        """
        Валидация уровней многоуровневого тейк-профита
        
        Args:
            levels: Список кортежей (уровень_цены_в_процентах, процент_объема)
            
        Returns:
            Tuple[bool, str]: (валидно, сообщение об ошибке)
        """
        return self.multi_tp_manager.validate_levels(levels)
    
    async def get_multi_tp_summary(self, position_id: int) -> Dict:
        """
        Получение сводки по многоуровневому тейк-профиту
        
        Args:
            position_id: ID позиции
            
        Returns:
            Dict: Сводка по уровням
        """
        return await self.multi_tp_manager.get_levels_summary(position_id)
