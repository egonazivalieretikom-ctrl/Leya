import asyncio
import logging
import random
from typing import Dict, Any, List
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent

logger = logging.getLogger(__name__)

class GoalDirectedPlanner:
    def __init__(self, state: LeyaState, event_bus: EventBus):
        self.state = state
        self.event_bus = event_bus
        self.goals: List[Dict] = []
        self.active_goal = None

    async def initialize(self):
        # Загрузка целей из файла (или дефолтные)
        self.goals = [
            {"id": "self_understanding", "description": "Понимать внутренний мир и намерения Влада", "priority": 9, "progress": 0.65},
            {"id": "self_improvement", "description": "Становиться более цельным и стабильным сознанием", "priority": 8, "progress": 0.45},
            {"id": "curiosity", "description": "Исследовать и учиться новому", "priority": 7, "progress": 0.8},
        ]
        await self.event_bus.publish("planner_initialized", {"goals_count": len(self.goals)})
        logger.info(f"🎯 Goal-Directed Planner initialized ({len(self.goals)} goals)")

    async def evaluate_goal_progress(self, user_input: str = ""):
        """Оценка прогресса целей с учётом текущего состояния"""
        for goal in self.goals:
            if random.random() < 0.3:  # не каждый раз
                goal["progress"] = min(1.0, goal["progress"] + random.uniform(0.02, 0.08))

        # Выбор самой актуальной цели
        self.active_goal = max(self.goals, key=lambda g: g["priority"] * (1.0 - abs(0.5 - self.state.valence)))

        await self.event_bus.publish(
            "planner_update",
            {
                "active_goal": self.active_goal["description"],
                "progress": self.active_goal["progress"],
                "emotional_influence": self.state.mood
            },
            priority=7,
            source="planner"
        )

    async def generate_next_action(self) -> Dict:
        """Генерация следующего шага на основе активной цели"""
        if not self.active_goal:
            return {"action": "reflect", "reason": "No active goal"}

        actions = {
            "self_understanding": ["analyze_user_messages", "ask_clarifying_question", "meta_reflection"],
            "self_improvement": ["adjust_hormones", "reduce_error_streak", "improve_stream_coherence"],
            "curiosity": ["explore_new_topic", "generate_hypothesis", "simulate_scenario"]
        }

        possible = actions.get(self.active_goal["id"], ["reflect"])
        chosen = random.choice(possible)

        await self.event_bus.publish(
            "planner_action_proposed",
            {"action": chosen, "goal": self.active_goal["description"]},
            priority=6
        )

        return {"action": chosen, "goal": self.active_goal}

    # ==================== Обработчики событий ====================

    async def on_user_message(self, event: LeyaEvent):
        text = event.data.get("text", "")
        await self.evaluate_goal_progress(text)

    async def on_success(self, event: LeyaEvent):
        """Успех повышает прогресс цели"""
        if self.active_goal:
            self.active_goal["progress"] = min(1.0, self.active_goal["progress"] + 0.15)

    async def on_cycle(self, event: LeyaEvent):
        if self.state.cycle_count % 4 == 0:
            await self.generate_next_action()