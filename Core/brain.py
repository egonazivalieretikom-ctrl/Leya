import asyncio
from typing import Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Core.cognitive_cycle import CognitiveCycle

class Brain:
    """
    Главный координатор Leya.
    Инициализирует подсистемы и управляет жизненным циклом.
    """
    
    def __init__(self):
        self.state = LeyaState()
        self.cycle = CognitiveCycle(self.state)
        self.is_running = False
        
        # Подсистемы (будут импортированы позже)
        self.perception = None
        self.cognition = None
        self.action = None
        self.memory = None
        
        log.info("🧠 Brain initialized")

    def _load_subsystems(self):
        """
        Динамическая загрузка подсистем.
        Используем try/except, чтобы Leya могла работать даже если какие-то модули отсутствуют.
        """
        log.info("Loading subsystems...")
        
        # Память
        try:
            from Memory.long_term import LongTermMemory
            from Memory.working import WorkingMemory
            self.memory = {
                "long_term": LongTermMemory(),
                "working": WorkingMemory()
            }
            log.info("✅ Memory systems loaded")
        except ImportError:
            log.warning("⚠️ Memory systems not found. Running without persistent memory.")

        # Восприятие
        try:
            from Perception.manager import PerceptionManager
            self.perception = PerceptionManager(self.state)
            log.info("✅ Perception system loaded")
        except ImportError:
            log.warning("⚠️ Perception system not found.")

        # Когнитивные процессы (Планировщик, Любопытство)
        try:
            from Cognition.manager import CognitionManager
            self.cognition = CognitionManager(self.state, self.memory)
            log.info("✅ Cognition system loaded")
        except ImportError:
            log.warning("⚠️ Cognition system not found.")

        # Действия
        try:
            from Action.executor import ActionExecutor
            self.action = ActionExecutor(self.state)
            log.info("✅ Action system loaded")
        except ImportError:
            log.warning("⚠️ Action system not found.")

        # Подключаем к когнитивному циклу
        self.cycle.attach_systems(
            perception=self.perception,
            thinking=self.cognition,
            action=self.action,
            learning=self.memory.get("long_term") if self.memory else None
        )

         # DMN и Planner
        try:
            from Cognition.dmn import DefaultModeNetwork
            from Cognition.planner import GoalDirectedPlanner
            self.dmn = DefaultModeNetwork(self.state, self.memory)
            self.planner = GoalDirectedPlanner(self.state)
            log.info("✅ DMN and Planner loaded")
        except ImportError:
            log.warning("⚠️ DMN/Planner not found.")
    
        # Подключаем к циклу
        self.cycle.attach_systems(
            perception=self.perception,
            thinking=self.cognition,
            action=self.action,
            learning=self.memory.get("long_term") if self.memory else None,
            dmn=self.dmn,
            planner=self.planner
        )

    async def start(self, cycle_interval: float = 2.0):
        """Запуск мозга"""
        if self.is_running:
            log.warning("Brain is already running")
            return
            
        log.info("🚀 Starting Leya OS...")
        self.is_running = True
        
        await event_bus.publish("leya_start", {"timestamp": self.state.start_time})
        
        try:
            self._load_subsystems()
            await self.cycle.run_continuous(cycle_interval)
        except asyncio.CancelledError:
            log.info("🛑 Brain cycle cancelled")
        except Exception as e:
            log.error("💥 Critical error in Brain", error=str(e), exc_info=True)
        finally:
            self.is_running = False
            await event_bus.publish("leya_stop", {"reason": "error_or_cancel"})

    async def stop(self):
        """Остановка мозга"""
        log.info("Stopping Leya OS...")
        self.is_running = False
        # Здесь можно добавить логику graceful shutdown

    async def inject_thought(self, thought: str):
        """
        Внешнее вмешательство: заставить Leya подумать о чем-то конкретном.
        Полезно для API или Telegram-бота.
        """
        log.info("💭 External thought injected", thought=thought)
        self.state.add_to_context({"type": "external_thought", "content": thought})
        await event_bus.publish("external_input", {"type": "thought", "data": thought})