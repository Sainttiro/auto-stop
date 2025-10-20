import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, Union
from dotenv import load_dotenv

from .settings import Config, InstrumentsConfig


def load_yaml_config(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Загрузка YAML конфигурации из файла"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file) or {}
    except Exception as e:
        print(f"Ошибка при загрузке конфигурации из {file_path}: {e}")
        return {}


def load_config(
    config_path: Optional[str] = None,
    instruments_path: Optional[str] = None
) -> tuple[Config, InstrumentsConfig]:
    """
    Загрузка основной конфигурации и конфигурации инструментов
    
    Args:
        config_path: Путь к основному файлу конфигурации
        instruments_path: Путь к файлу конфигурации инструментов
        
    Returns:
        tuple[Config, InstrumentsConfig]: Кортеж из основной конфигурации и конфигурации инструментов
    """
    # Загрузка переменных окружения из .env файла
    load_dotenv()
    
    # Определение путей к файлам конфигурации по умолчанию
    base_dir = Path(__file__).parent.parent.parent
    default_config_path = base_dir / "config" / "config.yaml"
    default_instruments_path = base_dir / "config" / "instruments.yaml"
    
    # Использование указанных путей или путей по умолчанию
    config_path = config_path or default_config_path
    instruments_path = instruments_path or default_instruments_path
    
    # Загрузка конфигураций из YAML файлов
    config_data = load_yaml_config(config_path)
    instruments_data = load_yaml_config(instruments_path)
    
    # Создание объектов конфигурации
    config = Config.model_validate(config_data)
    instruments_config = InstrumentsConfig.model_validate(instruments_data)
    
    # Получение токена API и ID чата из переменных окружения
    config.api.token = os.getenv(config.api.token_env, "")
    
    # Проверка наличия токена API
    if not config.api.token:
        raise ValueError(f"Токен API не найден в переменной окружения {config.api.token_env}")
    
    # Если настроен Telegram, получаем токен бота и ID чата
    if config.telegram:
        config.telegram.bot_token = os.getenv(config.telegram.bot_token_env, "")
        config.telegram.chat_id = os.getenv(config.telegram.chat_id_env, "")
    
    return config, instruments_config
