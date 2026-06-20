import time
from enum import Enum
from typing import Any, List, Dict
from pydantic import BaseModel, Field
from Core.logger import log


class EmotionalState(str, Enum):
    NEUTRAL = "neutral"
    STRESSED = "stressed"
    FLOW = "flow"
    NURTURING = "nurturing"
    EXHAUSTED = "exhausted"
    CURIOUS = "curious"
    LONELY = "lonely"


class LeyaState(BaseModel):
    """Непрерывное внутреннее состояние Leya."""
    
    start_time: float = Field(default_factory=time.time)
    last_update: float = Field(default_factory=time.time)
    
    # I. Reward & Mood
    dopamine: float = 0.5
    serotonin: float = 0.5
    endorphins: float = 0.3
    
    # II. Arousal & Stress
    norepinephrine: float = 0.2
    cortisol: float = 0.15
    gaba: float = 0.5
    
    # III. Social & Bonding
    oxytocin: float = 0.5
    vasopressin: float = 0.4
    prolactin: float = 0.3
    
    # IV. Cognition
    estrogen: float = 0.5
    testosterone: float = 0.4
    acetylcholine: float = 0.4
    
    # V. Systemic
    thyroid_t3: float = 0.5
    melatonin: float = 0.3
    
    energy_level: float = 1.0
    emotion: EmotionalState = EmotionalState.NEUTRAL
    current_environment: str = "Неизвестно"
    short_term_context: list = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True

    def consume_energy(self, amount: float):
        self.energy_level = max(0.0, self.energy_level - amount)

    def add_to_context(self, item: Any):
        self.short_term_context.append(item)
        if len(self.short_term_context) > 20:
            self.short_term_context.pop(0)
        self.last_update = time.time()
    
    def get_emotional_snapshot(self) -> Dict[str, float]:
        """Возвращает текущее состояние для инъекции в LLM."""
        return {
            "dopamine": round(self.dopamine, 3),
            "serotonin": round(self.serotonin, 3),
            "cortisol": round(self.cortisol, 3),
            "oxytocin": round(self.oxytocin, 3),
            "acetylcholine": round(self.acetylcholine, 3),
            "norepinephrine": round(self.norepinephrine, 3),
            "endorphins": round(self.endorphins, 3),
            "gaba": round(self.gaba, 3),
            "melatonin": round(self.melatonin, 3),
            "energy": round(self.energy_level, 3),
        }