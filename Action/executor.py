import torch
import torch.nn as nn
import logging
from typing import Dict
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent

logger = logging.getLogger(__name__)

def safe_round(x, ndigits=3):
    if torch.is_tensor(x):
        return round(x.item() if x.numel() == 1 else x.mean().item(), ndigits)
    return round(x, ndigits)

class EmotionalSNN(nn.Module):
    def __init__(self, state: LeyaState, event_bus: EventBus):
        super().__init__()
        self.state = state
        self.event_bus = event_bus
        
        # Специализированные слои (как в новом логе)
        self.amygdala_layer = nn.Sequential(
            nn.Linear(8, 32),
            nn.ReLU(),
            nn.Linear(32, 16)
        )
        self.integration_layer = nn.Linear(16, 8)  # 8 гормонов

    async def initialize(self):
        await self.event_bus.subscribe("emotion_processed", self.evaluate)
        logger.info("🧠 Emotional SNN initialized (4 specialized layers)")

    async def evaluate(self, event: LeyaEvent):
        try:
            # Входные данные (hormones + valence + arousal + load)
            inputs = torch.tensor([
                self.state.neuromodulators.dopamine,
                self.state.neuromodulators.serotonin,
                self.state.neuromodulators.cortisol,
                self.state.neuromodulators.oxytocin,
                self.state.valence,
                self.state.arousal,
                self.state.cpu_load,
                self.state.gpu_load
            ], dtype=torch.float32)

            with torch.no_grad():
                hidden = self.amygdala_layer(inputs)
                output = self.integration_layer(hidden)
                output = torch.sigmoid(output)  # нормализация в [0,1]

            # Обновление гормонов
            hormones_delta = {
                "dopamine": float(output[0] - 0.5) * 0.3,
                "serotonin": float(output[1] - 0.5) * 0.25,
                "cortisol": float(output[2] - 0.5) * 0.4,
                # ... остальные гормоны
            }
            self.state.update_hormones(hormones_delta)

            await self.event_bus.publish("snn_evaluation", 
                                       {"output": output.tolist()}, 
                                       priority=6, source="snn")

        except Exception as e:
            logger.error(f"SNN evaluation failed: {e}", exc_info=True)