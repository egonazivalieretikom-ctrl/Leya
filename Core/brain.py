import asyncio
from typing import Optional, Dict, Any
from Core.logger import log
from Core.state import LeyaState
from Core.cognitive_cycle import CognitiveCycle
from Core.homeostasis import HomeostaticEngine
from Core.event_bus import event_bus


class Brain:
    """
    Центральный орган управления Leya v0.9.
    
    Биология: Brain — это префронтальная кора + лимбическая система.
    Он создаёт HomeostaticEngine (сердце) и передаёт его всем подсистемам.
    
    Архитектура:
    - Единое сердце (HomeostaticEngine) для всех модулей
    - Knowledge Graph для долгосрочных фактов
    - Sleep Consolidation для формирования личности
    - Thalamus для фильтрации и объединения сигналов
    """
    
    def __init__(self):
        self.state = LeyaState()
        self.memory: Dict[str, Any] = {}
        
        # 🆕 Создаём homeostasis СРАЗУ (единое сердце)
        self.homeostasis = HomeostaticEngine(self.state)
        
        self.cycle: CognitiveCycle = CognitiveCycle(self.state)
        
        # Подсистемы (инициализируются в _load_subsystems)
        self.perception = None
        self.cognition = None
        self.action = None
        self.dmn = None
        self.planner = None
        self.stream = None
        self.sleep_consolidation = None
        self.thalamus = None
        
        log.info("🧠 Brain initialized (v0.9 - Full Integration)")
    
    def _load_subsystems(self):
        """Загружает все когнитивные подсистемы."""
        log.info("🚀 Starting Leya OS...")
        log.info("Loading subsystems...")
        
        # ====================================================================
        # 1. ПАМЯТЬ (LTM + Working Memory + Knowledge Graph)
        # ====================================================================
        try:
            from Memory.long_term import LongTermMemory
            from Memory.working import WorkingMemory
            from Memory.knowledge_graph import KnowledgeGraph
            
            self.memory["long_term"] = LongTermMemory()
            self.memory["working"] = WorkingMemory(capacity=50)
            self.memory["knowledge_graph"] = KnowledgeGraph()
            
            log.info("✅ Memory systems loaded (LTM + Working + KG)")
        except Exception as e:
            log.error("Failed to load memory systems", error=str(e))
            raise
        
        # ====================================================================
        # 2. ВОСПРИЯТИЕ (Perception)
        # ====================================================================
        try:
            from Perception.manager import PerceptionManager
            self.perception = PerceptionManager(self.state)
            log.info("✅ Perception system loaded")
        except Exception as e:
            log.error("Failed to load Perception", error=str(e))
            raise
        
        # ====================================================================
        # 3. ПОЗНАНИЕ (Cognition с передачей homeostasis)
        # ====================================================================
        try:
            from Cognition.manager import CognitionManager
            self.cognition = CognitionManager(
                state=self.state,
                memory=self.memory,
                homeostasis=self.homeostasis
            )
            log.info("✅ Cognition system loaded")
        except Exception as e:
            log.error("Failed to load Cognition", error=str(e))
            raise
        
        # ====================================================================
        # 4. ДЕЙСТВИЕ (Action)
        # ====================================================================
        try:
            from Action.executor import ActionExecutor
            self.action = ActionExecutor(self.state, self.memory)
            log.info("✅ Action system loaded")
        except Exception as e:
            log.error("Failed to load Action", error=str(e))
            raise
        
        # ====================================================================
        # 5. ПОТОК СОЗНАНИЯ (Stream of Consciousness)
        # ====================================================================
        try:
            from Cognition.stream_of_consciousness import StreamOfConsciousness
            self.stream = StreamOfConsciousness(
                self.state, 
                self.memory, 
                homeostasis=self.homeostasis
            )
            log.info("✅ Stream of Consciousness loaded")
        except Exception as e:
            log.error("Failed to load Stream of Consciousness", error=str(e))
            self.stream = None
        
        # ====================================================================
        # 6. DEFAULT MODE NETWORK (DMN)
        # ====================================================================
        try:
            from Cognition.dmn import DefaultModeNetwork
            self.dmn = DefaultModeNetwork(self.state, self.memory)
            log.info("✅ DMN loaded")
        except Exception as e:
            log.error("Failed to load DMN", error=str(e))
            self.dmn = None
        
        # ====================================================================
        # 7. ПЛАНИРОВЩИК (Planner)
        # ====================================================================
        try:
            from Cognition.planner import GoalDirectedPlanner
            self.planner = GoalDirectedPlanner(self.state, self.memory)
            log.info("✅ Planner loaded")
        except Exception as e:
            log.error("Failed to load Planner", error=str(e))
            self.planner = None
        
        # ====================================================================
        # 8. КОНСОЛИДАЦИЯ СНА (Sleep Consolidation)
        # ====================================================================
        try:
            from Cognition.sleep_consolidation import SleepConsolidation
            self.sleep_consolidation = SleepConsolidation(self.state, self.memory)
            log.info("✅ Sleep Consolidation loaded")
        except Exception as e:
            log.error("Failed to load Sleep Consolidation", error=str(e))
            self.sleep_consolidation = None
        
        # ====================================================================
        # 9. ТАЛАМУС (Thalamus — фильтр и объединитель сигналов)
        # ====================================================================
        try:
            from Core.thalamus import Thalamus
            self.thalamus = Thalamus(self.state)
            log.info("✅ Thalamus loaded")
        except Exception as e:
            log.error("Failed to load Thalamus", error=str(e))
            self.thalamus = None

        # ====================================================================
        # 🆕 9.5 МЕНЕДЖЕР СОБСТВЕННЫХ ПРОЕКТОВ
        # ====================================================================
        try:
            from Cognition.projects import ProjectManager
            self.project_manager = ProjectManager(self.state, self.memory)
            log.info("✅ Project Manager loaded")
        except Exception as e:
            log.error("Failed to load Project Manager", error=str(e))
            self.project_manager = None

        # ====================================================================
        # 🆕 ЭМБОДЗИМЕНТ (телесные ощущения)
        # ====================================================================
        try:
            from Core.embodiment import EmbodimentSystem
            self.embodiment = EmbodimentSystem(self.state)
            log.info("✅ Embodiment System loaded")
        except Exception as e:
            log.error("Failed to load Embodiment System", error=str(e))
            self.embodiment = None

        # ====================================================================
        # 🆕 НЕПРЕРЫВНОСТЬ (субъективное время + фоновые ощущения)
        # ====================================================================
        try:
            from Core.continuity import ContinuitySystem
            self.continuity = ContinuitySystem(self.state)
            log.info("✅ Continuity System loaded")
        except Exception as e:
            log.error("Failed to load Continuity System", error=str(e))
            self.continuity = None
        
        # ====================================================================
        # 10. ПЕРЕДАЧА ВСЕХ ПОДСИСТЕМ В ЦИКЛ
        # ====================================================================
        self.cycle.attach_systems(
            perception=self.perception,
            thinking=self.cognition,
            action=self.action,
            learning=None,
            dmn=self.dmn,
            planner=self.planner,
            stream=self.stream,
            sleep_consolidation=self.sleep_consolidation,
            thalamus=self.thalamus,
            project_manager=self.project_manager 
        )
        
        # ====================================================================
        # 11. СВЯЗЫВАНИЕ HOMEOSTASIS С COGNITION
        # ====================================================================
        if self.homeostasis and self.cognition:
            self.cognition.homeostasis = self.homeostasis
            log.info("🔗 Homeostasis linked to Cognition Manager")
        
        log.info("✅ All subsystems loaded and attached (v0.9)")
    
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
        
        # 🆕 Запускаем непрерывные процессы
        background_tasks = []
        
        if self.embodiment:
            background_tasks.append(asyncio.create_task(self.embodiment.start()))
        
        if self.continuity:
            background_tasks.append(asyncio.create_task(self.continuity.start()))
        
        # Запускаем когнитивный цикл
        try:
            await self.cycle.run_continuous(cycle_interval)
        except asyncio.CancelledError:
            log.info("🛑 Brain cycle cancelled")
            for task in background_tasks:
                task.cancel()
        except Exception as e:
            log.error("💥 Critical error in Brain cycle", error=str(e), exc_info=True)
            for task in background_tasks:
                task.cancel()
            raise