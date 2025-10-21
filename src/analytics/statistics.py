"""
Модуль для расчета статистики по операциям
"""

from typing import List, Dict, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

from src.storage.models import OperationCache
from src.utils.logger import get_logger

logger = get_logger("analytics.statistics")


class StatisticsCalculator:
    """
    Класс для расчета статистики по операциям
    """
    
    def calculate_statistics(
        self,
        operations: List[OperationCache],
        period: str = "month"
    ) -> Dict:
        """
        Расчет статистики по операциям
        
        Args:
            operations: Список операций
            period: Период группировки (month, week, day)
            
        Returns:
            Dict: Статистика
        """
        if not operations:
            return {
                'total': self._empty_stats(),
                'periods': {},
                'instruments': {}
            }
        
        # Группировка по периодам
        periods_data = self._group_by_period(operations, period)
        
        # Статистика по периодам
        periods_stats = {}
        for period_key, ops in periods_data.items():
            periods_stats[period_key] = self._calculate_period_stats(ops)
        
        # Общая статистика
        total_stats = self._calculate_period_stats(operations)
        
        # Статистика по инструментам
        instruments_stats = self._calculate_instruments_stats(operations)
        
        return {
            'total': total_stats,
            'periods': periods_stats,
            'instruments': instruments_stats
        }
    
    def _group_by_period(
        self,
        operations: List[OperationCache],
        period: str
    ) -> Dict[str, List[OperationCache]]:
        """
        Группировка операций по периодам
        
        Args:
            operations: Список операций
            period: Период (month, week, day)
            
        Returns:
            Dict: Операции, сгруппированные по периодам
        """
        grouped = defaultdict(list)
        
        for op in operations:
            if period == "month":
                key = op.date.strftime("%Y-%m")
            elif period == "week":
                # ISO неделя
                key = op.date.strftime("%Y-W%W")
            else:  # day
                key = op.date.strftime("%Y-%m-%d")
            
            grouped[key].append(op)
        
        return dict(grouped)
    
    def _calculate_period_stats(self, operations: List[OperationCache]) -> Dict:
        """
        Расчет статистики за период
        
        Args:
            operations: Список операций
            
        Returns:
            Dict: Статистика
        """
        buys = [op for op in operations if 'BUY' in op.type]
        sells = [op for op in operations if 'SELL' in op.type]
        
        total_buys = len(buys)
        total_sells = len(sells)
        total_trades = total_buys + total_sells
        
        # Объем торгов
        volume = sum(abs(op.payment or 0) for op in operations)
        
        # Комиссии
        commissions = sum(abs(op.commission or 0) for op in operations)
        
        # Прибыль/убыток (из поля yield_value)
        profit = sum(op.yield_value or 0 for op in operations)
        
        # ROI
        roi = (profit / volume * 100) if volume > 0 else 0
        
        # Винрейт (упрощенно: продажи с прибылью)
        profitable_sells = len([op for op in sells if (op.yield_value or 0) > 0])
        winrate = (profitable_sells / total_sells * 100) if total_sells > 0 else 0
        
        return {
            'total_trades': total_trades,
            'buys': total_buys,
            'sells': total_sells,
            'volume': round(volume, 2),
            'commissions': round(commissions, 2),
            'profit': round(profit, 2),
            'roi': round(roi, 2),
            'winrate': round(winrate, 1),
            'profitable_trades': profitable_sells,
            'losing_trades': total_sells - profitable_sells
        }
    
    def _calculate_instruments_stats(
        self,
        operations: List[OperationCache]
    ) -> Dict[str, Dict]:
        """
        Расчет статистики по инструментам
        
        Args:
            operations: Список операций
            
        Returns:
            Dict: Статистика по инструментам
        """
        instruments = defaultdict(list)
        
        for op in operations:
            if op.ticker:
                instruments[op.ticker].append(op)
        
        stats = {}
        for ticker, ops in instruments.items():
            stats[ticker] = {
                'trades': len(ops),
                'volume': round(sum(abs(op.payment or 0) for op in ops), 2),
                'profit': round(sum(op.yield_value or 0 for op in ops), 2),
                'commissions': round(sum(abs(op.commission or 0) for op in ops), 2)
            }
        
        # Сортировка по прибыли
        sorted_stats = dict(
            sorted(stats.items(), key=lambda x: x[1]['profit'], reverse=True)
        )
        
        return sorted_stats
    
    def _empty_stats(self) -> Dict:
        """Пустая статистика"""
        return {
            'total_trades': 0,
            'buys': 0,
            'sells': 0,
            'volume': 0,
            'commissions': 0,
            'profit': 0,
            'roi': 0,
            'winrate': 0,
            'profitable_trades': 0,
            'losing_trades': 0
        }
