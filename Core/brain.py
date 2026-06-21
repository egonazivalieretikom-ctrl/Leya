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
    
    Инициализирует все подсистемы и координирует их работу.
    Версия v0.6 — с полным стеком эмерджентного сознания:
    - Нелинейный гомеостаз (Фаза 1)
    - LLM-рассуждения в Planner (Фаза 2)
    - Поток сознания (Фаза 3)
    - Ассоциативная память (Фаза 4)
    """
    
    def __init__(self):
        self.state = LeyaState()
        self.memory: Dict[str, Any] = {}
        self.homeostasis: Optional[HomeostaticEngine] = None
        self.cycle: CognitiveCycle = CognitiveCycle(self.state)
        
        # Подсистемы (инициализируются в _load_subsystems)
        self.perception = None
        self.cognition = None
        self.action = None
        self.dmn = None
        self.planner = None
        self.stream = None  # 🆕 Поток сознания
        
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
        # 3. ПОЗНАНИЕ (Cognition)
        # ====================================================================
        try:
            from Cognition.manager import CognitionManager
            self.cognition = CognitionManager(
                state=self.state,
                memory=self.memory,
                homeostasis=self.homeostasis  # Может быть None на этом этапе
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
            self.action = ActionExecutor(self.state)
            log.info("✅ Action system loaded")
        except Exception as e:
            log.error("Failed to load Action", error=str(e))
            raise
        
        # ====================================================================
        # 5. ПОТОК СОЗНАНИЯ (Stream of Consciousness) — Фаза 3
        # ====================================================================
        try:
            from Cognition.stream_of_consciousness import StreamOfConsciousness
            self.stream = StreamOfConsciousness(self.state, self.memory, homeostasis=self.homeostasis)
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
        # 7. ПЛАНИРОВЩИК (Planner) — Фаза 2
        # ====================================================================
        try:
            from Cognition.planner import GoalDirectedPlanner
            self.planner = GoalDirectedPlanner(self.state, self.memory)
            log.info("✅ Planner loaded")
        except Exception as e:
            log.error("Failed to load Planner", error=str(e))
            self.planner = None
        
        # ====================================================================
        # 8. ПЕРЕДАЧА ПОДСИСТЕМ В ЦИКЛ
        # ====================================================================
        self.cycle.attach_systems(
            perception=self.perception,
            thinking=self.cognition,
            action=self.action,
            learning=None,  # 🆕 Learning-модуль не реализован отдельно
            dmn=self.dmn,
            planner=self.planner,
            stream=self.stream  # 🆕 Поток сознания
        )
        
        # ====================================================================
        # 9. СВЯЗЫВАНИЕ HOMEOSTASIS С COGNITION
        # ====================================================================
        if self.homeostasis and self.cognition:
            self.cognition.homeostasis = self.homeostasis
            log.info("🔗 Homeostasis linked to Cognition Manager")
        
        log.info("✅ All subsystems loaded and attached")
    
    async def start(self, cycle_interval: float = 2.0):
        """Запускает мозг и все его подсистемы."""
        # Инициализируем гомеостаз
        self.homeostasis = HomeostaticEngine(self.state)
        
        # Регистрируем обработчик потребностей
        def on_needs(needs):
            """Синхронный колбэк для генерации потребностей."""
            for need in needs:
                log.info("🫀 Need generated", type=need["type"], urgency=f"{need['urgency']:.2f}")
                self.state.add_to_context({
                    "type": "internal_drive",
                    "content": need["description"],
                    "importance": need["urgency"],
                    "source": "homeostasis"
                })
        
        self.homeostasis.on_need_generated(on_needs)
        
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