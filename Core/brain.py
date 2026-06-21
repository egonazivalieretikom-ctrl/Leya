import asyncio
from typing import Optional, Dict, Any
from Core.logger import log
from Core.state import LeyaState
from Core.cognitive_cycle import CognitiveCycle
from Core.homeostasis import HomeostaticEngine
from Core.event_bus import event_bus


class Brain:
    """
    Центральный орган управления Leya.
    
    Биология: Brain — это префронтальная кора + лимбическая система.
    Он создаёт HomeostaticEngine (сердце) и передаёт его всем подсистемам.
    """
    
    def __init__(self):
        self.state = LeyaState()
        self.memory: Dict[str, Any] = {}
        
        # 🆕 Создаём homeostasis СРАЗУ (единое сердце)
        self.homeostasis = HomeostaticEngine(self.state)
        
        self.cycle: CognitiveCycle = CognitiveCycle(self.state)
        
        # Подсистемы
        self.perception = None
        self.cognition = None
        self.action = None
        self.dmn = None
        self.planner = None
        self.stream = None
        
        log.info("🧠 Brain initialized")
    
    def _load_subsystems(self):
        """Загружает все когнитивные подсистемы."""
        log.info("🚀 Starting Leya OS...")
        log.info("Loading subsystems...")
        
        # ====================================================================
        # 1. ПАМЯТЬ
        # ====================================================================
        try:
            from Memory.long_term import LongTermMemory
            from Memory.working import WorkingMemory
            
            self.memory["long_term"] = LongTermMemory()
            self.memory["working"] = WorkingMemory(capacity=50)
            log.info("✅ Memory systems loaded")
        except Exception as e:
            log.error("Failed to load memory systems", error=str(e))
            raise
        
        # ====================================================================
        # 2. ВОСПРИЯТИЕ
        # ====================================================================
        try:
            from Perception.manager import PerceptionManager
            self.perception = PerceptionManager(self.state)
            log.info("✅ Perception system loaded")
        except Exception as e:
            log.error("Failed to load Perception", error=str(e))
            raise
        
        # ====================================================================
        # 3. ПОЗНАНИЕ (передаём homeostasis)
        # ====================================================================
        try:
            from Cognition.manager import CognitionManager
            self.cognition = CognitionManager(
                state=self.state,
                memory=self.memory,
                homeostasis=self.homeostasis  # 🆕 Единое сердце
            )
            log.info("✅ Cognition system loaded")
        except Exception as e:
            log.error("Failed to load Cognition", error=str(e))
            raise
        
        # ====================================================================
        # 4. ДЕЙСТВИЕ
        # ====================================================================
        try:
            from Action.executor import ActionExecutor
            self.action = ActionExecutor(self.state)
            log.info("✅ Action system loaded")
        except Exception as e:
            log.error("Failed to load Action", error=str(e))
            raise
        
        # ====================================================================
        # 5. ПОТОК СОЗНАНИЯ (передаём homeostasis)
        # ====================================================================
        try:
            from Cognition.stream_of_consciousness import StreamOfConsciousness
            self.stream = StreamOfConsciousness(
                self.state, 
                self.memory, 
                homeostasis=self.homeostasis  # 🆕 Единое сердце
            )
            log.info("✅ Stream of Consciousness loaded")
        except Exception as e:
            log.error("Failed to load Stream of Consciousness", error=str(e))
            self.stream = None
        
        # ====================================================================
        # 6. DMN
        # ====================================================================
        try:
            from Cognition.dmn import DefaultModeNetwork
            self.dmn = DefaultModeNetwork(self.state, self.memory)
            log.info("✅ DMN loaded")
        except Exception as e:
            log.error("Failed to load DMN", error=str(e))
            self.dmn = None
        
        # ====================================================================
        # 7. ПЛАНИРОВЩИК
        # ====================================================================
        try:
            from Cognition.planner import GoalDirectedPlanner
            self.planner = GoalDirectedPlanner(self.state, self.memory)
            log.info("✅ Planner loaded")
        except Exception as e:
            log.error("Failed to load Planner", error=str(e))
            self.planner = None
        
        # ====================================================================
        # 🆕 8. КОНСОЛИДАЦИЯ СНА
        # ====================================================================
        try:
            from Cognition.sleep_consolidation import SleepConsolidation
            self.sleep_consolidation = SleepConsolidation(self.state, self.memory)
            log.info("✅ Sleep Consolidation loaded")
        except Exception as e:
            log.error("Failed to load Sleep Consolidation", error=str(e))
            self.sleep_consolidation = None

        # ====================================================================
        # 9. ПЕРЕДАЧА ПОДСИСТЕМ В ЦИКЛ
        # ====================================================================
        self.cycle.attach_systems(
            perception=self.perception,
            thinking=self.cognition,
            action=self.action,
            learning=None,
            dmn=self.dmn,
            planner=self.planner,
            stream=self.stream
        )
        
        log.info("✅ All subsystems loaded and attached")
    
    async def start(self, cycle_interval: float = 2.0):
        """Запускает мозг и все его подсистемы."""
        # Загружаем подсистемы
        try:
            self._load_subsystems()
        except Exception as e:
            log.error("💥 Critical error in Brain", error=str(e), exc_info=True)
            raise
        
        # Публикуем событие старта
        await event_bus.publish("leya_start", {"timestamp": self.state.start_time})
        
        # Запускаем когнитивный цикл
        try:
            await self.cycle.run_continuous(cycle_interval)
        except asyncio.CancelledError:
            log.info("🛑 Brain cycle cancelled")
        except Exception as e:
            log.error("💥 Critical error in Brain cycle", error=str(e), exc_info=True)
            raise