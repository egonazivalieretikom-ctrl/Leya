import asyncio
import logging
from typing import Dict, Any
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent
from Cognition.stream_of_consciousness import StreamOfConsciousness
from Cognition.dmn import DefaultModeNetwork
from Cognition.planner import GoalDirectedPlanner
from Cognition.empathy import EmpathyEngine

logger = logging.getLogger(__name__)

class CognitionManager:
    def __init__(self, state: LeyaState, event_bus: EventBus):
        self.state = state
        self.event_bus = event_bus
        
        self.stream = StreamOfConsciousness(state, event_bus)
        self.dmn = DefaultModeNetwork(state, event_bus)
        self.planner = GoalDirectedPlanner(state, event_bus)
        self.empathy = EmpathyEngine(state, event_bus)
        
        self.current_context = {}

    async def initialize(self):
        await self.event_bus.publish("cognition_initialized", {"modules": ["stream", "dmn", "planner", "empathy"]})
        logger.info("🧠 Cognition Manager initialized (all subsystems connected)")

    async def process_user_input(self, data: Dict[str, Any]):
        text = data.get("text", "")
        self.state.last_user_message = text
        
        # Thalamus-like filtering
        importance = self._assess_importance(text)
        
        await self.event_bus.publish("user_message_processed", 
                                   {"text": text, "importance": importance}, 
                                   priority=9 if importance > 0.7 else 6)
        
        # Parallel processing
        tasks = [
            self.stream.generate_thought(text),
            self.empathy.process_empathy(text),
            self.planner.evaluate_goal_progress(text)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    def _assess_importance(self, text: str) -> float:
        # Простая, но расширяемая оценка
        keywords = ["как ты", "расскажи о себе", "что думаешь", "почему"]
        score = 0.5
        if any(k in text.lower() for k in keywords):
            score += 0.4
        if len(text) > 50:
            score += 0.1
        return min(1.0, score)

    async def think(self):
        """Основной шаг мышления в цикле"""
        await self.stream.tick()
        await self.dmn.tick()
        
        # Meta-cognition
        if self.state.cycle_count % 5 == 0:
            await self._meta_reflection()

    async def _meta_reflection(self):
        """Саморефлексия"""
        await self.event_bus.publish(
            "meta_reflection",
            {
                "energy": self.state.energy,
                "mood": self.state.mood,
                "error_streak": self.state.error_streak,
                "thought": self.state.current_thought
            },
            priority=5,
            source="cognition"
        )