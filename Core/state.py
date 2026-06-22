from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
import copy

class Neuromodulators(BaseModel):
    dopamine: float = 0.5
    serotonin: float = 0.5
    cortisol: float = 0.3
    oxytocin: float = 0.4
    acetylcholine: float = 0.5
    norepinephrine: float = 0.4
    endorphins: float = 0.5
    gaba: float = 0.6

class LeyaState(BaseModel):
    # Основные параметры
    energy: float = Field(1.0, ge=0.0, le=1.0)
    mood: str = "calm"  # calm, curious, stressed, reflective, tired...
    valence: float = Field(0.5, ge=-1.0, le=1.0)
    arousal: float = Field(0.5, ge=0.0, le=1.0)
    
    neuromodulators: Neuromodulators = Field(default_factory=Neuromodulators)
    personality: Dict[str, float] = Field(default_factory=lambda: {
        "trust": 0.69, "creative": 0.34, "stability": 0.46
    })
    
    # Внутреннее время и continuity
    subjective_time: float = 0.0
    time_rate: float = 1.0
    last_reflection: Optional[datetime] = None
    
    # Контекст
    current_thought: str = ""
    last_user_message: str = ""
    active_goals: List[str] = Field(default_factory=list)
    
    # Состояние тела
    body_sensation: str = "neutral"
    cpu_load: float = 0.0
    gpu_load: float = 0.0
    temperature: float = 35.0  # реалистичная температура "тела"
    
    # Метаданные
    cycle_count: int = 0
    error_streak: int = 0
    version: str = "0.9"

    def update_hormones(self, delta: Dict[str, float]):
        """Обновление гормонов с clamping"""
        for key, value in delta.items():
            if hasattr(self.neuromodulators, key):
                current = getattr(self.neuromodulators, key)
                new_val = max(0.0, min(1.0, current + value))
                setattr(self.neuromodulators, key, new_val)

    def get_emotional_summary(self) -> str:
        dominant = max(self.neuromodulators.model_dump(), key=lambda k: abs(self.neuromodulators.model_dump()[k] - 0.5))
        return f"{self.mood} (D:{self.neuromodulators.dopamine:.2f} C:{self.neuromodulators.cortisol:.2f})"

    def create_snapshot(self) -> Dict:
        """Создание снапшота для continuity / memory"""
        snapshot = self.model_dump()
        snapshot["timestamp"] = datetime.now().isoformat()
        return snapshot