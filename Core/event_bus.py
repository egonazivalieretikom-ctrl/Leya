import asyncio
import logging
from typing import Callable, Dict, Any, Set, Optional
from dataclasses import dataclass
from datetime import datetime

logger = setup_logging()

class LeyaOS:
    def __init__(self):
        self.state = LeyaState()
        self.brain = Brain()

    async def initialize(self):
        logger.info("🚀 Leya OS v1.0 — Starting full initialization...")

        self.brain.state = self.state
        self.brain.event_bus = event_bus

        # Создаём модули
        self.homeostasis = HomeostaticEngine(self.state, event_bus)
        self.embodiment = EmbodimentSystem(self.state, event_bus)
        self.continuity = ContinuitySystem(self.state, event_bus)
        self.cognition = CognitionManager(self.state, event_bus)
        self.snn = EmotionalSNN(self.state, event_bus)
        self.emotion_core = EmotionCore(self.state, event_bus, self.snn)
        self.memory = VectorMemory(self.state, event_bus)
        self.ui = UIServer(self.state, event_bus)

        # Инициализация
        await self.brain.initialize()
        await self.cognition.initialize()
        await self.snn.initialize()
        await self.memory.initialize()

        logger.info("✅ Leya OS fully initialized and connected!")

    async def run(self):
        await self.initialize()
        
        ui_task = asyncio.create_task(self.ui.start())
        cycle = CognitiveCycle(self.brain)
        
        try:
            await asyncio.gather(ui_task, cycle.start(), return_exceptions=True)
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self):
        await event_bus.stop()
        logger.info("🛑 Leya OS shutdown completed.")

async def main():
    leya = LeyaOS()
    try:
        await leya.run()
    except KeyboardInterrupt:
        await leya.shutdown()
    except Exception as e:
        logger.critical("Fatal error", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())

event_bus: EventBus = EventBus()