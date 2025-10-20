from decimal import Decimal
from tinkoff.invest import Quotation, MoneyValue


def quotation_to_decimal(quotation: Quotation) -> Decimal:
    """
    Конвертирует Quotation в Decimal
    
    Args:
        quotation: Объект Quotation из API Tinkoff
        
    Returns:
        Decimal: Значение в виде Decimal
    """
    if quotation is None:
        return Decimal(0)
    
    return Decimal(quotation.units) + Decimal(quotation.nano) / Decimal(1_000_000_000)


def decimal_to_quotation(value: Decimal) -> Quotation:
    """
    Конвертирует Decimal в Quotation
    
    Args:
        value: Значение в виде Decimal
        
    Returns:
        Quotation: Объект Quotation для API Tinkoff
    """
    units = int(value)
    nano = int((value - Decimal(units)) * Decimal(1_000_000_000))
    return Quotation(units=units, nano=nano)


def money_value_to_decimal(money_value: MoneyValue) -> Decimal:
    """
    Конвертирует MoneyValue в Decimal
    
    Args:
        money_value: Объект MoneyValue из API Tinkoff
        
    Returns:
        Decimal: Значение в виде Decimal
    """
    if money_value is None:
        return Decimal(0)
    
    return Decimal(money_value.units) + Decimal(money_value.nano) / Decimal(1_000_000_000)


def decimal_to_money_value(value: Decimal, currency: str = "rub") -> MoneyValue:
    """
    Конвертирует Decimal в MoneyValue
    
    Args:
        value: Значение в виде Decimal
        currency: Валюта (по умолчанию "rub")
        
    Returns:
        MoneyValue: Объект MoneyValue для API Tinkoff
    """
    units = int(value)
    nano = int((value - Decimal(units)) * Decimal(1_000_000_000))
    return MoneyValue(units=units, nano=nano, currency=currency)


def round_to_step(value: Decimal, min_step: Decimal) -> Decimal:
    """
    Округляет значение до ближайшего шага цены
    
    Args:
        value: Исходное значение
        min_step: Минимальный шаг цены инструмента
        
    Returns:
        Decimal: Округленное значение
    """
    if min_step == Decimal(0):
        return value
    
    return Decimal(round(value / min_step)) * min_step
