"""
leya_core/state_persistence.py — Сохранение и загрузка состояния Леи между сессиями.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("StatePersistence")


class StatePersistence:
    """Сохраняет и загружает состояние Леи из JSON файла."""
    
    def __init__(self, state_file: str = "./leya_brain/leya_state.json"):
        self.state_file = state_file
        self._ensure_directory()
    
    def _ensure_directory(self):
        directory = os.path.dirname(self.state_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
    
    def save_state(self, state: Dict[str, Any]) -> bool:
        """Сохраняет состояние в JSON файл."""
        try:
            state["_saved_at"] = datetime.now().isoformat()
            
            # Создаём резервную копию предыдущего состояния
            if os.path.exists(self.state_file):
                backup_path = self.state_file + ".backup"
                try:
                    os.replace(self.state_file, backup_path)
                except Exception:
                    pass
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            
            logger.info(f"StatePersistence: Состояние сохранено ({os.path.getsize(self.state_file)} байт)")
            return True
        
        except Exception as e:
            logger.error(f"StatePersistence: Ошибка сохранения: {e}")
            return False
    
    def load_state(self) -> Dict[str, Any]:
        """Загружает состояние из JSON файла."""
        if not os.path.exists(self.state_file):
            # Пробуем загрузить из резервной копии
            backup_path = self.state_file + ".backup"
            if os.path.exists(backup_path):
                logger.info("StatePersistence: Основной файл не найден, загружаем из резервной копии")
                self.state_file = backup_path
            else:
                logger.info("StatePersistence: Файл состояния не найден, начинаем с чистого листа")
                return {}
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            saved_at = state.get("_saved_at", "неизвестно")
            logger.info(f"StatePersistence: Состояние загружено (сохранено: {saved_at})")
            return state
        
        except Exception as e:
            logger.error(f"StatePersistence: Ошибка загрузки: {e}")
            return {}