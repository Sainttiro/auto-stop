from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class OrderDirection(enum.Enum):
    """Направление ордера"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(enum.Enum):
    """Статус ордера"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderType(enum.Enum):
    """Тип ордера"""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class Position(Base):
    """Модель позиции"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True)
    account_id = Column(String(50), nullable=False, index=True)
    figi = Column(String(50), nullable=False, index=True)
    ticker = Column(String(50), nullable=False, index=True)
    instrument_type = Column(String(20), nullable=False)  # "stock" или "futures"
    quantity = Column(Integer, nullable=False)
    average_price = Column(Float, nullable=False)
    direction = Column(String(10), nullable=False)  # "LONG" или "SHORT"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связь с ордерами
    orders = relationship("Order", back_populates="position")
    
    def __repr__(self):
        return f"<Position(ticker={self.ticker}, quantity={self.quantity}, avg_price={self.average_price})>"


class Order(Base):
    """Модель ордера"""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True)
    order_id = Column(String(50), nullable=False, unique=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    account_id = Column(String(50), nullable=False, index=True)
    figi = Column(String(50), nullable=False, index=True)
    order_type = Column(String(20), nullable=False)  # "STOP", "STOP_LIMIT", "LIMIT", "MARKET"
    direction = Column(String(10), nullable=False)  # "BUY" или "SELL"
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=True)  # Может быть NULL для рыночных ордеров
    stop_price = Column(Float, nullable=True)  # Для стоп-ордеров
    status = Column(String(20), nullable=False, default="NEW")
    order_purpose = Column(String(20), nullable=False)  # "STOP_LOSS", "TAKE_PROFIT", "MULTI_TP_1", "MULTI_TP_2", ...
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связь с позицией
    position = relationship("Position", back_populates="orders")
    
    def __repr__(self):
        return f"<Order(order_id={self.order_id}, type={self.order_type}, purpose={self.order_purpose}, status={self.status})>"


class Trade(Base):
    """Модель исполненной сделки"""
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True)
    trade_id = Column(String(50), nullable=False, unique=True, index=True)
    order_id = Column(String(50), nullable=False, index=True)
    account_id = Column(String(50), nullable=False, index=True)
    figi = Column(String(50), nullable=False, index=True)
    ticker = Column(String(50), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # "BUY" или "SELL"
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)  # Общая сумма сделки
    commission = Column(Float, nullable=True)  # Комиссия
    trade_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Trade(trade_id={self.trade_id}, ticker={self.ticker}, price={self.price}, quantity={self.quantity})>"


class MultiTakeProfitLevel(Base):
    """Модель уровня многоуровневого тейк-профита"""
    __tablename__ = "multi_tp_levels"
    
    id = Column(Integer, primary_key=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    level_number = Column(Integer, nullable=False)  # Номер уровня (1, 2, 3, ...)
    price_level = Column(Float, nullable=False)  # Целевая цена
    volume_percent = Column(Float, nullable=False)  # Процент объема для закрытия
    is_triggered = Column(Boolean, default=False)  # Сработал ли уровень
    order_id = Column(String(50), nullable=True)  # ID ордера, если выставлен
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<MultiTakeProfitLevel(level={self.level_number}, price={self.price_level}, volume={self.volume_percent}%)>"


class SystemEvent(Base):
    """Модель системного события"""
    __tablename__ = "system_events"
    
    id = Column(Integer, primary_key=True)
    event_type = Column(String(50), nullable=False, index=True)
    account_id = Column(String(50), nullable=True, index=True)
    figi = Column(String(50), nullable=True, index=True)
    ticker = Column(String(50), nullable=True, index=True)
    description = Column(Text, nullable=True)
    details = Column(Text, nullable=True)  # JSON с деталями события
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<SystemEvent(type={self.event_type}, ticker={self.ticker}, created_at={self.created_at})>"


class Setting(Base):
    """Модель настроек системы"""
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Setting(key={self.key}, value={self.value[:50]}...)>"


class Account(Base):
    """Модель счета Tinkoff"""
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    token = Column(Text, nullable=False)  # Зашифрованный токен
    account_id = Column(String(50), nullable=False, index=True)
    is_active = Column(Boolean, default=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Account(name={self.name}, account_id={self.account_id}, active={self.is_active})>"


class OperationCache(Base):
    """Модель кэша операций из API"""
    __tablename__ = "operations_cache"
    
    id = Column(Integer, primary_key=True)
    operation_id = Column(String(100), nullable=False, unique=True, index=True)
    account_id = Column(String(50), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    type = Column(String(50), nullable=False)  # BUY, SELL, DIVIDEND, etc.
    state = Column(String(20), nullable=False)  # EXECUTED, CANCELED, PROGRESS
    instrument_uid = Column(String(50), nullable=True, index=True)
    ticker = Column(String(50), nullable=True, index=True)
    figi = Column(String(50), nullable=True, index=True)
    instrument_type = Column(String(20), nullable=True)  # stock, bond, futures, etc.
    quantity = Column(Integer, nullable=True)  # Количество в единицах
    price = Column(Float, nullable=True)  # Цена за 1 инструмент
    payment = Column(Float, nullable=True)  # Сумма операции
    commission = Column(Float, nullable=True)  # Комиссия
    yield_value = Column(Float, nullable=True)  # Доходность
    currency = Column(String(10), nullable=True)  # Валюта
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<OperationCache(operation_id={self.operation_id}, ticker={self.ticker}, type={self.type}, date={self.date})>"


class GlobalSettings(Base):
    """Глобальные настройки торговли (для всех инструментов по умолчанию)"""
    __tablename__ = "global_settings"
    
    id = Column(Integer, primary_key=True)
    account_id = Column(String(50), nullable=False, unique=True, index=True)
    
    # Базовые настройки SL/TP
    stop_loss_pct = Column(Float, default=0.4)  # Процент стоп-лосса
    take_profit_pct = Column(Float, default=1.0)  # Процент тейк-профита
    
    # Настройки активации SL/TP
    sl_activation_pct = Column(Float, nullable=True)  # Цена активации SL (в %)
    tp_activation_pct = Column(Float, nullable=True)  # Цена активации TP (в %)
    
    # Multi-TP настройки
    multi_tp_enabled = Column(Boolean, default=False)  # Включен ли Multi-TP
    multi_tp_levels = Column(Text, nullable=True)  # JSON с уровнями Multi-TP
    # Формат: [{"level_pct": 1.0, "volume_pct": 25, "sl_after_pct": -0.4}, ...]
    multi_tp_sl_strategy = Column(String(20), default="fixed")  # "fixed" или "custom"
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<GlobalSettings(account_id={self.account_id}, sl={self.stop_loss_pct}%, tp={self.take_profit_pct}%, multi_tp={self.multi_tp_enabled})>"


class InstrumentSettings(Base):
    """Индивидуальные настройки для конкретного инструмента (переопределяют глобальные)"""
    __tablename__ = "instrument_settings"
    
    id = Column(Integer, primary_key=True)
    account_id = Column(String(50), nullable=False, index=True)
    ticker = Column(String(50), nullable=False, index=True)
    figi = Column(String(50), nullable=True, index=True)
    
    # Базовые настройки SL/TP (NULL = использовать глобальные)
    stop_loss_pct = Column(Float, nullable=True)
    take_profit_pct = Column(Float, nullable=True)
    
    # Настройки активации SL/TP (NULL = использовать глобальные)
    sl_activation_pct = Column(Float, nullable=True)
    tp_activation_pct = Column(Float, nullable=True)
    
    # Multi-TP настройки (NULL = использовать глобальные)
    multi_tp_enabled = Column(Boolean, nullable=True)  # NULL, True, False
    multi_tp_levels = Column(Text, nullable=True)  # JSON с уровнями
    multi_tp_sl_strategy = Column(String(20), nullable=True)  # NULL, "fixed", "custom"
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('account_id', 'ticker', name='uix_account_ticker'),
    )
    
    def __repr__(self):
        return f"<InstrumentSettings(ticker={self.ticker}, account_id={self.account_id})>"
