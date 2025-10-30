"""
Менеджер настроек торговли
Управление глобальными и индивидуальными настройками инструментов
"""

import json
from typing import Optional, Dict, List, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import GlobalSettings, InstrumentSettings
from src.storage.database import Database
from src.utils.logger import get_logger

logger = get_logger("settings_manager")


class SettingsManager:
    """
    Менеджер настроек торговли
    
    Управляет глобальными настройками и настройками для конкретных инструментов.
    Приоритет: Настройки инструмента → Глобальные настройки → Defaults
    """
    
    def __init__(self, database: Database):
        """
        Инициализация менеджера настроек
        
        Args:
            database: Экземпляр базы данных
        """
        self.db = database
    
    # ==================== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ====================
    
    async def get_global_settings(self, account_id: str) -> Optional[GlobalSettings]:
        """
        Получить глобальные настройки для аккаунта
        
        Args:
            account_id: ID аккаунта
            
        Returns:
            GlobalSettings или None если не найдены
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(GlobalSettings).where(GlobalSettings.account_id == account_id)
            )
            return result.scalar_one_or_none()
    
    async def create_global_settings(
        self,
        account_id: str,
        stop_loss_pct: float = 0.4,
        take_profit_pct: float = 1.0,
        sl_activation_pct: Optional[float] = None,
        tp_activation_pct: Optional[float] = None,
        multi_tp_enabled: bool = False,
        multi_tp_levels: Optional[List[Dict]] = None,
        multi_tp_sl_strategy: str = "fixed"
    ) -> GlobalSettings:
        """
        Создать глобальные настройки для аккаунта
        
        Args:
            account_id: ID аккаунта
            stop_loss_pct: Процент стоп-лосса
            take_profit_pct: Процент тейк-профита
            sl_activation_pct: Процент активации стоп-лосса (опционально)
            tp_activation_pct: Процент активации тейк-профита (опционально)
            multi_tp_enabled: Включен ли Multi-TP
            multi_tp_levels: Уровни Multi-TP
            multi_tp_sl_strategy: Стратегия SL ("fixed" или "custom")
            
        Returns:
            Созданные настройки
        """
        async with self.db.get_session() as session:
            settings = GlobalSettings(
                account_id=account_id,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                sl_activation_pct=sl_activation_pct,
                tp_activation_pct=tp_activation_pct,
                multi_tp_enabled=multi_tp_enabled,
                multi_tp_levels=json.dumps(multi_tp_levels) if multi_tp_levels else None,
                multi_tp_sl_strategy=multi_tp_sl_strategy
            )
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            
            logger.info(f"Созданы глобальные настройки для аккаунта {account_id}")
            return settings
    
    async def update_global_settings(
        self,
        account_id: str,
        **kwargs
    ) -> GlobalSettings:
        """
        Обновить глобальные настройки
        
        Args:
            account_id: ID аккаунта
            **kwargs: Параметры для обновления
            
        Returns:
            Обновленные настройки
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(GlobalSettings).where(GlobalSettings.account_id == account_id)
            )
            settings = result.scalar_one_or_none()
            
            if not settings:
                # Создать если не существует
                return await self.create_global_settings(account_id, **kwargs)
            
            # Обновить поля
            for key, value in kwargs.items():
                if key == 'multi_tp_levels' and value is not None:
                    value = json.dumps(value)
                if hasattr(settings, key):
                    setattr(settings, key, value)
            
            await session.commit()
            await session.refresh(settings)
            
            logger.info(f"Обновлены глобальные настройки для аккаунта {account_id}: {kwargs}")
            return settings
    
    # ==================== НАСТРОЙКИ ИНСТРУМЕНТОВ ====================
    
    async def get_instrument_settings(
        self,
        account_id: str,
        ticker: str
    ) -> Optional[InstrumentSettings]:
        """
        Получить настройки для конкретного инструмента
        
        Args:
            account_id: ID аккаунта
            ticker: Тикер инструмента
            
        Returns:
            InstrumentSettings или None
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(InstrumentSettings).where(
                    InstrumentSettings.account_id == account_id,
                    InstrumentSettings.ticker == ticker
                )
            )
            return result.scalar_one_or_none()
    
    async def create_instrument_settings(
        self,
        account_id: str,
        ticker: str,
        figi: Optional[str] = None,
        **kwargs
    ) -> InstrumentSettings:
        """
        Создать настройки для инструмента
        
        Args:
            account_id: ID аккаунта
            ticker: Тикер инструмента
            figi: FIGI инструмента
            **kwargs: Дополнительные параметры
            
        Returns:
            Созданные настройки
        """
        async with self.db.get_session() as session:
            # Конвертировать multi_tp_levels в JSON если есть
            if 'multi_tp_levels' in kwargs and kwargs['multi_tp_levels'] is not None:
                kwargs['multi_tp_levels'] = json.dumps(kwargs['multi_tp_levels'])
            
            settings = InstrumentSettings(
                account_id=account_id,
                ticker=ticker,
                figi=figi,
                **kwargs
            )
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            
            logger.info(f"Созданы настройки для {ticker} (аккаунт {account_id})")
            return settings
    
    async def update_instrument_settings(
        self,
        account_id: str,
        ticker: str,
        **kwargs
    ) -> InstrumentSettings:
        """
        Обновить настройки инструмента
        
        Args:
            account_id: ID аккаунта
            ticker: Тикер инструмента
            **kwargs: Параметры для обновления
            
        Returns:
            Обновленные настройки
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(InstrumentSettings).where(
                    InstrumentSettings.account_id == account_id,
                    InstrumentSettings.ticker == ticker
                )
            )
            settings = result.scalar_one_or_none()
            
            if not settings:
                # Создать если не существует
                return await self.create_instrument_settings(account_id, ticker, **kwargs)
            
            # Обновить поля
            for key, value in kwargs.items():
                if key == 'multi_tp_levels' and value is not None:
                    value = json.dumps(value)
                if hasattr(settings, key):
                    setattr(settings, key, value)
            
            await session.commit()
            await session.refresh(settings)
            
            logger.info(f"Обновлены настройки для {ticker} (аккаунт {account_id}): {kwargs}")
            return settings
    
    async def delete_instrument_settings(
        self,
        account_id: str,
        ticker: str
    ) -> bool:
        """
        Удалить настройки инструмента (вернуться к глобальным)
        
        Args:
            account_id: ID аккаунта
            ticker: Тикер инструмента
            
        Returns:
            True если удалено, False если не найдено
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(InstrumentSettings).where(
                    InstrumentSettings.account_id == account_id,
                    InstrumentSettings.ticker == ticker
                )
            )
            settings = result.scalar_one_or_none()
            
            if settings:
                await session.delete(settings)
                await session.commit()
                logger.info(f"Удалены настройки для {ticker} (аккаунт {account_id})")
                return True
            
            return False
    
    async def get_all_instruments(self, account_id: str) -> List[InstrumentSettings]:
        """
        Получить все инструменты с индивидуальными настройками
        
        Args:
            account_id: ID аккаунта
            
        Returns:
            Список настроек инструментов
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(InstrumentSettings).where(
                    InstrumentSettings.account_id == account_id
                ).order_by(InstrumentSettings.ticker)
            )
            return list(result.scalars().all())
    
    # ==================== ЭФФЕКТИВНЫЕ НАСТРОЙКИ ====================
    
    async def get_effective_settings(
        self,
        account_id: str,
        ticker: str
    ) -> Dict[str, Any]:
        """
        Получить эффективные настройки для инструмента
        
        Применяет приоритет: Инструмент → Глобальные → Defaults
        
        Args:
            account_id: ID аккаунта
            ticker: Тикер инструмента
            
        Returns:
            Словарь с эффективными настройками
        """
        # Получить настройки инструмента
        instrument_settings = await self.get_instrument_settings(account_id, ticker)
        
        # Получить глобальные настройки
        global_settings = await self.get_global_settings(account_id)
        
        # Defaults
        defaults = {
            'stop_loss_pct': 0.4,
            'take_profit_pct': 1.0,
            'sl_activation_pct': None,
            'tp_activation_pct': None,
            'multi_tp_enabled': False,
            'multi_tp_levels': [],
            'multi_tp_sl_strategy': 'fixed',
            'source': 'default'
        }
        
        # Применить глобальные настройки
        if global_settings:
            defaults['stop_loss_pct'] = global_settings.stop_loss_pct
            defaults['take_profit_pct'] = global_settings.take_profit_pct
            defaults['sl_activation_pct'] = global_settings.sl_activation_pct
            defaults['tp_activation_pct'] = global_settings.tp_activation_pct
            defaults['multi_tp_enabled'] = global_settings.multi_tp_enabled
            defaults['multi_tp_levels'] = (
                json.loads(global_settings.multi_tp_levels)
                if global_settings.multi_tp_levels
                else []
            )
            defaults['multi_tp_sl_strategy'] = global_settings.multi_tp_sl_strategy
            defaults['source'] = 'global'
        
        # Применить настройки инструмента (переопределяют глобальные)
        if instrument_settings:
            if instrument_settings.stop_loss_pct is not None:
                defaults['stop_loss_pct'] = instrument_settings.stop_loss_pct
                defaults['source'] = 'instrument'
            
            if instrument_settings.take_profit_pct is not None:
                defaults['take_profit_pct'] = instrument_settings.take_profit_pct
                defaults['source'] = 'instrument'
            
            if instrument_settings.sl_activation_pct is not None:
                defaults['sl_activation_pct'] = instrument_settings.sl_activation_pct
                defaults['source'] = 'instrument'
            
            if instrument_settings.tp_activation_pct is not None:
                defaults['tp_activation_pct'] = instrument_settings.tp_activation_pct
                defaults['source'] = 'instrument'
            
            if instrument_settings.multi_tp_enabled is not None:
                defaults['multi_tp_enabled'] = instrument_settings.multi_tp_enabled
                defaults['source'] = 'instrument'
            
            if instrument_settings.multi_tp_levels is not None:
                defaults['multi_tp_levels'] = json.loads(instrument_settings.multi_tp_levels)
                defaults['source'] = 'instrument'
            
            if instrument_settings.multi_tp_sl_strategy is not None:
                defaults['multi_tp_sl_strategy'] = instrument_settings.multi_tp_sl_strategy
                defaults['source'] = 'instrument'
        
        logger.debug(
            f"Эффективные настройки для {ticker}: "
            f"SL={defaults['stop_loss_pct']}%, TP={defaults['take_profit_pct']}%, "
            f"SL-активация={defaults['sl_activation_pct']}%, TP-активация={defaults['tp_activation_pct']}%, "
            f"Multi-TP={defaults['multi_tp_enabled']}, source={defaults['source']}"
        )
        
        return defaults
    
    # ==================== ВАЛИДАЦИЯ ====================
    
    def validate_activation_settings(
        self,
        sl_pct: float,
        sl_activation_pct: Optional[float],
        tp_pct: float,
        tp_activation_pct: Optional[float],
        direction: str = "LONG"
    ) -> tuple[bool, Optional[str]]:
        """
        Валидация настроек активации
        
        Args:
            sl_pct: Процент стоп-лосса
            sl_activation_pct: Процент активации стоп-лосса
            tp_pct: Процент тейк-профита
            tp_activation_pct: Процент активации тейк-профита
            direction: Направление позиции ("LONG" или "SHORT")
            
        Returns:
            (valid, error_message)
        """
        # Если активация не задана, то всё валидно
        if sl_activation_pct is None and tp_activation_pct is None:
            return True, None
        
        # Проверка активации SL
        if sl_activation_pct is not None:
            if sl_activation_pct <= 0:
                return False, "Активация SL должна быть больше 0%"
            
            if direction == "LONG":
                # Для LONG: активация должна быть меньше SL
                if sl_activation_pct >= sl_pct:
                    return False, f"Активация SL ({sl_activation_pct}%) должна быть меньше SL ({sl_pct}%)"
            else:  # SHORT
                # Для SHORT: активация должна быть меньше SL
                if sl_activation_pct >= sl_pct:
                    return False, f"Активация SL ({sl_activation_pct}%) должна быть меньше SL ({sl_pct}%)"
        
        # Проверка активации TP
        if tp_activation_pct is not None:
            if tp_activation_pct <= 0:
                return False, "Активация TP должна быть больше 0%"
            
            if direction == "LONG":
                # Для LONG: активация должна быть меньше TP
                if tp_activation_pct >= tp_pct:
                    return False, f"Активация TP ({tp_activation_pct}%) должна быть меньше TP ({tp_pct}%)"
            else:  # SHORT
                # Для SHORT: активация должна быть меньше TP
                if tp_activation_pct >= tp_pct:
                    return False, f"Активация TP ({tp_activation_pct}%) должна быть меньше TP ({tp_pct}%)"
        
        return True, None
    
    def validate_multi_tp_levels(self, levels: List[Dict]) -> tuple[bool, Optional[str]]:
        """
        Валидация уровней Multi-TP
        
        Args:
            levels: Список уровней
            
        Returns:
            (valid, error_message)
        """
        if not levels:
            return False, "Должен быть хотя бы один уровень"
        
        if len(levels) > 10:
            return False, "Максимум 10 уровней"
        
        # Проверка суммы процентов только если уровней больше одного
        if len(levels) > 1:
            total_volume = sum(level.get('volume_pct', 0) for level in levels)
            if abs(total_volume - 100) > 0.01:  # Допуск на погрешность
                return False, f"Сумма процентов должна быть 100%, сейчас {total_volume}%"
        
        # Проверка порядка уровней
        prev_level = 0
        for i, level in enumerate(levels):
            level_pct = level.get('level_pct', 0)
            if level_pct <= prev_level:
                return False, f"Уровни должны быть в порядке возрастания (уровень {i+1})"
            prev_level = level_pct
            
            # Проверка диапазонов
            if level_pct <= 0 or level_pct > 100:
                return False, f"Уровень цены должен быть от 0.1% до 100% (уровень {i+1})"
            
            volume_pct = level.get('volume_pct', 0)
            if volume_pct <= 0 or volume_pct > 100:
                return False, f"Объем должен быть от 1% до 100% (уровень {i+1})"
        
        return True, None
