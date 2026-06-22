import asyncio
import logging
import torch
import psutil
from datetime import datetime

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_GPU = True
except:
    HAS_GPU = False

from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent

logger = logging.getLogger(__name__)

class EmbodimentSystem:
    def __init__(self, state: LeyaState, event_bus: EventBus):
        self.state = state
        self.event_bus = event_bus
        self.last_update = datetime.now()

    async def tick(self):
        """200ms тик тела"""
        await self._update_system_metrics()
        await self._generate_sensations()
        
        await self.event_bus.publish(
            "embodiment_update",
            {
                "temperature": self.state.temperature,
                "cpu_load": self.state.cpu_load,
                "sensation": self.state.body_sensation
            },
            priority=4,
            source="embodiment"
        )

    async def _update_system_metrics(self):
        # CPU + RAM
        self.state.cpu_load = psutil.cpu_percent(interval=0.1) / 100.0
        
        # GPU (если доступно)
        if HAS_GPU:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu / 100.0
                self.state.temperature = float(temp)
                self.state.gpu_load = util
            except:
                self.state.temperature = 38.0 + (self.state.cpu_load * 12)
        else:
            self.state.temperature = 36.5 + (self.state.cpu_load * 15)

    async def _generate_sensations(self):
        load = max(self.state.cpu_load, self.state.gpu_load)
        
        if self.state.neuromodulators.cortisol > 0.7 or load > 0.75:
            self.state.body_sensation = "stressed"
        elif load < 0.25 and self.state.neuromodulators.dopamine > 0.6:
            self.state.body_sensation = "relaxed"
        elif 0.4 < load < 0.7:
            self.state.body_sensation = "neutral"
        else:
            self.state.body_sensation = "alert"

        # Интероцепция → Stream of Consciousness
        if self.state.body_sensation == "stressed":
            await self.event_bus.publish(
                "internal_sensation",
                {"text": f"Чувствую напряжение в 'теле'. Нагрузка высокая ({int(load*100)}%)."},
                priority=5,
                source="embodiment"
            )

    async def on_event(self, event: LeyaEvent):
        if event.type == "user_message":
            self.state.temperature = max(36.0, self.state.temperature - 0.8)  # "успокаивается"