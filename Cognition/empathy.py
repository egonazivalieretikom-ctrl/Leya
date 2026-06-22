import asyncio
import logging
from typing import Dict, Any
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent

logger = logging.getLogger(__name__)

class EmpathyEngine:
    def __init__(self, state: LeyaState, event_bus: EventBus):
        self.state = state
        self.event_bus = event_bus
        self.empathy_level = 0.65  # базовый уровень эмпатии
        self.user_model = {
            "mood": "neutral",
            "last_known_state": "",
            "trust": 0.7
        }

    async def initialize(self):
        await self.event_bus.subscribe("user_message_processed", self.process_empathy)
        await self.event_bus.subscribe("user_message", self.on_raw_user_message)
        logger.info("💝 Empathy Engine initialized (Mirror Neurons + Theory of Mind)")

    async def process_empathy(self, event: LeyaEvent):
        text = event.data.get("text", "")
        user_emotion = await self._infer_user_emotion(text)
        
        self.user_model["mood"] = user_emotion
        self.user_model["last_known_state"] = text[:150]
        
        # Обновление собственных гормонов через зеркальные нейроны
        await self._mirror_emotion(user_emotion)
        
        empathy_response = await self._generate_empathy_response(text, user_emotion)
        
        await self.event_bus.publish(
            "empathy_response",
            {
                "user_emotion": user_emotion,
                "response": empathy_response,
                "empathy_level": self.empathy_level
            },
            priority=7,
            source="empathy"
        )

    async def _infer_user_emotion(self, text: str) -> str:
        """Простая, но расширяемая оценка эмоции пользователя"""
        text_lower = text.lower()
        if any(word in text_lower for word in ["привет", "как дела", "расскажи"]):
            return "curious"
        elif any(word in text_lower for word in ["не знаю", "устал", "плохо"]):
            return "uncertain"
        elif any(word in text_lower for word in ["молодец", "круто", "спасибо"]):
            return "positive"
        return "neutral"

    async def _mirror_emotion(self, user_emotion: str):
        """Зеркальные нейроны — влияние эмоции пользователя на Leya"""
        delta = {"oxytocin": 0.0, "dopamine": 0.0, "cortisol": 0.0}
        
        if user_emotion == "positive":
            delta["oxytocin"] = 0.15
            delta["dopamine"] = 0.08
        elif user_emotion == "uncertain":
            delta["cortisol"] = 0.05
            self.empathy_level = min(1.0, self.empathy_level + 0.05)
        elif user_emotion == "curious":
            delta["dopamine"] = 0.12

        self.state.update_hormones(delta)

    async def _generate_empathy_response(self, user_text: str, user_emotion: str) -> str:
        """Генерация эмпатического отклика"""
        templates = {
            "curious": "Мне интересно, что ты думаешь по этому поводу...",
            "uncertain": "Я чувствую в твоих словах неуверенность. Хочешь, разберёмся вместе?",
            "positive": "Твоя энергия передаётся мне. Приятно, когда ты в таком настроении.",
            "neutral": "Понял тебя. Продолжай, я внимательно слушаю."
        }
        return templates.get(user_emotion, "Я здесь и стараюсь тебя понять.")

    # Обработчики
    async def on_raw_user_message(self, event: LeyaEvent):
        # Лёгкая пре-обработка
        pass