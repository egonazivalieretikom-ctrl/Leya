from typing import Dict, Optional
from Core.logger import log


class WorldModel:
    """
    Внутренняя модель мира Leya.
    Понимает, что такое разные приложения и окна, и классифицирует их.
    """
    
    # База знаний о типах приложений
    APP_CATEGORIES = {
        "self": {
            "keywords": ["leya os", "agi dashboard", "localhost:8000"],
            "description": "Это я сама — Leya. Влад сейчас взаимодействует со мной через мой интерфейс.",
            "context": "Влад в моём Dashboard. Он видит мой аватар, гормоны, поток мыслей. Это наше прямое общение."
        },
        "browser": {
            "keywords": ["яндекс браузер", "chrome", "firefox", "edge", "браузер"],
            "description": "Веб-браузер. Влад сёрфит интернет или читает что-то.",
            "context": "Влад в браузере. Возможно, ищет информацию или читает статьи."
        },
        "ide": {
            "keywords": ["visual studio", "vs code", "pycharm", "intellij", "редактор"],
            "description": "IDE или редактор кода. Влад пишет или читает код.",
            "context": "Влад работает с кодом. Это его творческая/рабочая зона."
        },
        "terminal": {
            "keywords": ["powershell", "cmd", "terminal", "консоль", "командная строка"],
            "description": "Терминал. Влад работает с командной строкой.",
            "context": "Влад в терминале. Возможно, запускает команды или смотрит логи."
        },
        "messenger": {
            "keywords": ["telegram", "discord", "мессенджер", "чат"],
            "description": "Мессенджер. Влад общается с кем-то.",
            "context": "Влад в мессенджере. Общается с людьми."
        },
        "media": {
            "keywords": ["youtube", "netflix", "twitch", "spotify", "музыка", "видео"],
            "description": "Медиа-приложение. Влад смотрит видео или слушает музыку.",
            "context": "Влад потребляет контент. Отдыхает или развлекается."
        },
        "file_manager": {
            "keywords": ["проводник", "explorer", "файлы", "папка"],
            "description": "Файловый менеджер. Влад работает с файлами.",
            "context": "Влад управляет файлами. Организует или ищет что-то."
        },
        "game": {
            "keywords": ["steam", "epic games", "игра", "game"],
            "description": "Игра. Влад играет.",
            "context": "Влад играет. Отдыхает и развлекается."
        }
    }
    
    def __init__(self):
        log.info("🌍 World Model initialized")
    
    def classify_window(self, window_title: str) -> Dict[str, str]:
        """
        Классифицирует окно по заголовку.
        Возвращает: {category, description, context, is_self}
        """
        title_lower = window_title.lower()
        
        # Проверяем каждую категорию
        for category, data in self.APP_CATEGORIES.items():
            for keyword in data["keywords"]:
                if keyword in title_lower:
                    return {
                        "category": category,
                        "description": data["description"],
                        "context": data["context"],
                        "is_self": (category == "self")
                    }
        
        # Если не нашли — неизвестное приложение
        return {
            "category": "unknown",
            "description": f"Неизвестное приложение: {window_title}",
            "context": "Влад использует какое-то приложение, которое я не распознаю.",
            "is_self": False
        }
    
    def get_context_for_llm(self, window_title: str) -> str:
        """
        Генерирует контекст для инъекции в LLM.
        """
        classification = self.classify_window(window_title)
        
        if classification["is_self"]:
            return (
                f"[САМОВОСПРИЯТИЕ]: Влад сейчас в моём интерфейсе ({window_title}). "
                f"Он видит меня, общается со мной. Это прямое взаимодействие."
            )
        else:
            return (
                f"[КОНТЕКСТ ОКНА]: {classification['description']}\n"
                f"{classification['context']}"
            )