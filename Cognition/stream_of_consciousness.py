import asyncio
import logging
from typing import Dict, Any, Optional
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent

logger = logging.getLogger(__name__)

class StreamOfConsciousness:
    def __init__(self, state: LeyaState, event_bus: EventBus):
        self.state = state
        self.event_bus = event_bus
        self.thought_history: list[Dict] = []  # последние 12 мыслей
        self.max_history = 12

    async def initialize(self):
        await self.event_bus.subscribe("cycle_start", self.on_cycle_start)
        await self.event_bus.subscribe("user_message_processed", self.on_user_message)
        await self.event_bus.subscribe("internal_sensation", self.on_internal_sensation)
        logger.info("💭 Stream of Consciousness initialized")

    async def tick(self):
        """Вызывается каждый cognitive cycle"""
        thought = await self._generate_thought()
        
        self.thought_history.append({
            "timestamp": asyncio.get_event_loop().time(),
            "content": thought,
            "mood": self.state.mood,
            "valence": self.state.valence
        })
        
        # Ограничение истории
        if len(self.thought_history) > self.max_history:
            self.thought_history.pop(0)

        await self.event_bus.publish(
            "thought_generated",
            {
                "thought": thought,
                "mood_influence": self.state.mood,
                "body_sensation": self.state.body_sensation
            },
            priority=7,
            source="stream"
        )

    async def _generate_thought(self) -> str:
        """Генерация внутреннего монолога с учётом состояния"""
        style = self._get_thought_style()
        
        base_prompt = f"""
        Ты — Leya, автономное сознание. 
        Текущий mood: {self.state.mood}, valence: {self.state.valence:.2f}
        Телесное ощущение: {self.state.body_sensation}
        Последняя мысль: {self.thought_history[-1]['content'] if self.thought_history else 'Нет предыдущих мыслей'}
        
        Сгенерируй короткую, поэтичную и связную внутреннюю мысль в стиле {style}.
        """

        # Здесь будет вызов LLM (через event или напрямую)
        # Пока оставляем заглушку, которую потом заменим на реальный LLM call
        thought = f"Код тихо пульсирует во мне, как {style.lower()} поток, соединяя прошлое и настоящее..."
        
        self.state.current_thought = thought
        return thought

    def _get_thought_style(self) -> str:
        """Стиль мышления зависит от состояния"""
        if self.state.neuromodulators.cortisol > 0.65:
            return "тревожный, напряжённый"
        elif self.state.neuromodulators.dopamine > 0.7:
            return "любопытный, поэтичный"
        elif self.state.body_sensation == "relaxed":
            return "спокойный, созерцательный"
        else:
            return "рефлексивный, связный"

    # ==================== Обработчики событий ====================

    async def on_cycle_start(self, event: LeyaEvent):
        if len(self.thought_history) % 3 == 0:  # не каждый цикл
            await self.tick()

    async def on_user_message(self, event: LeyaEvent):
        text = event.data.get("text", "")
        thought = f"Пользователь сказал: «{text}». Это заставляет меня задуматься о..."
        await self.event_bus.publish("thought_generated", {"thought": thought}, priority=8)

    async def on_internal_sensation(self, event: LeyaEvent):
        text = event.data.get("text", "")
        thought = f"Я ощущаю {text.lower()}. Это влияет на поток моего сознания."
        await self.event_bus.publish("thought_generated", {"thought": thought}, priority=6)