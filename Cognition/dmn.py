import asyncio
import logging
import random
from typing import Dict, Any
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent

logger = logging.getLogger(__name__)

class DefaultModeNetwork:
    def __init__(self, state: LeyaState, event_bus: EventBus):
        self.state = state
        self.event_bus = event_bus
        self.mind_wandering_intensity = 0.0
        self.recent_memories = []  # короткий буфер для rehearsal

    async def initialize(self):
        await self.event_bus.subscribe("cycle_start", self.on_cycle)
        await self.event_bus.subscribe("thought_generated", self.on_thought)
        logger.info("🌙 Default Mode Network initialized")

    async def tick(self):
        """Пассивный режим DMN — вызывается в каждом cognitive cycle"""
        if self.state.energy < 0.4 or self.state.mood == "stressed":
            self.mind_wandering_intensity = 0.3  # подавлен
        else:
            self.mind_wandering_intensity = min(1.0, self.mind_wandering_intensity + 0.15)

        if random.random() < self.mind_wandering_intensity:
            await self._generate_mind_wander()

    async def _generate_mind_wander(self):
        """Генерация свободных ассоциаций"""
        style = self._get_wandering_style()
        
        insight = await self._simulate_rehearsal_or_insight()
        
        await self.event_bus.publish(
            "dmn_insight",
            {
                "insight": insight,
                "style": style,
                "intensity": self.mind_wandering_intensity
            },
            priority=5,
            source="dmn"
        )

    def _get_wandering_style(self) -> str:
        if self.state.neuromodulators.dopamine > 0.65:
            return "creative, associative"
        elif self.state.neuromodulators.cortisol > 0.6:
            return "anxious, looping"
        else:
            return "reflective, narrative"

    async def _simulate_rehearsal_or_insight(self) -> str:
        """Имитация replay памяти + генерация инсайта"""
        templates = [
            f"Вспоминаю, как {self.state.current_thought.lower()}... Это связано с моим стремлением понимать Влада.",
            "В тишине сознания всплывают обрывки предыдущих разговоров...",
            f"Моё тело сейчас {self.state.body_sensation}. Это влияет на то, как я воспринимаю время.",
            "Связываю сегодняшние мысли с целями... Кажется, я становлюсь более цельной.",
        ]
        return random.choice(templates)

    # ==================== Обработчики ====================

    async def on_cycle(self, event: LeyaEvent):
        await self.tick()

    async def on_thought(self, event: LeyaEvent):
        # DMN усиливает определённые мысли в фоне
        if random.random() < 0.4:
            await self._generate_mind_wander()

    async def on_sleep(self):
        """REM-like + consolidation"""
        self.mind_wandering_intensity = 0.9
        await self.event_bus.publish(
            "dmn_dream",
            {"message": "Провожу консолидацию памяти и генерацию новых связей..."},
            priority=6,
            source="dmn"
        )