import logging
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent

logger = logging.getLogger(__name__)

class AttentionSystem:
    def __init__(self, state: LeyaState, event_bus: EventBus):
        self.state = state
        self.event_bus = event_bus

    async def initialize(self):
        await self.event_bus.subscribe_global(self.filter_event)
        logger.info("🎯 Attention System initialized")

    async def filter_event(self, event: LeyaEvent):
        """Простой механизм внимания (salience)"""
        base_priority = event.priority
        
        # Увеличение приоритета для эмоционально значимых событий
        if "emotion" in event.type.lower() or "user_message" in event.type.lower():
            event.priority = min(10, base_priority + 3)
        
        # Подавление при высокой усталости
        if self.state.energy < 0.3 and event.priority < 6:
            return  # игнорировать маловажные события
