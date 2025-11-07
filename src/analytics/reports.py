"""
Модуль для форматирования отчетов по статистике
"""

from typing import Dict, List
from datetime import datetime

from src.storage.models import OperationCache
from src.utils.logger import get_logger

logger = get_logger("analytics.reports")


class ReportFormatter:
    """
    Класс для форматирования отчетов
    """
    
    MONTH_NAMES_RU = {
        '01': 'Январь', '02': 'Февраль', '03': 'Март',
        '04': 'Апрель', '05': 'Май', '06': 'Июнь',
        '07': 'Июль', '08': 'Август', '09': 'Сентябрь',
        '10': 'Октябрь', '11': 'Ноябрь', '12': 'Декабрь'
    }
    
    def format_report(
        self,
        stats: Dict,
        period: str,
        start_year: int
    ) -> str:
        """
        Форматирование отчета
        
        Args:
            stats: Статистика
            period: Период (month, week, day)
            start_year: Год начала периода
            
        Returns:
            str: Отформатированный отчет
        """
        if not stats or not stats.get('total'):
            return "📊 Нет данных для отображения"
        
        report_lines = []
        
        # Заголовок
        report_lines.append(f"📊 СТАТИСТИКА С 01.01.{start_year}\n")
        
        # Статистика по периодам
        if stats.get('periods'):
            period_name = {
                'month': 'МЕСЯЦАМ',
                'week': 'НЕДЕЛЯМ',
                'day': 'ДНЯМ'
            }.get(period, 'ПЕРИОДАМ')
            
            report_lines.append(f"📅 ПО {period_name}:\n")
            
            # Сортировка периодов в обратном порядке (новые сверху)
            sorted_periods = sorted(stats['periods'].items(), reverse=True)
            
            for period_key, period_stats in sorted_periods[:10]:  # Топ-10 периодов
                period_label = self._format_period_label(period_key, period)
                report_lines.append(self._format_period_stats(period_label, period_stats))
        
        # Топ инструменты
        if stats.get('instruments'):
            report_lines.append("\n🏆 ТОП ИНСТРУМЕНТЫ:")
            
            top_instruments = list(stats['instruments'].items())[:10]
            for i, (ticker, inst_stats) in enumerate(top_instruments, 1):
                profit = inst_stats['profit']
                profit_sign = '+' if profit >= 0 else ''
                report_lines.append(
                    f"{i}. {ticker}: {profit_sign}{profit:,.0f}₽ "
                    f"({inst_stats['trades']} сделок)"
                )
        
        # Общая статистика
        total = stats['total']
        report_lines.append("\n💰 ИТОГО:")
        report_lines.append(f"├─ Всего сделок: {total['total_trades']}")
        report_lines.append(f"├─ Общий объем: {total['volume']:,.0f}₽")
        report_lines.append(f"├─ Комиссии: {total['commissions']:,.0f}₽")
        
        profit = total['profit']
        profit_sign = '+' if profit >= 0 else ''
        profit_emoji = '📈' if profit >= 0 else '📉'
        report_lines.append(
            f"├─ Прибыль: {profit_emoji} {profit_sign}{profit:,.0f}₽ "
            f"({profit_sign}{total['roi']:.1f}%)"
        )
        report_lines.append(
            f"└─ Винрейт: {total['winrate']:.1f}% "
            f"({total['profitable_trades']}/{total['sells']})"
        )
        
        return '\n'.join(report_lines)
    
    def _format_period_label(self, period_key: str, period: str) -> str:
        """
        Форматирование метки периода
        
        Args:
            period_key: Ключ периода (например, "2025-03")
            period: Тип периода
            
        Returns:
            str: Отформатированная метка
        """
        if period == 'month':
            year, month = period_key.split('-')
            month_name = self.MONTH_NAMES_RU.get(month, month)
            return f"{month_name} {year}"
        elif period == 'week':
            return f"Неделя {period_key}"
        else:  # day
            try:
                date = datetime.strptime(period_key, '%Y-%m-%d')
                return date.strftime('%d.%m.%Y')
            except:
                return period_key
    
    def _format_period_stats(self, label: str, stats: Dict) -> str:
        """
        Форматирование статистики периода
        
        Args:
            label: Метка периода
            stats: Статистика
            
        Returns:
            str: Отформатированная строка
        """
        profit = stats['profit']
        profit_sign = '+' if profit >= 0 else ''
        
        return (
            f"📅 {label}\n"
            f"├─ Сделок: {stats['total_trades']} "
            f"({stats['buys']} покупок, {stats['sells']} продаж)\n"
            f"├─ Объем: {stats['volume']:,.0f}₽\n"
            f"├─ Комиссии: {stats['commissions']:,.0f}₽\n"
            f"├─ Прибыль: {profit_sign}{profit:,.0f}₽ ({profit_sign}{stats['roi']:.1f}%)\n"
            f"└─ Винрейт: {stats['winrate']:.1f}% "
            f"({stats['profitable_trades']}/{stats['sells']})\n"
        )
    
    def format_instrument_report(
        self,
        stats: Dict,
        ticker: str,
        period: str,
        start_year: int
    ) -> str:
        """
        Форматирование отчета по инструменту
        
        Args:
            stats: Статистика
            ticker: Тикер инструмента
            period: Период
            start_year: Год начала периода
            
        Returns:
            str: Отформатированный отчет
        """
        if not stats or not stats.get('total'):
            return f"📊 Нет данных по {ticker}"
        
        report_lines = []
        report_lines.append(f"📊 СТАТИСТИКА ПО {ticker} ({start_year})\n")
        
        # Общая статистика
        total = stats['total']
        profit = total['profit']
        profit_sign = '+' if profit >= 0 else ''
        profit_emoji = '📈' if profit >= 0 else '📉'
        
        report_lines.append("💰 ИТОГО:")
        report_lines.append(f"├─ Сделок: {total['total_trades']}")
        report_lines.append(f"├─ Объем: {total['volume']:,.0f}₽")
        report_lines.append(f"├─ Комиссии: {total['commissions']:,.0f}₽")
        report_lines.append(
            f"├─ Прибыль: {profit_emoji} {profit_sign}{profit:,.0f}₽ "
            f"({profit_sign}{total['roi']:.1f}%)"
        )
        report_lines.append(
            f"└─ Винрейт: {total['winrate']:.1f}% "
            f"({total['profitable_trades']}/{total['sells']})"
        )
        
        return '\n'.join(report_lines)
    
    async def format_detailed_report(
        self,
        stats: Dict,
        operations: List[OperationCache],
        period: str,
        start_year: int,
        api_client=None,
        account_id: str = None
    ) -> str:
        """
        Форматирование детального отчета с информацией по каждой сделке
        
        Args:
            stats: Статистика
            operations: Список операций
            period: Период (month, week, day)
            start_year: Год начала периода
            api_client: API клиент для получения актуальных позиций (опционально)
            account_id: ID счета для получения позиций (опционально)
            
        Returns:
            str: Отформатированный отчет
        """
        if not stats or not stats.get('total'):
            return "📊 Нет данных для отображения"
        
        report_lines = []
        
        # Заголовок
        today = datetime.now().strftime('%d.%m.%Y')
        report_lines.append(f"📊 СТАТИСТИКА ЗА {today}\n")
        
        # Общая статистика
        total = stats['total']
        profit = total['profit']
        profit_sign = '+' if profit >= 0 else ''
        profit_emoji = '📈' if profit >= 0 else '📉'
        
        report_lines.append("📈 Общие показатели:")
        report_lines.append(f"├─ Сделок: {total['total_trades']} "
                           f"({total['buys']} покупок, {total['sells']} продаж)")
        report_lines.append(f"├─ Объем: {total['volume']:,.0f}₽")
        report_lines.append(f"├─ Комиссии: {total['commissions']:,.0f}₽")
        report_lines.append(
            f"├─ Прибыль: {profit_sign}{profit:,.0f}₽ ({profit_sign}{total['roi']:.1f}%)"
        )
        report_lines.append(
            f"└─ Винрейт: {total['winrate']:.1f}% "
            f"({total['profitable_trades']}/{total['sells']})"
        )
        
        # Детали по сделкам
        report_lines.append("\n📋 Детали по сделкам:")
        
        # Собираем все закрытые сделки (где есть yield_value и оно не равно 0)
        closed_trades = [op for op in operations if op.yield_value is not None and op.yield_value != 0]
        
        # Разделяем на прибыльные и убыточные
        profitable_trades = [op for op in closed_trades if op.yield_value > 0]
        losing_trades = [op for op in closed_trades if op.yield_value < 0]  # Строго меньше 0
        
        # Словарь для поиска соответствующих операций открытия позиции
        buys = {op.ticker: op for op in operations if 'BUY' in op.type and op.ticker}
        sells = {op.ticker: op for op in operations if 'SELL' in op.type and op.ticker}
        
        # Прибыльные сделки
        if profitable_trades:
            report_lines.append("\n✅ Прибыльные:")
            for op in profitable_trades:
                # Получаем информацию о ценах
                # Определяем тип операции для поиска соответствующей пары
                if 'SELL' in op.type:
                    # SELL операция (закрытие LONG) - ищем соответствующую BUY
                    price_info = self._get_price_info(op, buys.get(op.ticker))
                else:
                    # BUY операция (закрытие SHORT) - ищем соответствующую SELL
                    price_info = self._get_price_info(op, sells.get(op.ticker))
                
                report_lines.append(
                    f"• {op.ticker}: +{op.yield_value:,.2f}₽ {price_info}"
                )
        else:
            report_lines.append("\n✅ Прибыльные:\n(пусто)")
        
        # Убыточные сделки
        if losing_trades:
            report_lines.append("\n❌ Убыточные:")
            for op in losing_trades:
                # Получаем информацию о ценах
                if 'SELL' in op.type:
                    # SELL операция (закрытие LONG) - ищем соответствующую BUY
                    price_info = self._get_price_info(op, buys.get(op.ticker))
                else:
                    # BUY операция (закрытие SHORT) - ищем соответствующую SELL
                    price_info = self._get_price_info(op, sells.get(op.ticker))
                
                report_lines.append(
                    f"• {op.ticker}: {op.yield_value:,.2f}₽ {price_info}"
                )
        else:
            report_lines.append("\n❌ Убыточные:\n(пусто)")
        
        # Открытые позиции - получаем актуальные данные от брокера
        if api_client and account_id:
            open_positions = await self._get_actual_positions(api_client, account_id)
        else:
            # Fallback на расчет из операций
            open_positions = self._get_open_positions(operations)
        
        if open_positions:
            report_lines.append("\n⏳ Открытые позиции:")
            for ticker, position in open_positions.items():
                report_lines.append(
                    f"• {ticker}: {position['quantity']} лотов @ {position['price']:,.2f}"
                )
        
        return '\n'.join(report_lines)
    
    async def _get_actual_positions(self, api_client, account_id: str) -> Dict:
        """
        Получение актуальных позиций от брокера через API
        
        Использует комбинацию двух методов:
        - get_positions() для получения списка позиций с тикерами
        - get_portfolio() для получения средних цен позиций
        
        Args:
            api_client: API клиент
            account_id: ID счета
            
        Returns:
            Dict: Словарь позиций {ticker: {quantity, price}}
        """
        try:
            # 1. Получаем позиции с тикерами через get_positions
            positions_response = await api_client.get_positions(account_id)
            
            # 2. Получаем портфель для средних цен через get_portfolio
            portfolio = await api_client.get_portfolio(account_id)
            
            # Создаем словарь средних цен по FIGI
            prices_by_figi = {}
            for portfolio_pos in portfolio.positions:
                # Пропускаем закрытые позиции
                quantity_units = portfolio_pos.quantity.units
                quantity_nano = portfolio_pos.quantity.nano
                
                if quantity_units == 0 and quantity_nano == 0:
                    continue
                
                # Получаем среднюю цену
                avg_price = (portfolio_pos.average_position_price.units + 
                           portfolio_pos.average_position_price.nano / 1e9)
                
                prices_by_figi[portfolio_pos.figi] = avg_price
            
            # 3. Объединяем данные: тикеры из get_positions + цены из get_portfolio
            positions = {}
            for position in positions_response.securities:
                # Пропускаем закрытые позиции
                if position.balance == 0:
                    continue
                
                # Используем тикер напрямую из ответа API
                ticker = position.ticker
                quantity = position.balance
                
                # Получаем среднюю цену из портфеля по FIGI
                avg_price = prices_by_figi.get(position.figi, 0.0)
                
                positions[ticker] = {
                    'quantity': int(quantity),
                    'price': avg_price
                }
            
            logger.info(f"Получено {len(positions)} актуальных позиций от брокера")
            return positions
            
        except Exception as e:
            logger.error(f"Ошибка получения актуальных позиций от брокера: {e}", exc_info=True)
            # В случае ошибки возвращаем пустой словарь
            return {}
    
    def _get_price_info(self, closing_op: OperationCache, opening_op: OperationCache) -> str:
        """
        Получение информации о ценах входа/выхода
        
        Args:
            closing_op: Операция закрытия позиции (SELL для LONG, BUY для SHORT)
            opening_op: Операция открытия позиции (BUY для LONG, SELL для SHORT)
            
        Returns:
            str: Строка с информацией о ценах
        """
        if not closing_op.price:
            return ""
        
        closing_price = closing_op.price
        
        if opening_op and opening_op.price:
            opening_price = opening_op.price
            return f"({opening_price:.2f} → {closing_price:.2f})"
        
        return f"(цена выхода: {closing_price:.2f})"
    
    def _get_open_positions(self, operations: List[OperationCache]) -> Dict:
        """
        Получение открытых позиций из операций
        
        Args:
            operations: Список операций
            
        Returns:
            Dict: Словарь открытых позиций
        """
        positions = {}
        
        for op in operations:
            if not op.ticker or not op.quantity:
                continue
            
            ticker = op.ticker
            quantity = op.quantity
            
            if ticker not in positions:
                positions[ticker] = {
                    'quantity': 0,
                    'total_cost': 0,
                    'price': 0,
                    'direction': None
                }
            
            if 'BUY' in op.type:
                positions[ticker]['quantity'] += quantity
                if op.price and op.payment:
                    positions[ticker]['total_cost'] += abs(op.payment)
            elif 'SELL' in op.type:
                positions[ticker]['quantity'] -= quantity
                # Учитываем стоимость и для SELL операций (для корректного расчета средней цены SHORT позиций)
                if op.price and op.payment:
                    positions[ticker]['total_cost'] += abs(op.payment)
        
        # Обрабатываем открытые позиции и рассчитываем среднюю цену
        open_positions = {}
        for ticker, pos in positions.items():
            # Определяем направление позиции
            if pos['quantity'] > 0:
                pos['direction'] = 'LONG'
                pos['price'] = pos['total_cost'] / pos['quantity'] if pos['quantity'] > 0 else 0
                open_positions[ticker] = pos
            elif pos['quantity'] < 0:
                # SHORT позиция (отрицательное количество)
                pos['direction'] = 'SHORT'
                pos['quantity'] = abs(pos['quantity'])  # Абсолютное значение для отображения
                pos['price'] = pos['total_cost'] / pos['quantity'] if pos['quantity'] > 0 else 0
                open_positions[ticker] = pos
        
        return open_positions
