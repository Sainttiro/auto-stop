from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from typing import Dict, List, Optional, Union, Literal
from decimal import Decimal


class TelegramSettings(BaseModel):
    """Настройки Telegram-уведомлений"""
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "TELEGRAM_CHAT_ID"
    bot_token: str = ""  # Будет заполнено из переменной окружения
    chat_id: str = ""    # Будет заполнено из переменной окружения
    notifications: List[str] = Field(
        default_factory=lambda: [
            "trade_executed",
            "order_placed",
            "stop_triggered",
            "errors"
        ]
    )


class ApiSettings(BaseModel):
    """Настройки API Tinkoff Invest"""
    token_env: str = "TINKOFF_TOKEN"
    token: str = ""  # Будет заполнено из переменной окружения
    app_name: str = "AutoStopSystem"


class MultiTakeProfitLevel(BaseModel):
    """Уровень многоуровневого тейк-профита"""
    level_pct: float
    volume_pct: float


class MultiTakeProfitSettings(BaseModel):
    """Настройки многоуровневого тейк-профита"""
    enabled: bool = False
    levels: List[MultiTakeProfitLevel] = Field(default_factory=list)


class StockSettings(BaseModel):
    """Настройки для акций"""
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 5.0


class FuturesSettings(BaseModel):
    """Настройки для фьючерсов"""
    stop_loss_steps: Optional[int] = 10  # Для обратной совместимости
    take_profit_steps: Optional[int] = 30  # Для обратной совместимости
    stop_loss_pct: Optional[float] = 2.0  # Новый подход - в процентах
    take_profit_pct: Optional[float] = 5.0  # Новый подход - в процентах


class DefaultSettings(BaseModel):
    """Настройки по умолчанию"""
    stocks: StockSettings = Field(default_factory=StockSettings)
    futures: FuturesSettings = Field(default_factory=FuturesSettings)


class LoggingSettings(BaseModel):
    """Настройки логирования"""
    level: str = "INFO"
    file: str = "logs/system.log"
    max_bytes: int = 10485760  # 10MB
    backup_count: int = 5


class InstrumentMultiTP(BaseModel):
    """Настройки многоуровневого TP для инструмента"""
    enabled: bool = True
    levels: List[MultiTakeProfitLevel]


class InstrumentSettings(BaseModel):
    """Настройки для конкретного инструмента"""
    type: Literal["stock", "futures"]
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    stop_loss_steps: Optional[int] = None
    take_profit_steps: Optional[int] = None
    multi_tp: Optional[InstrumentMultiTP] = None


class Config(BaseSettings):
    """Основная конфигурация приложения"""
    api: ApiSettings = Field(default_factory=ApiSettings)
    default_settings: DefaultSettings = Field(default_factory=DefaultSettings)
    multi_take_profit: MultiTakeProfitSettings = Field(default_factory=MultiTakeProfitSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    account_id: str = ""


class InstrumentsConfig(BaseModel):
    """Конфигурация инструментов"""
    instruments: Dict[str, InstrumentSettings] = Field(default_factory=dict)
