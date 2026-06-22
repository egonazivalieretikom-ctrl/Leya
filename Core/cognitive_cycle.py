import asyncio
import logging
from Core.state import LeyaState
from Core.event_bus import EventBus
from Core.brain import Brain

logger = logging.getLogger(__name__)

class CognitiveCycle:
    def __init__(self, brain: Brain):
        self.brain = brain
        self.state = brain.state
        self.event_bus = brain.event_bus
        self.interval = 2.0
        self.running = False

    async def start(self):
        if self.running:
            return
        self.running = True
        logger.info("🔄 Cognitive Cycle started (v1.0 - Thalamus + Full Integration)")

        while self.running:
            try:
                self.state.cycle_count += 1
                
                await self.event_bus.publish("cycle_start", {
                    "cycle": self.state.cycle_count,
                    "energy": self.state.energy,
                    "mood": self.state.mood
                }, priority=8)

                # === Основные фазы цикла ===
                await self._perception_phase()
                await self.brain.homeostasis.tick()
                await self.brain.cognition_manager.think()
                await self._action_phase()
                await self._reflection_phase()

                await asyncio.sleep(self.interval)

            except Exception as e:
                logger.error("Critical cycle failure", exc_info=True)
                self.state.error_streak += 1
                await asyncio.sleep(5.0)

    async def _perception_phase(self):
        await self.event_bus.publish("perception_tick", {"active": True}, priority=6)

    async def _action_phase(self):
        # Пока заглушка — будет расширяться
        pass

    async def _reflection_phase(self):
        if self.state.cycle_count % 3 == 0:
            await self.event_bus.publish("reflection", {
                "cycle": self.state.cycle_count,
                "summary": self.state.get_emotional_summary()
            }, priority=5)

    async def stop(self):
        self.running = False