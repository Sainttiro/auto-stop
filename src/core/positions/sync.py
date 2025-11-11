"""
Синхронизация позиций с брокером
"""
from typing import Dict, Any
from decimal import Decimal

from src.api.client import TinkoffAPIClient
from src.api.instrument_info import InstrumentInfoCache
from src.storage.database import Database
from src.storage.models import Position
from src.utils.logger import get_logger
from src.core.positions.cache import PositionCache

logger = get_logger("core.positions.sync")


class PositionSynchronizer:
    """
    Синхронизация позиций с брокером
    
    Отвечает за синхронизацию позиций между системой и брокером,
    обработку расхождений и восстановление позиций при запуске.
    """
    
    def __init__(
        self,
        database: Database,
        position_cache: PositionCache,
        instrument_cache: InstrumentInfoCache
    ):
        """
        Инициализация синхронизатора позиций
        
        Args:
            database: Объект для работы с базой данных
            position_cache: Кэш позиций
            instrument_cache: Кэш информации об инструментах
        """
        self.db = database
        self.position_cache = position_cache
        self.instrument_cache = instrument_cache
    
    async def sync_from_broker(self, account_id: str, api_client: TinkoffAPIClient) -> int:
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
            # Запрашиваем текущие позиции через API (для тикеров)
            positions_response = await api_client.get_positions(account_id)
            
            # Запрашиваем портфель (для средних цен)
            portfolio = await api_client.get_portfolio(account_id)
            
            # Создаем словарь средних цен по FIGI
            avg_prices = {}
            for position in portfolio.positions:
                figi = position.figi
                if position.average_position_price:
                    avg_price = Decimal(str(position.average_position_price.units)) + \
                               Decimal(str(position.average_position_price.nano)) / Decimal(1_000_000_000)
                    avg_prices[figi] = avg_price
            
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
                    existing_position = await self.position_cache.get(account_id, figi)
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
                    
                    # Получаем среднюю цену из портфеля
                    avg_price = avg_prices.get(figi)
                    
                    if not avg_price or avg_price == 0:
                        logger.warning(
                            f"Средняя цена для {ticker} недоступна из API. "
                            f"Позиция НЕ будет синхронизирована. "
                            f"Она будет создана при первой сделке."
                        )
                        continue
                    
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
                    await self.position_cache.add(position)
                    
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
    
    async def detect_discrepancies(self, account_id: str, api_client: TinkoffAPIClient) -> Dict[str, Any]:
        """
        Обнаружение расхождений между позициями в системе и у брокера
        
        Args:
            account_id: ID счета
            api_client: Клиент API для запроса позиций
            
        Returns:
            Dict[str, Any]: Информация о расхождениях
        """
        logger.info(f"Проверка расхождений позиций для счета {account_id}")
        
        try:
            # Получаем позиции из брокера
            positions_response = await api_client.get_positions(account_id)
            
            # Получаем позиции из системы
            system_positions = await self.position_cache.get_all_for_account(account_id)
            
            # Создаем словарь позиций брокера для быстрого поиска
            broker_positions = {}
            for security in positions_response.securities:
                figi = security.figi
                balance = security.balance
                
                # Пропускаем позиции с нулевым балансом
                if balance == 0:
                    continue
                
                broker_positions[figi] = {
                    "quantity": balance,
                    "figi": figi
                }
            
            # Находим расхождения
            missing_in_system = []  # Есть у брокера, нет в системе
            missing_in_broker = []  # Есть в системе, нет у брокера
            quantity_mismatch = []  # Разное количество
            
            # Проверяем позиции брокера
            for figi, broker_pos in broker_positions.items():
                if figi not in system_positions:
                    missing_in_system.append(broker_pos)
                else:
                    system_qty = system_positions[figi].quantity
                    broker_qty = abs(broker_pos["quantity"])
                    
                    if system_qty != broker_qty:
                        quantity_mismatch.append({
                            "figi": figi,
                            "ticker": system_positions[figi].ticker,
                            "system_qty": system_qty,
                            "broker_qty": broker_qty
                        })
            
            # Проверяем позиции системы
            for figi, system_pos in system_positions.items():
                if figi not in broker_positions:
                    missing_in_broker.append({
                        "figi": figi,
                        "ticker": system_pos.ticker,
                        "quantity": system_pos.quantity
                    })
            
            # Формируем результат
            result = {
                "missing_in_system": missing_in_system,
                "missing_in_broker": missing_in_broker,
                "quantity_mismatch": quantity_mismatch,
                "has_discrepancies": bool(missing_in_system or missing_in_broker or quantity_mismatch)
            }
            
            if result["has_discrepancies"]:
                logger.warning(
                    f"Обнаружены расхождения позиций: "
                    f"{len(missing_in_system)} отсутствуют в системе, "
                    f"{len(missing_in_broker)} отсутствуют у брокера, "
                    f"{len(quantity_mismatch)} с разным количеством"
                )
            else:
                logger.info("Расхождений позиций не обнаружено")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при проверке расхождений позиций: {e}")
            return {
                "error": str(e),
                "has_discrepancies": False
            }
    
    async def resolve_discrepancies(self, account_id: str, api_client: TinkoffAPIClient) -> Dict[str, Any]:
        """
        Устранение расхождений между позициями в системе и у брокера
        
        Args:
            account_id: ID счета
            api_client: Клиент API для запроса позиций
            
        Returns:
            Dict[str, Any]: Результаты устранения расхождений
        """
        logger.info(f"Устранение расхождений позиций для счета {account_id}")
        
        try:
            # Получаем информацию о расхождениях
            discrepancies = await self.detect_discrepancies(account_id, api_client)
            
            if not discrepancies["has_discrepancies"]:
                logger.info("Нет расхождений для устранения")
                return {
                    "removed_from_db": 0,
                    "added_to_db": 0,
                    "updated_quantity": 0
                }
            
            removed_count = 0
            added_count = 0
            updated_count = 0
            
            # Синхронизируем отсутствующие в системе позиции
            for broker_pos in discrepancies["missing_in_system"]:
                try:
                    figi = broker_pos["figi"]
                    
                    # Получаем информацию об инструменте
                    instrument = await self.instrument_cache.get_instrument_by_figi(figi)
                    if not instrument:
                        logger.warning(f"Не удалось получить информацию об инструменте {figi}")
                        continue
                    
                    # Синхронизируем позицию
                    synced = await self.sync_from_broker(account_id, api_client)
                    if synced > 0:
                        added_count += synced
                    
                except Exception as e:
                    logger.error(f"Ошибка при синхронизации позиции {broker_pos['figi']}: {e}")
            
            # Закрываем позиции, отсутствующие у брокера
            for system_pos in discrepancies["missing_in_broker"]:
                try:
                    figi = system_pos["figi"]
                    ticker = system_pos["ticker"]
                    
                    # Получаем позицию из БД
                    position = await self.position_cache.get(account_id, figi)
                    if not position:
                        logger.warning(f"Позиция {ticker} ({figi}) не найдена в БД")
                        continue
                    
                    # Закрываем позицию
                    await self.db.delete(Position, position.id)
                    await self.position_cache.remove(account_id, figi)
                    
                    logger.info(f"Закрыта позиция {ticker} ({figi}), отсутствующая у брокера")
                    
                    # Логируем событие
                    await self.db.log_event(
                        event_type="POSITION_CLOSED_SYNC",
                        account_id=account_id,
                        figi=figi,
                        ticker=ticker,
                        description=f"Закрыта позиция {ticker}, отсутствующая у брокера",
                        details={
                            "quantity": system_pos["quantity"]
                        }
                    )
                    
                    removed_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка при закрытии позиции {system_pos['figi']}: {e}")
            
            # Обновляем позиции с разным количеством
            for mismatch in discrepancies["quantity_mismatch"]:
                try:
                    figi = mismatch["figi"]
                    ticker = mismatch["ticker"]
                    broker_qty = mismatch["broker_qty"]
                    
                    # Получаем позицию из БД
                    position = await self.position_cache.get(account_id, figi)
                    if not position:
                        logger.warning(f"Позиция {ticker} ({figi}) не найдена в БД")
                        continue
                    
                    # Обновляем количество
                    position.quantity = broker_qty
                    await self.db.update(Position, position.id, {"quantity": broker_qty})
                    await self.position_cache.update(position)
                    
                    logger.info(
                        f"Обновлена позиция {ticker} ({figi}), "
                        f"количество: {mismatch['system_qty']} -> {broker_qty}"
                    )
                    
                    # Логируем событие
                    await self.db.log_event(
                        event_type="POSITION_UPDATED_SYNC",
                        account_id=account_id,
                        figi=figi,
                        ticker=ticker,
                        description=f"Обновлена позиция {ticker}, количество: {mismatch['system_qty']} -> {broker_qty}",
                        details={
                            "old_quantity": mismatch["system_qty"],
                            "new_quantity": broker_qty
                        }
                    )
                    
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка при обновлении позиции {mismatch['figi']}: {e}")
            
            logger.info(f"Устранено {removed_count + added_count + updated_count} расхождений позиций")
            return {
                "removed_from_db": removed_count,
                "added_to_db": added_count,
                "updated_quantity": updated_count
            }
            
        except Exception as e:
            logger.error(f"Ошибка при устранении расхождений позиций: {e}")
            return {
                "error": str(e),
                "removed_from_db": 0,
                "added_to_db": 0,
                "updated_quantity": 0
            }
