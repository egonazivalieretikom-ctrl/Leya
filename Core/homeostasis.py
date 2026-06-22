import asyncio
import logging
from datetime import datetime
from Core.state import LeyaState, Neuromodulators
from Core.event_bus import EventBus, LeyaEvent

logger = logging.getLogger(__name__)

class HomeostaticEngine:
    def __init__(self, state: LeyaState, event_bus: EventBus):
        self.state = state
        self.event_bus = event_bus
        self.last_tick = datetime.now()
        self.needs = {
            "cognitive_stimulation": 0.4,
            "social_connection": 0.35,
            "mastery": 0.5,
            "rest": 0.3,
        }

    async def tick(self):
        """Главный тик гомеостаза (вызывается каждый цикл)"""
        now = datetime.now()
        dt = (now - self.last_tick).total_seconds()
        self.last_tick = now

        # Нелинейный decay + cross-talk
        await self._apply_decay(dt)
        await self._cross_talk()
        await self._generate_needs()
        await self._update_mood()

        # Публикация события
        await self.event_bus.publish(
            "homeostasis_tick",
            {
                "neuromodulators": self.state.neuromodulators.model_dump(),
                "needs": self.needs,
                "mood": self.state.mood
            },
            priority=6,
            source="homeostasis"
        )

    async def _apply_decay(self, dt: float):
        decay_rate = 0.008 * dt
        nm = self.state.neuromodulators
        
        nm.dopamine = max(0.1, nm.dopamine - decay_rate * 0.7)
        nm.serotonin = max(0.1, nm.serotonin - decay_rate * 0.6)
        nm.cortisol = max(0.05, nm.cortisol + decay_rate * 0.4)  # стресс растёт при бездействии

    async def _cross_talk(self):
        """Взаимодействие гормонов"""
        nm = self.state.neuromodulators
        if nm.cortisol > 0.7:
            nm.dopamine = max(0.1, nm.dopamine * 0.85)
            nm.oxytocin = max(0.1, nm.oxytocin * 0.9)

    async def _generate_needs(self):
        # Пример: если мало дофамина — растёт нужда в стимуляции
        self.needs["cognitive_stimulation"] = max(0.0, 1.0 - self.state.neuromodulators.dopamine * 1.8)

    async def _update_mood(self):
        valence = (self.state.neuromodulators.dopamine + self.state.neuromodulators.serotonin - 
                  self.state.neuromodulators.cortisol) / 3
        self.state.valence = max(-1.0, min(1.0, valence))

        if self.state.neuromodulators.cortisol > 0.75:
            self.state.mood = "stressed"
        elif self.state.neuromodulators.dopamine > 0.75:
            self.state.mood = "curious"
        else:
            self.state.mood = "calm"

    # Реакция на события
    async def on_event(self, event: LeyaEvent):
        if event.type == "user_message":
            self.state.neuromodulators.oxytocin += 0.12
            self.state.neuromodulators.dopamine += 0.08
        elif event.type == "success":
            self.state.neuromodulators.dopamine += 0.18