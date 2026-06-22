import asyncio
import logging
from typing import Dict, List, Any, Optional
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent
from Core.homeostasis import Homeostasis
from Cognition.manager import CognitionManager
from Core.embodiment import EmbodimentSystem
from Cognition.planner import GoalDirectedPlanner
from Cognition.stream_of_consciousness import StreamOfConsciousness
from Cognition.dmn import DefaultModeNetwork
from Cognition.sleep_consolidation import SleepConsolidation
from Core.thalamus import Thalamus
from Core.project_manager import ProjectManager
from Cognition.lesson_system import LessonSystem

logger = logging.getLogger(__name__)


class Brain:
    """
    Центральный модуль управления всеми когнитивными процессами.
    
    Использует EventBus для событийно-ориентированной архитектуры.
    Управляет жизненным циклом всех когнитивных модулей.
    """
    
    def __init__(self):
        self.state = LeyaState()
        self.event_bus = EventBus()
        
        # Когнитивные модули
        self.homeostasis: Optional[Homeostasis] = None
        self.cognition_manager: Optional[CognitionManager] = None
        self.embodiment: Optional[EmbodimentSystem] = None
        self.planner: Optional[GoalDirectedPlanner] = None
        self.stream_of_consciousness: Optional[StreamOfConsciousness] = None
        self.dmn: Optional[DefaultModeNetwork] = None
        self.sleep_consolidation: Optional[SleepConsolidation] = None
        self.thalamus: Optional[Thalamus] = None
        self.project_manager: Optional[ProjectManager] = None
        self.lesson_system: Optional[LessonSystem] = None
        
        # Состояние цикла
        self.cycle_count = 0
        self.is_running = False
        self.cycle_interval = 2.0
        
        logger.info("🧠 Brain initialized with EventBus architecture")
    
    async def initialize(self):
        """Инициализация Brain и всех подчинённых модулей."""
        try:
            # Запускаем EventBus
            self.event_bus.start()
            
            # Подписываемся на события
            self.event_bus.subscribe("user_message", self._handle_user_message)
            self.event_bus.subscribe("thought_generated", self._handle_internal_thought)
            self.event_bus.subscribe("cycle_start", self._handle_cycle_start)
            self.event_bus.subscribe("cycle_end", self._handle_cycle_end)
            self.event_bus.subscribe("hormone_update", self._handle_hormone_update)
            self.event_bus.subscribe("emotion_change", self._handle_emotion_change)
            self.event_bus.subscribe("goal_achieved", self._handle_goal_achieved)
            self.event_bus.subscribe_global(self._on_any_event)
            
            logger.info("🧠 Brain event subscriptions registered")
            
            # Инициализируем все модули
            await self._initialize_modules()
            
            self.is_running = True
            logger.info("🧠 Brain fully initialized and running")
            
        except Exception as e:
            logger.error("Failed to initialize Brain", exc_info=True)
            raise
    
    async def _initialize_modules(self):
        """Инициализация всех когнитивных модулей."""
        try:
            # Homeostasis
            self.homeostasis = Homeostasis()
            await self.homeostasis.initialize()
            logger.info("🫀 Homeostasis initialized")
            
            # Embodiment
            self.embodiment = EmbodimentSystem(self.state)
            await self.embodiment.initialize()
            logger.info("🖥️ Embodiment initialized")
            
            # Cognition Manager
            self.cognition_manager = CognitionManager(self.state, self.event_bus)
            await self.cognition_manager.initialize()
            logger.info("🧠 Cognition Manager initialized")
            
            # Planner
            self.planner = GoalDirectedPlanner(self.state, self.event_bus)
            await self.planner.initialize()
            logger.info("🎯 Planner initialized")
            
            # Stream of Consciousness
            self.stream_of_consciousness = StreamOfConsciousness(self.state, self.event_bus)
            await self.stream_of_consciousness.initialize()
            logger.info("💭 Stream of Consciousness initialized")
            
            # DMN
            self.dmn = DefaultModeNetwork(self.state, self.event_bus)
            await self.dmn.initialize()
            logger.info("🧠 DMN initialized")
            
            # Sleep Consolidation
            self.sleep_consolidation = SleepConsolidation(self.state, self.event_bus)
            await self.sleep_consolidation.initialize()
            logger.info("🌙 Sleep Consolidation initialized")
            
            # Thalamus
            self.thalamus = Thalamus(self.state, self.event_bus)
            await self.thalamus.initialize()
            logger.info("🚦 Thalamus initialized")
            
            # Project Manager
            self.project_manager = ProjectManager(self.state, self.event_bus)
            await self.project_manager.initialize()
            logger.info("🎨 Project Manager initialized")
            
            # Lesson System
            self.lesson_system = LessonSystem(self.state, self.event_bus)
            await self.lesson_system.initialize()
            logger.info("📚 Lesson System initialized")
            
            # Связываем homeostasis с cognition_manager
            if self.cognition_manager and self.homeostasis:
                self.cognition_manager.homeostasis = self.homeostasis
                logger.info("🔗 Homeostasis linked to Cognition Manager")
            
        except Exception as e:
            logger.error("Failed to initialize modules", exc_info=True)
            raise
    
    async def _handle_user_message(self, event: LeyaEvent):
        """Обработка входящего сообщения от пользователя."""
        try:
            text = event.data.get("text", "")
            self.state.last_user_message = text
            self.state.cycle_count += 1
            
            logger.info("📥 User message received", text=text[:50])
            
            # Передаём в cognition_manager
            if self.cognition_manager:
                await self.cognition_manager.process_user_input(event.data)
            
            # Публикуем событие о обработке сообщения
            await self.event_bus.publish("message_processed", {
                "text": text,
                "cycle": self.state.cycle_count
            })
            
        except Exception as e:
            logger.error("Failed to handle user message", exc_info=True)
    
    async def _handle_internal_thought(self, event: LeyaEvent):
        """Обработка внутренней мысли."""
        try:
            thought = event.data.get("thought", "")
            self.state.current_thought = thought
            
            logger.debug("💭 Internal thought processed", thought=thought[:50])
            
            # Связь с DMN для фоновой обработки
            if self.dmn:
                await self.dmn.process_thought(thought)
            
            # Связь с continuity для сохранения в памяти
            if self.state.continuity:
                await self.state.continuity.record_thought(thought)
            
        except Exception as e:
            logger.error("Failed to handle internal thought", exc_info=True)
    
    async def _handle_cycle_start(self, event: LeyaEvent):
        """Обработка начала когнитивного цикла."""
        try:
            cycle_num = event.data.get("cycle", 0)
            logger.debug(f"🌟 Cycle #{cycle_num} started")
            
            # Обновляем состояние
            self.state.cycle_count = cycle_num
            
        except Exception as e:
            logger.error("Failed to handle cycle start", exc_info=True)
    
    async def _handle_cycle_end(self, event: LeyaEvent):
        """Обработка завершения когнитивного цикла."""
        try:
            cycle_num = event.data.get("cycle", 0)
            logger.debug(f"✅ Cycle #{cycle_num} completed")
            
        except Exception as e:
            logger.error("Failed to handle cycle end", exc_info=True)
    
    async def _handle_hormone_update(self, event: LeyaEvent):
        """Обработка обновления гормонов."""
        try:
            hormones = event.data.get("hormones", {})
            self.state.update_hormones(hormones)
            
            logger.debug("🧪 Hormones updated", hormones=hormones)
            
        except Exception as e:
            logger.error("Failed to handle hormone update", exc_info=True)
    
    async def _handle_emotion_change(self, event: LeyaEvent):
        """Обработка изменения эмоции."""
        try:
            emotion = event.data.get("emotion", "")
            intensity = event.data.get("intensity", 0.0)
            
            self.state.current_emotion = emotion
            self.state.emotion_intensity = intensity
            
            logger.debug("💝 Emotion changed", emotion=emotion, intensity=intensity)
            
        except Exception as e:
            logger.error("Failed to handle emotion change", exc_info=True)
    
    async def _handle_goal_achieved(self, event: LeyaEvent):
        """Обработка достижения цели."""
        try:
            goal = event.data.get("goal", "")
            logger.info(f"🎯 Goal achieved: {goal}")
            
            # Обновляем planner
            if self.planner:
                await self.planner.on_goal_achieved(goal)
            
        except Exception as e:
            logger.error("Failed to handle goal achieved", exc_info=True)
    
    async def _on_any_event(self, event: LeyaEvent):
        """Глобальная реакция на любое событие."""
        try:
            # Глобальные реакции на события
            if "hormone" in event.type.lower():
                self.state.update_hormones(event.data)
            
            # Можно добавить другие глобальные реакции
            
        except Exception as e:
            logger.error("Failed to handle global event", exc_info=True)
    
    async def _perceive(self):
        """Фаза восприятия."""
        try:
            if self.embodiment:
                await self.embodiment.perceive()
            
            # Публикуем событие о восприятии
            await self.event_bus.publish("perception_complete", {
                "cycle": self.state.cycle_count
            })
            
        except Exception as e:
            logger.error("Perception failed", exc_info=True)
    
    async def _act(self):
        """Фаза действия."""
        try:
            if self.cognition_manager:
                await self.cognition_manager.act()
            
            # Публикуем событие о действии
            await self.event_bus.publish("action_complete", {
                "cycle": self.state.cycle_count
            })
            
        except Exception as e:
            logger.error("Action failed", exc_info=True)
    
    async def _reflect(self):
        """Фаза рефлексии."""
        try:
            if self.stream_of_consciousness:
                await self.stream_of_consciousness.reflect()
            
            if self.dmn:
                await self.dmn.reflect()
            
            # Публикуем событие о рефлексии
            await self.event_bus.publish("reflection_complete", {
                "cycle": self.state.cycle_count
            })
            
        except Exception as e:
            logger.error("Reflection failed", exc_info=True)
    
    async def run_cognitive_cycle(self):
        """Запуск непрерывного когнитивного цикла."""
        self.is_running = True
        logger.info("🔄 Starting continuous cognitive cycle")
        
        while self.is_running:
            try:
                self.state.cycle_count += 1
                
                # Публикуем начало цикла
                await self.event_bus.publish("cycle_start", {
                    "cycle": self.state.cycle_count
                }, priority=7)
                
                # Выполняем фазы цикла
                await self._perceive()
                
                if self.homeostasis:
                    await self.homeostasis.tick()
                
                if self.cognition_manager:
                    await self.cognition_manager.think()
                
                await self._act()
                await self._reflect()
                
                # Публикуем конец цикла
                await self.event_bus.publish("cycle_end", {
                    "cycle": self.state.cycle_count
                })
                
                # Ждём до следующего цикла
                await asyncio.sleep(self.cycle_interval)
                
            except Exception as e:
                logger.error("Cycle error", exc_info=True)
                self.state.error_streak += 1
                
                # Ждём перед следующей попыткой
                await asyncio.sleep(1.0)
    
    async def stop(self):
        """Остановка Brain и всех модулей."""
        self.is_running = False
        logger.info("🛑 Stopping Brain...")
        
        try:
            # Останавливаем все модули
            if self.cognition_manager:
                await self.cognition_manager.stop()
            
            if self.embodiment:
                await self.embodiment.stop()
            
            if self.planner:
                await self.planner.stop()
            
            if self.stream_of_consciousness:
                await self.stream_of_consciousness.stop()
            
            if self.dmn:
                await self.dmn.stop()
            
            if self.sleep_consolidation:
                await self.sleep_consolidation.stop()
            
            if self.thalamus:
                await self.thalamus.stop()
            
            if self.project_manager:
                await self.project_manager.stop()
            
            if self.lesson_system:
                await self.lesson_system.stop()
            
            if self.homeostasis:
                await self.homeostasis.stop()
            
            # Останавливаем EventBus
            self.event_bus.stop()
            
            logger.info("✅ Brain stopped successfully")
            
        except Exception as e:
            logger.error("Error stopping Brain", exc_info=True)
    
    def get_state(self) -> Dict[str, Any]:
        """Получение текущего состояния Brain."""
        return {
            "cycle_count": self.state.cycle_count,
            "is_running": self.is_running,
            "error_streak": self.state.error_streak,
            "current_emotion": self.state.current_emotion,
            "emotion_intensity": self.state.emotion_intensity,
            "last_user_message": self.state.last_user_message,
            "current_thought": self.state.current_thought
        }