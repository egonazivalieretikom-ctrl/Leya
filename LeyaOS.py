import asyncio
from Core.logger import setup_logging

# Явные импорты — самый надёжный способ
from Core.state import LeyaState
from Core.event_bus import event_bus
from Core.brain import Brain
from Core.homeostasis import HomeostaticEngine
from Core.embodiment import EmbodimentSystem
from Core.continuity import ContinuitySystem
from Core.emotion_core import EmotionCore
from Core.emotional_snn import EmotionalSNN

from Cognition.manager import CognitionManager
from Memory.vector_memory import VectorMemory
from UI.server import UIServer
from Core.cognitive_cycle import CognitiveCycle

logger = setup_logging()

class LeyaOS:
    def __init__(self):
        self.state = LeyaState()
        self.event_bus = EventBus()
        self.brain = None

    async def initialize(self):
        logger.info("🚀 Starting Leya OS v1.0 - Full Integration")

        self.brain = Brain()
        self.brain.state = self.state
        self.brain.event_bus = self.event_bus

        # Инициализация всех модулей
        self.homeostasis = HomeostaticEngine(self.state, self.event_bus)
        self.embodiment = EmbodimentSystem(self.state, self.event_bus)
        self.continuity = ContinuitySystem(self.state, self.event_bus)
        self.cognition = CognitionManager(self.state, self.event_bus)
        self.snn = EmotionalSNN(self.state, self.event_bus)
        self.emotion_core = EmotionCore(self.state, self.event_bus, self.snn)
        self.memory = VectorMemory(self.state, self.event_bus)
        self.ui = UIServer(self.state, self.event_bus)

        await self.brain.initialize()
        await self.cognition.initialize()
        await self.snn.initialize()
        await self.memory.initialize()

        logger.info("✅ All subsystems successfully initialized and connected")

    async def run(self):
        await self.initialize()
        
        # Запуск UI сервера
        ui_task = asyncio.create_task(self.ui.start())
        
        # Запуск основного когнитивного цикла
        cycle = CognitiveCycle(self.brain)
        await cycle.start()

        # Ожидание всех задач
        await asyncio.gather(ui_task, return_exceptions=True)

    async def shutdown(self):
        await self.event_bus.stop()
        logger.info("🛑 Leya OS shutdown completed gracefully")


async def main():
    leya = LeyaOS()
    try:
        await leya.run()
    except KeyboardInterrupt:
        await leya.shutdown()
    except Exception as e:
        logger.critical("Critical failure in Leya OS", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())