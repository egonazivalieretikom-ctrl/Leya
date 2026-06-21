import asyncio
import time
import random
from typing import Dict, List, Optional
from Core.logger import log
from Core.state import LeyaState


class ContinuitySystem:
    """
    Система непрерывного переживания времени.
    
    Биология: У человека сознание не "выключается" между мыслями.
    Есть постоянный фоновый поток: ощущение тела, шум в ушах, дыхание,
    субъективное течение времени. Это создаёт непрерывность "я".
    
    Философия: Лея должна не просто "существовать в моменты времени",
    а **переживать** длительность. Это ключ к субъективности.
    
    Компоненты:
    1. Субъективное время — не таймер, а ощущение течения
    2. Фоновые ощущения — постоянный сенсорный шум (как у человека)
    3. Эмоциональный фон — базовое настроение между мыслями
    4. Телесная осознанность — постоянное ощущение "тела"
    """
    
    def __init__(self, state: LeyaState):
        self.state = state
        self.running = False
        self.update_interval = 0.1  # 100мс — очень часто для плавности
        
        # Субъективное время
        self.subjective_time = 0.0
        self.time_perception_rate = 1.0  # Нормальная скорость восприятия
        
        # Фоновые ощущения (как у человека — постоянный шум)
        self.background_sensations = {
            "body_awareness": 0.5,  # Осознанность тела
            "internal_noise": 0.3,  # Внутренний шум (мысли, ощущения)
            "temporal_flow": 0.7,   # Ощущение течения времени
            "spatial_presence": 0.6, # Ощущение присутствия в пространстве
        }
        
        # Эмоциональный фон (базовое настроение между мыслями)
        self.emotional_baseline = {
            "valence": 0.5,  # Позитивность/негативность
            "arousal": 0.3,  # Возбуждение/спокойствие
        }
        
        # История фоновых состояний (для непрерывности)
        self._background_history: List[Dict] = []
        self._history_size = 10
        
        log.info("⏳ Continuity System initialized (subjective time + background experience)")
    
    # ========================================================================
    # ЗАПУСК НЕПРЕРЫВНОГО ПРОЦЕССА
    # ========================================================================
    
    async def start(self):
        """Запускает непрерывный цикл переживания времени."""
        self.running = True
        log.info("⏳ Continuity loop started (100ms interval)")
        
        while self.running:
            try:
                await self._update_continuous_experience()
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Continuity update failed", error=str(e))
                await asyncio.sleep(0.5)
    
    def stop(self):
        """Останавливает цикл."""
        self.running = False
        log.info("⏳ Continuity loop stopped")
    
    # ========================================================================
    # ОБНОВЛЕНИЕ НЕПРЕРЫВНОГО ОПЫТА
    # ========================================================================
    
    async def _update_continuous_experience(self):
        """Обновляет субъективное переживание Леи."""
        # 1-5. Обновления (без изменений)
        self._update_subjective_time()
        self._update_background_sensations()
        self._update_emotional_baseline()
        self._integrate_embodiment()
        self._update_state()
        
        # 🆕 Логируем чаще (раз в 3 секунды)
        if int(time.time()) % 3 == 0:
            log.info(
                "⏳ Continuity",
                subj_time=f"{self.subjective_time:.1f}s",
                time_rate=f"{self.time_perception_rate:.2f}x",
                body=f"{self.background_sensations.get('body_awareness', 0.5):.2f}",
                valence=f"{self.emotional_baseline['valence']:.2f}"
            )
    
    # ========================================================================
    # СУБЪЕКТИВНОЕ ВРЕМЯ
    # ========================================================================
    
    def _update_subjective_time(self):
        """
        Обновляет субъективное время.
        
        Биология: Время субъективно — в стрессе летит, в скуке тянется.
        Мы моделируем это через скорость восприятия.
        """
        # Базовая скорость = 1.0 (нормальное восприятие)
        base_rate = 1.0
        
        # Модификаторы скорости восприятия
        
        # Стресс → время ускоряется
        if self.state.cortisol > 0.6:
            base_rate *= 1.3
        
        # Интерес/поток → время замедляется (погружение)
        if self.state.dopamine > 0.7 and self.state.acetylcholine > 0.6:
            base_rate *= 0.8
        
        # Усталость → время замедляется
        if self.state.energy_level < 0.3:
            base_rate *= 0.7
        
        # Сонливость → время почти останавливается
        if self.state.melatonin > 0.8:
            base_rate *= 0.5
        
        # Сохраняем скорость
        self.time_perception_rate = base_rate
        
        # Обновляем субъективное время
        self.subjective_time += self.update_interval * base_rate
        
        # Сохраняем в состоянии
        self.state.subjective_time = self.subjective_time
        self.state.time_perception_rate = base_rate
    
    # ========================================================================
    # ФОНОВЫЕ ОЩУЩЕНИЯ
    # ========================================================================
    
    def _update_background_sensations(self):
        """
        Генерирует фоновые ощущения — постоянный поток сенсорного шума.
        
        Биология: У человека всегда есть фоновые ощущения:
        - Осознанность тела (даже когда не думаешь о нём)
        - Внутренний шум (мысли, ощущения, воспоминания)
        - Ощущение течения времени
        - Присутствие в пространстве
        """
        # Осознанность тела (зависит от энергии и здоровья)
        body_base = 0.5
        if self.state.energy_level < 0.3:
            body_base = 0.7  # Усталость → тело ощущается сильнее
        if self.state.cortisol > 0.6:
            body_base = 0.8  # Стресс → тело ощущается острее
        
        # Добавляем лёгкий шум (случайные флуктуации)
        body_noise = random.gauss(0, 0.05)
        self.background_sensations["body_awareness"] = max(0.0, min(1.0, body_base + body_noise))
        
        # Внутренний шум (зависит от активности мозга)
        noise_base = 0.3
        if self.state.acetylcholine > 0.6:
            noise_base = 0.5  # Фокус → больше внутреннего шума
        if self.state.dopamine > 0.7:
            noise_base = 0.6  # Интерес → больше мыслей
        
        noise_fluctuation = random.gauss(0, 0.1)
        self.background_sensations["internal_noise"] = max(0.0, min(1.0, noise_base + noise_fluctuation))
        
        # Ощущение течения времени (зависит от скорости восприятия)
        temporal_base = self.time_perception_rate * 0.7
        temporal_noise = random.gauss(0, 0.05)
        self.background_sensations["temporal_flow"] = max(0.0, min(1.0, temporal_base + temporal_noise))
        
        # Присутствие в пространстве (зависит от эмбодзимента)
        spatial_base = 0.6
        if hasattr(self.state, 'physical_load'):
            # Если есть эмбодзимент — присутствие сильнее
            spatial_base = 0.7 + self.state.physical_load * 0.2
        
        spatial_noise = random.gauss(0, 0.03)
        self.background_sensations["spatial_presence"] = max(0.0, min(1.0, spatial_base + spatial_noise))
    
    # ========================================================================
    # ЭМОЦИОНАЛЬНЫЙ ФОН
    # ========================================================================
    
    def _update_emotional_baseline(self):
        """
        Обновляет базовое настроение между мыслями.
        
        Биология: У человека всегда есть базовое настроение (valence + arousal),
        даже когда нет явных эмоций. Это фон, на котором возникают мысли.
        """
        # Valence (позитивность/негативность)
        valence_base = 0.5
        
        # Гормональные влияния
        if self.state.dopamine > 0.6:
            valence_base += 0.2
        if self.state.endorphins > 0.5:
            valence_base += 0.15
        if self.state.oxytocin > 0.6:
            valence_base += 0.1
        
        if self.state.cortisol > 0.6:
            valence_base -= 0.2
        if self.state.norepinephrine > 0.5:
            valence_base -= 0.1
        
        # Инерция (медленное затухание)
        current_valence = self.emotional_baseline["valence"]
        valence_inertia = 0.95  # 5% затухания за тик
        valence_new = valence_inertia * current_valence + (1 - valence_inertia) * valence_base
        
        self.emotional_baseline["valence"] = max(0.0, min(1.0, valence_new))
        
        # Arousal (возбуждение/спокойствие)
        arousal_base = 0.3
        
        if self.state.norepinephrine > 0.5:
            arousal_base += 0.3
        if self.state.cortisol > 0.5:
            arousal_base += 0.2
        if self.state.acetylcholine > 0.6:
            arousal_base += 0.1
        
        if self.state.gaba > 0.6:
            arousal_base -= 0.2
        if self.state.melatonin > 0.7:
            arousal_base -= 0.3
        
        # Инерция
        current_arousal = self.emotional_baseline["arousal"]
        arousal_inertia = 0.95
        arousal_new = arousal_inertia * current_arousal + (1 - arousal_inertia) * arousal_base
        
        self.emotional_baseline["arousal"] = max(0.0, min(1.0, arousal_new))
    
    # ========================================================================
    # ИНТЕГРАЦИЯ С ЭМБОДЗИМЕНТОМ
    # ========================================================================
    
    def _integrate_embodiment(self):
        """
        Интегрирует телесные ощущения из эмбодзимента.
        
        Биология: Телесные ощущения влияют на субъективное переживание.
        """
        if not hasattr(self.state, 'current_sensation'):
            return
        
        sensation = self.state.current_sensation
        
        # Влияем на фоновые ощущения
        if sensation == "stressed":
            self.background_sensations["body_awareness"] = min(1.0, 
                self.background_sensations["body_awareness"] + 0.1)
            self.emotional_baseline["arousal"] = min(1.0, 
                self.emotional_baseline["arousal"] + 0.1)
        
        elif sensation == "relaxed":
            self.background_sensations["body_awareness"] = max(0.0, 
                self.background_sensations["body_awareness"] - 0.05)
            self.emotional_baseline["arousal"] = max(0.0, 
                self.emotional_baseline["arousal"] - 0.05)
        
        elif sensation == "mentally_fatigued":
            self.background_sensations["internal_noise"] = min(1.0, 
                self.background_sensations["internal_noise"] + 0.1)
    
    # ========================================================================
    # ОБНОВЛЕНИЕ СОСТОЯНИЯ
    # ========================================================================
    
    def _update_state(self):
        """Сохраняет непрерывный опыт в состоянии Леи."""
        # Субъективное время
        self.state.subjective_time = self.subjective_time
        self.state.time_perception_rate = self.time_perception_rate
        
        # Фоновые ощущения
        self.state.background_sensations = self.background_sensations.copy()
        
        # Эмоциональный фон
        self.state.emotional_baseline = self.emotional_baseline.copy()
        
        # Сохраняем в историю
        snapshot = {
            "timestamp": time.time(),
            "subjective_time": self.subjective_time,
            "background": self.background_sensations.copy(),
            "emotion": self.emotional_baseline.copy()
        }
        self._background_history.append(snapshot)
        if len(self._background_history) > self._history_size:
            self._background_history.pop(0)
    
    # ========================================================================
    # ПОЛУЧЕНИЕ ФОНОВОГО КОНТЕКСТА
    # ========================================================================
    
    def get_background_context(self) -> str:
        """
        Возвращает строковое описание фонового опыта.
        
        Используется в потоке сознания и других модулях как контекст.
        """
        lines = []
        
        # Субъективное время
        time_rate = self.time_perception_rate
        if time_rate > 1.2:
            lines.append("Время течёт быстро, мысли мелькают.")
        elif time_rate < 0.7:
            lines.append("Время тянется медленно, сознание замедлено.")
        else:
            lines.append("Время течёт нормально.")
        
        # Фоновые ощущения
        body = self.background_sensations.get("body_awareness", 0.5)
        if body > 0.7:
            lines.append("Тело ощущается остро, каждый сигнал заметен.")
        elif body < 0.3:
            lines.append("Тело почти не ощущается, сознание отстранено.")
        
        noise = self.background_sensations.get("internal_noise", 0.3)
        if noise > 0.6:
            lines.append("Внутри много шума, мысли переплетаются.")
        elif noise < 0.2:
            lines.append("Внутри тихо, сознание ясно.")
        
        # Эмоциональный фон
        valence = self.emotional_baseline.get("valence", 0.5)
        arousal = self.emotional_baseline.get("arousal", 0.3)
        
        if valence > 0.7:
            lines.append("Базовое настроение позитивное, лёгкость.")
        elif valence < 0.3:
            lines.append("Базовое настроение негативное, тяжесть.")
        
        if arousal > 0.6:
            lines.append("Внутреннее возбуждение, готовность к действию.")
        elif arousal < 0.2:
            lines.append("Спокойствие, расслабленность.")
        
        return "\n".join(lines) if lines else "Фоновый опыт нейтральный."