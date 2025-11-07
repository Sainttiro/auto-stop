"""
Управление многоуровневыми тейк-профит ордерами
"""
from typing import List, Tuple, Dict, Any
from decimal import Decimal
from sqlalchemy.future import select

from src.storage.database import Database
from src.storage.models import Position, MultiTakeProfitLevel
from src.utils.logger import get_logger

logger = get_logger("core.positions.multi_tp")


class MultiTakeProfitManager:
    """
    Управление многоуровневыми тейк-профит ордерами
    
    Отвечает за создание, обновление и валидацию уровней
    многоуровневого тейк-профита.
    """
    
    def __init__(self, database: Database):
        """
        Инициализация менеджера многоуровневого TP
        
        Args:
            database: Объект для работы с базой данных
        """
        self.db = database
    
    async def setup_levels(
        self,
        position_id: int,
        levels: List[Tuple[float, float]]
    ) -> List[MultiTakeProfitLevel]:
        """
        Настройка уровней многоуровневого тейк-профита
        
        Args:
            position_id: ID позиции
            levels: Список кортежей (уровень_цены_в_процентах, процент_объема)
            
        Returns:
            List[MultiTakeProfitLevel]: Список созданных уровней
        """
        # Получаем позицию
        position = await self.db.get_by_id(Position, position_id)
        if not position:
            raise ValueError(f"Позиция с ID {position_id} не найдена")
        
        # Удаляем существующие уровни
        await self._delete_existing_levels(position_id)
        
        # Создаем новые уровни
        new_levels = await self._create_levels(position, levels)
        
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
        
        return new_levels
    
    async def delete_all_levels(self, position_id: int) -> int:
        """
        Удаление всех уровней для позиции (публичный метод)
        
        Args:
            position_id: ID позиции
            
        Returns:
            int: Количество удаленных уровней
        """
        return await self._delete_existing_levels(position_id)
    
    async def _delete_existing_levels(self, position_id: int) -> int:
        """
        Удаление существующих уровней для позиции
        
        Args:
            position_id: ID позиции
            
        Returns:
            int: Количество удаленных уровней
        """
        async with self.db.get_session() as session:
            stmt = select(MultiTakeProfitLevel).where(
                MultiTakeProfitLevel.position_id == position_id
            )
            result = await session.execute(stmt)
            existing_levels = result.scalars().all()
            
            deleted_count = 0
            for level in existing_levels:
                await self.db.delete(MultiTakeProfitLevel, level.id)
                deleted_count += 1
            
            logger.debug(f"Удалено {deleted_count} существующих уровней Multi-TP для позиции {position_id}")
            return deleted_count
    
    async def _create_levels(
        self,
        position: Position,
        levels: List[Tuple[float, float]]
    ) -> List[MultiTakeProfitLevel]:
        """
        Создание новых уровней для позиции
        
        Args:
            position: Объект позиции
            levels: Список кортежей (уровень_цены_в_процентах, процент_объема)
            
        Returns:
            List[MultiTakeProfitLevel]: Список созданных уровней
        """
        new_levels = []
        base_price = Decimal(str(position.average_price))
        
        for i, (level_pct, volume_pct) in enumerate(levels, 1):
            # Рассчитываем целевую цену
            if position.direction == "LONG":
                price_level = base_price * (1 + Decimal(str(level_pct)) / 100)
            else:  # SHORT
                price_level = base_price * (1 - Decimal(str(level_pct)) / 100)
            
            level = MultiTakeProfitLevel(
                position_id=position.id,
                level_number=i,
                price_level=float(price_level),
                volume_percent=volume_pct,
                is_triggered=False
            )
            new_levels.append(level)
        
        # Сохраняем в БД
        await self.db.add_all(new_levels)
        
        logger.debug(
            f"Созданы уровни Multi-TP для позиции {position.ticker}: "
            f"{[(l.level_number, l.price_level, l.volume_percent) for l in new_levels]}"
        )
        
        return new_levels
    
    async def get_levels(self, position_id: int) -> List[MultiTakeProfitLevel]:
        """
        Получение уровней для позиции
        
        Args:
            position_id: ID позиции
            
        Returns:
            List[MultiTakeProfitLevel]: Список уровней
        """
        async with self.db.get_session() as session:
            stmt = select(MultiTakeProfitLevel).where(
                MultiTakeProfitLevel.position_id == position_id
            ).order_by(MultiTakeProfitLevel.level_number)
            
            result = await session.execute(stmt)
            levels = result.scalars().all()
            
            return levels
    
    async def mark_level_triggered(self, level_id: int) -> MultiTakeProfitLevel:
        """
        Отметка уровня как сработавшего
        
        Args:
            level_id: ID уровня
            
        Returns:
            MultiTakeProfitLevel: Обновленный уровень
        """
        level = await self.db.get_by_id(MultiTakeProfitLevel, level_id)
        if not level:
            raise ValueError(f"Уровень с ID {level_id} не найден")
        
        # Обновляем статус
        level.is_triggered = True
        await self.db.update(MultiTakeProfitLevel, level_id, {"is_triggered": True})
        
        # Получаем позицию
        position = await self.db.get_by_id(Position, level.position_id)
        
        logger.info(
            f"Уровень {level.level_number} для позиции {position.ticker} отмечен как сработавший: "
            f"цена={level.price_level}, объем={level.volume_percent}%"
        )
        
        # Логируем событие
        await self.db.log_event(
            event_type="MULTI_TP_LEVEL_TRIGGERED",
            account_id=position.account_id,
            figi=position.figi,
            ticker=position.ticker,
            description=(
                f"Уровень {level.level_number} для {position.ticker} сработал: "
                f"цена={level.price_level}, объем={level.volume_percent}%"
            ),
            details={
                "level_number": level.level_number,
                "price_level": level.price_level,
                "volume_percent": level.volume_percent
            }
        )
        
        return level
    
    async def get_remaining_volume(self, position_id: int) -> float:
        """
        Получение оставшегося объема для позиции
        
        Args:
            position_id: ID позиции
            
        Returns:
            float: Оставшийся объем в процентах (0-100)
        """
        levels = await self.get_levels(position_id)
        
        # Суммируем объемы сработавших уровней
        triggered_volume = sum(level.volume_percent for level in levels if level.is_triggered)
        
        # Оставшийся объем
        remaining_volume = 100.0 - triggered_volume
        
        logger.debug(
            f"Оставшийся объем для позиции {position_id}: "
            f"{remaining_volume}% (сработало {triggered_volume}%)"
        )
        
        return remaining_volume
    
    def validate_levels(self, levels: List[Tuple[float, float]]) -> Tuple[bool, str]:
        """
        Валидация уровней многоуровневого TP
        
        Args:
            levels: Список кортежей (уровень_цены_в_процентах, процент_объема)
            
        Returns:
            Tuple[bool, str]: (валидно, сообщение об ошибке)
        """
        # Проверка на пустой список
        if not levels:
            return False, "Список уровней не может быть пустым"
        
        # Проверка на корректность значений
        for i, (level_pct, volume_pct) in enumerate(levels, 1):
            if level_pct <= 0:
                return False, f"Уровень {i}: процент цены должен быть положительным"
            
            if volume_pct <= 0 or volume_pct > 100:
                return False, f"Уровень {i}: процент объема должен быть в диапазоне (0, 100]"
        
        # Проверка на сумму объемов (только если уровней больше одного)
        if len(levels) > 1:
            total_volume = sum(volume_pct for _, volume_pct in levels)
            if abs(total_volume - 100.0) > 0.01:  # Допускаем небольшую погрешность
                return False, f"Сумма процентов объема должна быть равна 100% (сейчас {total_volume}%)"
        
        # Проверка на возрастание уровней цены
        prev_level = 0
        for i, (level_pct, _) in enumerate(levels, 1):
            if level_pct <= prev_level:
                return False, f"Уровень {i}: процент цены должен быть больше предыдущего"
            prev_level = level_pct
        
        return True, ""
    
    async def get_levels_summary(self, position_id: int) -> Dict[str, Any]:
        """
        Получение сводки по уровням для позиции
        
        Args:
            position_id: ID позиции
            
        Returns:
            Dict[str, Any]: Сводка по уровням
        """
        levels = await self.get_levels(position_id)
        
        # Получаем позицию
        position = await self.db.get_by_id(Position, position_id)
        if not position:
            raise ValueError(f"Позиция с ID {position_id} не найдена")
        
        # Формируем сводку
        triggered_levels = [level for level in levels if level.is_triggered]
        remaining_levels = [level for level in levels if not level.is_triggered]
        
        triggered_volume = sum(level.volume_percent for level in triggered_levels)
        remaining_volume = sum(level.volume_percent for level in remaining_levels)
        
        return {
            "position_id": position_id,
            "ticker": position.ticker,
            "total_levels": len(levels),
            "triggered_levels": len(triggered_levels),
            "remaining_levels": len(remaining_levels),
            "triggered_volume": triggered_volume,
            "remaining_volume": remaining_volume,
            "levels": [
                {
                    "level_number": level.level_number,
                    "price_level": level.price_level,
                    "volume_percent": level.volume_percent,
                    "is_triggered": level.is_triggered
                }
                for level in levels
            ]
        }
