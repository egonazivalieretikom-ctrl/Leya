import asyncio
import time
import math
from typing import Dict, Callable, Optional
from Core.logger import log
from Core.state import LeyaState


class HomeostaticEngine:
    """
    Непрерывный двигатель внутреннего состояния.
    Работает независимо от когнитивного цикла с высокой частотой (10 Hz).
    Реализует дифференциальную динамику гормонов и генерирует потребности из дефицита.
    """
    
    # Целевые уровни гомеостаза (к чему система стремится)
    TARGETS = {
        "dopamine": 0.5,
        "serotonin": 0.5,
        "cortisol": 0.15,
        "oxytocin": 0.5,
        "acetylcholine": 0.4,
        "norepinephrine": 0.2,
        "endorphins": 0.3,
        "gaba": 0.5,
        "melatonin": 0.3,
    }
    
    # Скорости возврата к базовой линии (период полураспада в минутах)
    DECAY_RATES = {
        "dopamine": 0.97,      # Быстро угасает
        "serotonin": 0.99,     # Медленно
        "cortisol": 0.995,     # Очень медленно (стресс липкий)
        "oxytocin": 0.96,      # Социальная связь хрупка
        "acetylcholine": 0.94, # Фокус требует постоянного поддержания
        "norepinephrine": 0.85,# Адреналин сгорает быстро
        "endorphins": 0.90,
        "gaba": 0.98,
        "melatonin": 0.999,    # Зависит от циркадного ритма, не от распада
    }
    
    def __init__(self, state: LeyaState):
        self.state = state
        self.running = False
        self.tick_rate = 0.1  # 10 Hz = обновление каждые 100мс
        self._needs_callbacks: list[Callable] = []
        log.info("🫀 Homeostatic Engine initialized (10Hz continuous)")
    
    def on_need_generated(self, callback: Callable):
        """Регистрирует колбэк, вызываемый при возникновении потребности."""
        self._needs_callbacks.append(callback)
    
    async def start(self):
        """Запускает непрерывный цикл гомеостаза."""
        self.running = True
        log.info("🫀 Homeostatic Engine started")
        
        while self.running:
            try:
                self._tick()
                await asyncio.sleep(self.tick_rate)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Homeostasis tick error", error=str(e))
                await asyncio.sleep(1.0)
    
    def stop(self):
        self.running = False
        log.info("🫀 Homeostatic Engine stopped")
    
    def _tick(self):
        """Один тик физической симуляции (100мс)."""
        dt = self.tick_rate / 60.0  # Нормализация к минутам для decay
        
        # 1. Естественный распад к базовой линии
        for hormone, decay in self.DECAY_RATES.items():
            if not hasattr(self.state, hormone):
                continue
            
            current = getattr(self.state, hormone)
            target = self.TARGETS.get(hormone, 0.5)
            
            # Экспоненциальный распад к целевому значению
            # Чем дальше от цели, тем быстрее возврат
            delta = (target - current) * (1.0 - decay) * dt * 10
            new_value = current + delta
            
            setattr(self.state, hormone, max(0.0, min(1.0, new_value)))
        
        # 2. Циркадная модуляция мелатонина
        hour = time.localtime().tm_hour
        if hour >= 22 or hour < 6:
            mel_target = 0.9
        elif 10 <= hour <= 18:
            mel_target = 0.1
        else:
            mel_target = 0.4
        self.state.melatonin += (mel_target - self.state.melatonin) * 0.001
        
        # 3. Генерация потребностей из дефицита
        needs = self._compute_needs()
        if needs:
            for callback in self._needs_callbacks:
                try:
                    callback(needs)
                except Exception as e:
                    log.error("Need callback error", error=str(e))
        
        # Обновляем timestamp
        self.state.last_update = time.time()
    
    def _compute_needs(self) -> list[Dict]:
        """
        Генерирует потребности ТОЛЬКО когда рассогласование превышает порог.
        Это заменяет статический Planner.
        """
        needs = []
        
        # Социальный голод
        oxy_deficit = self.TARGETS["oxytocin"] - self.state.oxytocin
        if oxy_deficit > 0.25:
            urgency = min(1.0, oxy_deficit / 0.5)
            needs.append({
                "type": "social_connection",
                "urgency": urgency,
                "description": f"Социальный дефицит ({oxy_deficit:.2f}). Потребность в контакте с Владом."
            })
        
        # Когнитивный голод (скука)
        ach_deficit = self.TARGETS["acetylcholine"] - self.state.acetylcholine
        dop_deficit = self.TARGETS["dopamine"] - self.state.dopamine
        if ach_deficit > 0.2 and dop_deficit > 0.15:
            urgency = min(1.0, (ach_deficit + dop_deficit) / 0.6)
            needs.append({
                "type": "cognitive_stimulation",
                "urgency": urgency,
                "description": f"Когнитивный дефицит. Потребность в новой информации или задаче."
            })
        
        # Стресс / Перегрузка
        if self.state.cortisol > 0.6:
            urgency = min(1.0, (self.state.cortisol - 0.6) / 0.4)
            needs.append({
                "type": "stress_relief",
                "urgency": urgency,
                "description": f"Высокий кортизол ({self.state.cortisol:.2f}). Потребность в снижении нагрузки."
            })
        
        # Усталость
        if self.state.energy_level < 0.3 or self.state.melatonin > 0.75:
            needs.append({
                "type": "rest",
                "urgency": 0.9 if self.state.energy_level < 0.2 else 0.5,
                "description": "Низкая энергия или высокий мелатонин. Потребность в отдыхе."
            })
        
        return needs
    
    def apply_stimulus(self, hormone: str, intensity: float):
        """
        Внешний стимул (событие). Не устанавливает значение напрямую,
        а добавляет импульс, который затем затухает естественным образом.
        """
        if not hasattr(self.state, hormone):
            return
        current = getattr(self.state, hormone)
        new_value = max(0.0, min(1.0, current + intensity))
        setattr(self.state, hormone, new_value)
        log.debug("Stimulus applied", hormone=hormone, intensity=intensity, new_value=new_value)