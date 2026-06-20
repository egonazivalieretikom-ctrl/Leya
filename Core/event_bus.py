import asyncio
from typing import Callable, Dict, List, Any
from collections import defaultdict
from Core.logger import log

class EventBus:
    """
    Асинхронная шина событий.
    Позволяет модулям Leya общаться друг с другом, не создавая жестких связей (coupling).
    
    Пример:
    - Модуль Vision публикует событие "object_detected".
    - Модуль Memory и Модуль Curiosity подписаны на "object_detected" и реагируют.
    """
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        log.debug("EventBus initialized")

    def subscribe(self, event_name: str, callback: Callable):
        """Подписать функцию на событие"""
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)
            log.debug(f"Subscribed to {event_name}", callback=callback.__name__)

    def unsubscribe(self, event_name: str, callback: Callable):
        """Отписать функцию от события"""
        if callback in self._subscribers[event_name]:
            self._subscribers[event_name].remove(callback)

    async def publish(self, event_name: str, data: Any = None):
        """Опубликовать событие и вызвать все подписанные функции"""
        log.debug("Publishing event", event_name=event_name, data_type=type(data).__name__)
        
        if event_name not in self._subscribers:
            return
            
        for callback in self._subscribers[event_name]:
            try:
                # Поддерживаем как синхронные, так и асинхронные коллбэки
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                log.error(
                    "Error in event callback", 
                    event=event_name, 
                    callback=callback.__name__, 
                    error=str(e)
                )

# Глобальный экземпляр шины событий для использования во всем проекте
event_bus = EventBus()