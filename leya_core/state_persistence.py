"""
leya_core/state_persistence.py — Сохранение и загрузка состояния Леи между сессиями.
"""

import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger("StatePersistence")


class StatePersistence:
    """Сохраняет и загружает состояние Леи из JSON файла."""
    
    def __init__(self, state_file: str = "./leya_brain/leya_state.json"):
        self.state_file = state_file
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Создает директорию для файла состояния."""
        directory = os.path.dirname(self.state_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
    
    def save_state(self, state: Dict[str, Any]) -> bool:
        """
        Сохраняет состояние в JSON файл.
        
        Args:
            state: Словарь с данными для сохранения
            
        Returns:
            True если успешно, False если ошибка
        """
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            logger.info(f"StatePersistence: Состояние сохранено в {self.state_file}")
            return True
        except Exception as e:
            logger.error(f"StatePersistence: Ошибка сохранения состояния: {e}")
            return False
    
    def load_state(self) -> Dict[str, Any]:
        """
        Загружает состояние из JSON файла.
        
        Returns:
            Словарь с загруженными данными или пустой словарь если файл не найден
        """
        if not os.path.exists(self.state_file):
            logger.info("StatePersistence: Файл состояния не найден, начинаем с чистого листа")
            return {}
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            logger.info(f"StatePersistence: Состояние загружено из {self.state_file}")
            return state
        except Exception as e:
            logger.error(f"StatePersistence: Ошибка загрузки состояния: {e}")
            return {}