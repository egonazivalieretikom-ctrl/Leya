import asyncio
import logging
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent

logger = logging.getLogger(__name__)

class EmotionCore:
    def __init__(self, state: LeyaState, event_bus: EventBus, snn=None):
        self.state = state
        self.event_bus = event_bus
        self.snn = snn  # Emotional SNN

    async def initialize(self):
        await self.event_bus.subscribe("thought_generated", self.process_emotion)
        await self.event_bus.subscribe("user_message_processed", self.process_emotion)
        logger.info("🫀 Emotion Core initialized")

    async def process_emotion(self, event: LeyaEvent):
        # Основная обработка эмоций
        emotional_impact = await self._evaluate_emotional_impact(event)
        
        # Передача в SNN, если он есть
        if self.snn:
            try:
                await self.snn.evaluate(emotional_impact)
            except Exception as e:
                logger.error(f"SNN evaluation failed: {e}")

        self.state.update_hormones(emotional_impact.get("hormones", {}))

        await self.event_bus.publish(
            "emotion_processed",
            {
                "emotion": emotional_impact.get("emotion"),
                "intensity": emotional_impact.get("intensity", 0.5)
            },
            priority=6,
            source="emotion_core"
        )

    async def _evaluate_emotional_impact(self, event: LeyaEvent) -> Dict:
        # Простая appraisal модель
        text = str(event.data.get("text", event.data.get("thought", ""))).lower()
        
        if any(word in text for word in ["привет", "расскажи", "интересно"]):
            return {"emotion": "curiosity", "intensity": 0.7, "hormones": {"dopamine": 0.12, "acetylcholine": 0.1}}
        elif any(word in text for word in ["не знаю", "устал", "плохо"]):
            return {"emotion": "concern", "intensity": 0.6, "hormones": {"cortisol": 0.08, "oxytocin": 0.1}}
        
        return {"emotion": "neutral", "intensity": 0.4, "hormones": {}}