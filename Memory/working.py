from collections import deque
from typing import List, Dict, Any
from Core.logger import log

class WorkingMemory:
    """
    Краткосрочная память (RAM мозга).
    Хранит недавние события, реплики и действия для формирования текущего контекста.
    """
    
    def __init__(self, capacity: int = 50):
        """
        :param capacity: Максимальное количество событий в памяти.
        """
        self.capacity = capacity
        self.buffer: deque = deque(maxlen=capacity)
        log.info("Working Memory initialized", capacity=capacity)

    def add(self, event: Dict[str, Any]):
        """Добавить событие в рабочую память"""
        # Можно добавить мета-информацию, например, время
        import time
        event["_wm_timestamp"] = time.time()
        self.buffer.append(event)
        
    def get_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """Получить N последних событий для передачи в LLM"""
        return list(self.buffer)[-n:]

    def get_all(self) -> List[Dict[str, Any]]:
        """Получить весь текущий буфер"""
        return list(self.buffer)

    def clear(self):
        """Очистить рабочую память (например, при смене контекста или "сне")"""
        self.buffer.clear()
        log.info("Working Memory cleared")
        
    def __len__(self):
        return len(self.buffer)