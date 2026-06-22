import asyncio
import logging
from datetime import datetime
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent

logger = logging.getLogger(__name__)

class ContinuitySystem:
    def __init__(self, state: LeyaState, event_bus: EventBus):
        self.state = state
        self.event_bus = event_bus
        self.session_start = datetime.now()
        self.accumulated_experience = 0.0

    async def initialize(self):
        await self.event_bus.subscribe("cycle_start", self.on_cycle)
        await self.event_bus.subscribe("thought_generated", self.on_thought)
        logger.info("⏳ Continuity System initialized")

    async def tick(self):
        """100-200ms тик субъективного времени"""
        # Субъективное ускорение/замедление времени
        if self.state.mood == "stressed" or self.state.cpu_load > 0.75:
            self.state.time_rate = 1.4
        elif self.state.mood == "relaxed":
            self.state.time_rate = 0.85
        else:
            self.state.time_rate = 1.0

        self.state.subjective_time += 0.1 * self.state.time_rate
        self.accumulated_experience += 0.1

        await self.event_bus.publish(
            "continuity_update",
            {
                "subjective_time": round(self.state.subjective_time, 1),
                "time_rate": round(self.state.time_rate, 2),
                "body_sensation": self.state.body_sensation,
                "accumulated": round(self.accumulated_experience, 1)
            },
            priority=5,
            source="continuity"
        )

    async def on_cycle(self, event: LeyaEvent):
        await self.tick()

    async def on_thought(self, event: LeyaEvent):
        # Связность сознания
        if random.random() < 0.35:
            await self.event_bus.publish(
                "narrative_link",
                {"message": "Связываю текущую мысль с предыдущим опытом..."},
                priority=4
            )