"""
Проверка условий активации стоп-лоссов и тейк-профитов
"""
from typing import Dict, Any, Tuple, Optional
from decimal import Decimal

from src.storage.database import Database
from src.storage.models import Position
from src.core.utils.price_calculator import calculate_activation_prices
from src.utils.logger import get_logger

logger = get_logger("core.streams.activation_checker")


class ActivationChecker:
    """
    Проверка условий активации стоп-лоссов и тейк-профитов
    """
    
    def __init__(self, db: Database):
        """
        Инициализация проверки активации
        
        Args:
            db: Объект для работы с базой данных
        """
        self.db = db
        
        # Словарь для отслеживания позиций, ожидающих активации
        # Формат: {figi: {'position_id': id, 'sl_activation_price': price, 'tp_activation_price': price, 'sl_activated': bool, 'tp_activated': bool}}
        self._pending_activations: Dict[str, Dict[str, Any]] = {}
    
    def add_pending_activation(
        self,
        figi: str,
        position_id: int,
        sl_activation_price: Optional[float],
        tp_activation_price: Optional[float]
    ) -> None:
        """
        Добавление позиции в список ожидающих активации
        
        Args:
            figi: FIGI инструмента
            position_id: ID позиции
            sl_activation_price: Цена активации стоп-лосса
            tp_activation_price: Цена активации тейк-профита
        """
        self._pending_activations[figi] = {
            'position_id': position_id,
            'sl_activation_price': sl_activation_price,
            'tp_activation_price': tp_activation_price,
            'sl_activated': False,
            'tp_activated': False
        }
    
    def remove_pending_activation(self, figi: str) -> None:
        """
        Удаление позиции из списка ожидающих активации
        
        Args:
            figi: FIGI инструмента
        """
        if figi in self._pending_activations:
            del self._pending_activations[figi]
    
    def get_pending_activations(self) -> Dict[str, Dict[str, Any]]:
        """
        Получение списка позиций, ожидающих активации
        
        Returns:
            Dict[str, Dict[str, Any]]: Словарь позиций, ожидающих активации
        """
        return self._pending_activations.copy()
    
    def is_pending_activation(self, figi: str) -> bool:
        """
        Проверка, ожидает ли позиция активации
        
        Args:
            figi: FIGI инструмента
            
        Returns:
            bool: True, если позиция ожидает активации
        """
        return figi in self._pending_activations
    
    def get_activation_status(self, figi: str) -> Tuple[bool, bool]:
        """
        Получение статуса активации для позиции
        
        Args:
            figi: FIGI инструмента
            
        Returns:
            Tuple[bool, bool]: (sl_activated, tp_activated)
        """
        if figi not in self._pending_activations:
            return True, True  # Если нет в списке ожидающих, считаем активированными
        
        return (
            self._pending_activations[figi]['sl_activated'],
            self._pending_activations[figi]['tp_activated']
        )
    
    async def check_activation_conditions(
        self,
        figi: str,
        current_price: Decimal,
        position: Position,
        settings: Dict[str, Any]
    ) -> Tuple[bool, bool]:
        """
        Проверка условий активации SL/TP
        
        Args:
            figi: FIGI инструмента
            current_price: Текущая цена
            position: Позиция
            settings: Настройки инструмента
            
        Returns:
            Tuple[bool, bool]: (sl_activated, tp_activated)
        """
        sl_activation_pct = settings.get('sl_activation_pct')
        tp_activation_pct = settings.get('tp_activation_pct')
        
        # Если нет настроек активации, считаем что активировано сразу
        if sl_activation_pct is None and tp_activation_pct is None:
            return True, True
        
        # instrument_cache должен быть передан в метод или в конструктор
        instrument_cache = None
        
        # Получаем цены активации
        sl_activation_price, tp_activation_price = await calculate_activation_prices(
            avg_price=Decimal(str(position.average_price)),
            direction=position.direction,
            sl_activation_pct=sl_activation_pct,
            tp_activation_pct=tp_activation_pct,
            figi=figi,
            instrument_cache=instrument_cache
        )
        
        # Проверяем активацию SL
        sl_activated = True  # По умолчанию активировано, если нет настроек активации
        if sl_activation_price is not None:
            if position.direction == "LONG":
                # Для LONG: активация SL когда цена падает ниже уровня активации
                sl_activated = current_price <= sl_activation_price
            else:  # SHORT
                # Для SHORT: активация SL когда цена растет выше уровня активации
                sl_activated = current_price >= sl_activation_price
        
        # Проверяем активацию TP
        tp_activated = True  # По умолчанию активировано, если нет настроек активации
        if tp_activation_price is not None:
            if position.direction == "LONG":
                # Для LONG: активация TP когда цена растет выше уровня активации
                tp_activated = current_price >= tp_activation_price
            else:  # SHORT
                # Для SHORT: активация TP когда цена падает ниже уровня активации
                tp_activated = current_price <= tp_activation_price
        
        # Логируем активацию
        if sl_activated and sl_activation_price is not None:
            logger.info(
                f"🔔 SL для {position.ticker} активирован! "
                f"Цена активации: {sl_activation_price}, текущая цена: {current_price}"
            )
            
            # Логируем событие
            await self.db.log_event(
                event_type="SL_ACTIVATED",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"SL для {position.ticker} активирован",
                details={
                    "activation_price": float(sl_activation_price),
                    "current_price": float(current_price),
                    "position_id": position.id
                }
            )
        
        if tp_activated and tp_activation_price is not None:
            logger.info(
                f"🔔 TP для {position.ticker} активирован! "
                f"Цена активации: {tp_activation_price}, текущая цена: {current_price}"
            )
            
            # Логируем событие
            await self.db.log_event(
                event_type="TP_ACTIVATED",
                account_id=position.account_id,
                figi=position.figi,
                ticker=position.ticker,
                description=f"TP для {position.ticker} активирован",
                details={
                    "activation_price": float(tp_activation_price),
                    "current_price": float(current_price),
                    "position_id": position.id
                }
            )
        
        # Обновляем статус активации в словаре
        if figi in self._pending_activations:
            if sl_activated:
                self._pending_activations[figi]['sl_activated'] = True
            if tp_activated:
                self._pending_activations[figi]['tp_activated'] = True
        
        return sl_activated, tp_activated
