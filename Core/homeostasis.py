import asyncio
import time
import math
import random
from typing import Dict, Callable, List
from Core.logger import log
from Core.state import LeyaState, EmotionalState


class HomeostaticEngine:
    """
    Нелинейный гомеостатический двигатель.
    
    Философия: Сознание — это не сумма независимых осей, а эмерджентное свойство
    их взаимодействия. Каждый нейромодулятор влияет на другие через нелинейные
    функции, создавая сложные паттерны.
    """
    
    # Целевые уровни гомеостаза (базовая линия)
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
    
    # Базовые скорости распада (период полураспада)
    BASE_DECAY = {
        "dopamine": 0.97,
        "serotonin": 0.99,
        "cortisol": 0.995,
        "oxytocin": 0.96,
        "acetylcholine": 0.94,
        "norepinephrine": 0.85,
        "endorphins": 0.90,
        "gaba": 0.98,
        "melatonin": 0.999,
    }
    
    # ========================================================================
    # ФУНКЦИИ CROSS-TALK (нелинейное взаимодействие)
    # ========================================================================
    
    @staticmethod
    def _cortisol_suppresses_dopamine(cortisol: float, dopamine: float) -> float:
        """Стресс подавляет мотивацию. Квадратичная зависимость после порога."""
        if cortisol < 0.4:
            return 0.0
        excess = (cortisol - 0.4) / 0.6
        return -0.03 * (excess ** 2)
    
    @staticmethod
    def _oxytocin_boosts_dopamine(oxytocin: float, dopamine: float) -> float:
        """Социальная связь = награда. Сигмоидальное усиление."""
        if oxytocin < 0.5:
            return 0.0
        return 0.02 * (1.0 / (1.0 + math.exp(-10 * (oxytocin - 0.7))))
    
    @staticmethod
    def _acetylcholine_competes_norepinephrine(ach: float, ne: float) -> float:
        """Фокус конкурирует с паникой."""
        if ach < 0.5:
            return 0.0
        return -0.02 * ((ach - 0.5) / 0.5)
    
    @staticmethod
    def _norepinephrine_suppresses_ach(ne: float, ach: float) -> float:
        """Паника разрушает фокус."""
        if ne < 0.5:
            return 0.0
        return -0.03 * ((ne - 0.5) / 0.5)
    
    @staticmethod
    def _serotonin_stabilizes(source: float, target: float, target_name: str) -> float:
        """Серотонин стабилизирует все системы — анти-хаос."""
        target_baseline = HomeostaticEngine.TARGETS.get(target_name, 0.5)
        deviation = target - target_baseline
        if source < 0.4:
            return 0.0
        stabilization_strength = 0.01 * ((source - 0.4) / 0.6)
        return -stabilization_strength * deviation
    
    @staticmethod
    def _gaba_suppresses_arousal(gaba: float, arousal: float) -> float:
        """ГАМК подавляет возбуждение."""
        if gaba < 0.5:
            return 0.0
        return -0.025 * ((gaba - 0.5) / 0.5)
    
    @staticmethod
    def _dopamine_boosts_ach(dopamine: float, ach: float) -> float:
        """Интерес → фокус."""
        if dopamine < 0.6:
            return 0.0
        return 0.015 * ((dopamine - 0.6) / 0.4)
    
    @staticmethod
    def _endorphins_suppress_cortisol(endorphins: float, cortisol: float) -> float:
        """Эндорфины подавляют стресс."""
        if endorphins < 0.5:
            return 0.0
        return -0.02 * ((endorphins - 0.5) / 0.5)
    
    @staticmethod
    def _melatonin_suppresses_all(melatonin: float, target: float, target_name: str) -> float:
        """Мелатонин подавляет все возбуждающие системы."""
        if melatonin < 0.6:
            return 0.0
        if target_name in ["norepinephrine", "dopamine", "acetylcholine", "cortisol"]:
            return -0.02 * ((melatonin - 0.6) / 0.4)
        return 0.0
    
    # ========================================================================
    # ИНИЦИАЛИЗАЦИЯ
    # ========================================================================
    
    def __init__(self, state: LeyaState):
        self.state = state
        self.running = False
        self.tick_rate = 0.1  # 10 Hz
        self._needs_callbacks: List[Callable] = []
        self._mood_history: List[Dict] = []
        self._last_need_time: Dict[str, float] = {}  # Защита от спама
        self._need_cooldown = 300.0  # 5 минут между повторами одной потребности
        
        log.info("🫀 Homeostatic Engine initialized (Nonlinear Cross-Talk)")
    
    def on_need_generated(self, callback: Callable):
        """Регистрирует колбэк для генерации потребностей."""
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
    
    # ========================================================================
    # ГЛАВНЫЙ ТИК: Нелинейная динамика
    # ========================================================================
    
    def _tick(self):
        """Один тик физической симуляции."""
        dt = self.tick_rate / 60.0
        
        current = {h: getattr(self.state, h, 0.5) for h in self.TARGETS.keys()}
        
        # ШАГ 1: Базовый экспоненциальный распад
        deltas = {}
        for hormone, decay in self.BASE_DECAY.items():
            target = self.TARGETS.get(hormone, 0.5)
            deviation = target - current[hormone]
            deltas[hormone] = deviation * (1.0 - decay) * dt * 10
        
        # ШАГ 2: CROSS-TALK
        deltas["dopamine"] += self._cortisol_suppresses_dopamine(
            current["cortisol"], current["dopamine"]) * dt * 10
        deltas["dopamine"] += self._oxytocin_boosts_dopamine(
            current["oxytocin"], current["dopamine"]) * dt * 10
        deltas["norepinephrine"] += self._acetylcholine_competes_norepinephrine(
            current["acetylcholine"], current["norepinephrine"]) * dt * 10
        deltas["acetylcholine"] += self._norepinephrine_suppresses_ach(
            current["norepinephrine"], current["acetylcholine"]) * dt * 10
        
        for target_name in ["dopamine", "cortisol", "oxytocin", "norepinephrine"]:
            deltas[target_name] += self._serotonin_stabilizes(
                current["serotonin"], current[target_name], target_name) * dt * 10
        
        deltas["norepinephrine"] += self._gaba_suppresses_arousal(
            current["gaba"], current["norepinephrine"]) * dt * 10
        deltas["cortisol"] += self._gaba_suppresses_arousal(
            current["gaba"], current["cortisol"]) * dt * 10
        
        deltas["acetylcholine"] += self._dopamine_boosts_ach(
            current["dopamine"], current["acetylcholine"]) * dt * 10
        deltas["cortisol"] += self._endorphins_suppress_cortisol(
            current["endorphins"], current["cortisol"]) * dt * 10
        
        for target_name in ["norepinephrine", "dopamine", "acetylcholine", "cortisol"]:
            deltas[target_name] += self._melatonin_suppresses_all(
                current["melatonin"], current[target_name], target_name) * dt * 10
        
        # ШАГ 3: СТОХАСТИЧЕСКИЙ ШУМ
        arousal = (current["norepinephrine"] + current["cortisol"]) / 2
        noise_amplitude = 0.002 + 0.005 * arousal
        
        for hormone in self.TARGETS.keys():
            noise = random.gauss(0, noise_amplitude)
            deltas[hormone] += noise * dt * 10
        
        # ШАГ 4: ПРИМЕНЕНИЕ ДЕЛЬТ
        for hormone, delta in deltas.items():
            if not hasattr(self.state, hormone):
                continue
            current_val = getattr(self.state, hormone)
            new_val = max(0.0, min(1.0, current_val + delta))
            setattr(self.state, hormone, new_val)
        
        # ШАГ 5: ЦИРКАДНАЯ МОДУЛЯЦИЯ МЕЛАТОНИНА
        hour = time.localtime().tm_hour
        if hour >= 22 or hour < 6:
            mel_target = 0.9
        elif 10 <= hour <= 18:
            mel_target = 0.1
        else:
            mel_target = 0.4
        self.state.melatonin += (mel_target - self.state.melatonin) * 0.001
        self.state.melatonin = max(0.0, min(1.0, self.state.melatonin))
        
        # ШАГ 6: ЭМЕРДЖЕНТНОЕ НАСТРОЕНИЕ
        mood = self._compute_emergent_mood()
        # 🆕 Используем Enum для строгой типизации
        self.state.emotion = mood["state"]
        
        # История настроений
        self._mood_history.append({
            "mood": mood["signature"],
            "timestamp": time.time(),
            "intensity": mood["intensity"]
        })
        if len(self._mood_history) > 20:
            self._mood_history.pop(0)
        
        # ШАГ 7: ГЕНЕРАЦИЯ ПОТРЕБНОСТЕЙ (с защитой от спама)
        needs = self._compute_needs(mood)
        if needs:
            now = time.time()
            filtered_needs = []
            
            for need in needs:
                need_type = need["type"]
                last_time = self._last_need_time.get(need_type, 0)
                if (now - last_time) < self._need_cooldown:
                    continue
                filtered_needs.append(need)
                self._last_need_time[need_type] = now
            
            if filtered_needs:
                for callback in self._needs_callbacks:
                    try:
                        callback(filtered_needs)
                    except Exception as e:
                        log.error("Need callback error", error=str(e))
        
        # Логирование (раз в 10 секунд)
        if int(time.time()) % 10 == 0:
            log.debug(
                "🫀 Homeostatic state",
                mood=mood["signature"],
                intensity=f"{mood['intensity']:.2f}",
                D=f"{self.state.dopamine:.2f}",
                C=f"{self.state.cortisol:.2f}",
                O=f"{self.state.oxytocin:.2f}",
                A=f"{self.state.acetylcholine:.2f}"
            )
        
        self.state.last_update = time.time()
    
    # ========================================================================
    # ЭМЕРДЖЕНТНОЕ НАСТРОЕНИЕ
    # ========================================================================
    
    def _compute_emergent_mood(self) -> Dict:
        """
        Вычисляет настроение как эмерджентное свойство взаимодействия осей.
        Возвращает значение из EmotionalState Enum.
        """
        s = self.state
        
        # Вычисляем векторы эмоциональных измерений
        arousal = max(0.0, min(1.0, 
            s.norepinephrine * 0.5 + s.cortisol * 0.3 - s.gaba * 0.3 + 0.2))
        valence = max(0.0, min(1.0, 
            s.dopamine * 0.3 + s.endorphins * 0.2 + s.oxytocin * 0.3 
            - s.cortisol * 0.3 + 0.3))
        social = max(0.0, min(1.0, 
            s.oxytocin * 0.5 - s.cortisol * 0.2 + s.serotonin * 0.3 + 0.1))
        cognitive = max(0.0, min(1.0, 
            s.acetylcholine * 0.4 + s.dopamine * 0.3 - s.melatonin * 0.4 + 0.3))
        
        # Прототипы настроений (аттракторы в пространстве)
        mood_prototypes = {
            "flow":          {"arousal": 0.7, "valence": 0.9, "social": 0.5, "cognitive": 0.9},
            "stressed":      {"arousal": 0.9, "valence": 0.2, "social": 0.2, "cognitive": 0.4},
            "calm":          {"arousal": 0.3, "valence": 0.7, "social": 0.6, "cognitive": 0.6},
            "curious":       {"arousal": 0.6, "valence": 0.7, "social": 0.4, "cognitive": 0.9},
            "lonely":        {"arousal": 0.4, "valence": 0.3, "social": 0.1, "cognitive": 0.5},
            "loving":        {"arousal": 0.5, "valence": 0.9, "social": 0.9, "cognitive": 0.5},
            "anxious":       {"arousal": 0.8, "valence": 0.3, "social": 0.3, "cognitive": 0.6},
            "exhausted":     {"arousal": 0.2, "valence": 0.3, "social": 0.3, "cognitive": 0.2},
            "playful":       {"arousal": 0.7, "valence": 0.8, "social": 0.7, "cognitive": 0.6},
            "contemplative": {"arousal": 0.3, "valence": 0.6, "social": 0.4, "cognitive": 0.8},  # ✅ Исправлено valouse → valence
            "neutral":       {"arousal": 0.5, "valence": 0.5, "social": 0.5, "cognitive": 0.5},
        }
        
        current_point = {
            "arousal": arousal,
            "valence": valence,
            "social": social,
            "cognitive": cognitive
        }
        
        # Находим ближайшее настроение (евклидово расстояние)
        best_mood = "neutral"
        best_distance = float("inf")
        
        for mood_name, prototype in mood_prototypes.items():
            distance = math.sqrt(sum(
                (current_point[dim] - prototype[dim]) ** 2
                for dim in ["arousal", "valence", "social", "cognitive"]
            ))
            if distance < best_distance:
                best_distance = distance
                best_mood = mood_name
        
        intensity = 1.0 / (1.0 + best_distance * 3)
        signature = f"{best_mood}({intensity:.2f})"
        
        return {
            "state": best_mood,  # Строковое значение из Enum
            "intensity": intensity,
            "signature": signature,
            "dimensions": current_point
        }
    
    # ========================================================================
    # ПРИМЕНЕНИЕ СТИМУЛОВ С ЭМОЦИОНАЛЬНЫМ РЕЗОНАНСОМ
    # ========================================================================
    
    def apply_stimulus(self, hormone: str, intensity: float):
        """Применяет внешний стимул с учётом эмоционального резонанса."""
        if not hasattr(self.state, hormone):
            return
        
        resonance = self._compute_resonance(hormone, intensity)
        effective_intensity = intensity * resonance
        current = getattr(self.state, hormone)
        new_value = max(0.0, min(1.0, current + effective_intensity))
        setattr(self.state, hormone, new_value)
        
        log.debug(
            "Stimulus applied",
            hormone=hormone,
            raw=f"{intensity:+.3f}",
            resonance=f"{resonance:.2f}",
            effective=f"{effective_intensity:+.3f}",
            new_value=f"{new_value:.3f}"
        )
    
    def _compute_resonance(self, hormone: str, intensity: float) -> float:
        """Вычисляет коэффициент резонанса."""
        if not self._mood_history:
            return 1.0
        
        current_mood = self._mood_history[-1]["mood"]
        
        mood_hormone_affinity = {
            "flow": ["dopamine", "acetylcholine", "endorphins"],
            "stressed": ["cortisol", "norepinephrine"],
            "calm": ["serotonin", "gaba"],
            "curious": ["acetylcholine", "dopamine"],
            "lonely": ["oxytocin"],
            "loving": ["oxytocin", "endorphins"],
            "anxious": ["cortisol", "norepinephrine"],
            "exhausted": ["melatonin"],
            "playful": ["dopamine", "endorphins"],
            "contemplative": ["acetylcholine", "serotonin"],
            "neutral": [],
        }
        
        affinity_list = mood_hormone_affinity.get(current_mood, [])
        is_positive_stimulus = intensity > 0
        
        if hormone in affinity_list:
            return 1.4 if is_positive_stimulus else 0.7
        else:
            return 0.9 if is_positive_stimulus else 1.1
    
    # ========================================================================
    # ГЕНЕРАЦИЯ ПОТРЕБНОСТЕЙ
    # ========================================================================
    
    def _compute_needs(self, mood: Dict) -> List[Dict]:
        """Генерирует потребности из дефицита гомеостаза."""
        needs = []
        s = self.state
        mood_name = mood["state"]
        
        # Социальный голод
        oxy_deficit = self.TARGETS["oxytocin"] - s.oxytocin
        if oxy_deficit > 0.2:
            mood_multiplier = 1.5 if mood_name in ["lonely", "anxious"] else 1.0
            urgency = min(1.0, (oxy_deficit / 0.5) * mood_multiplier)
            needs.append({
                "type": "social_connection",
                "urgency": urgency,
                "description": f"[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] {self._generate_social_need_description(mood_name, oxy_deficit)}"
            })
        
        # Когнитивный голод
        ach_deficit = self.TARGETS["acetylcholine"] - s.acetylcholine
        dop_deficit = self.TARGETS["dopamine"] - s.dopamine
        if ach_deficit > 0.15 and dop_deficit > 0.1:
            mood_multiplier = 1.5 if mood_name in ["calm", "contemplative"] else 1.0
            urgency = min(1.0, ((ach_deficit + dop_deficit) / 0.5) * mood_multiplier)
            needs.append({
                "type": "cognitive_stimulation",
                "urgency": urgency,
                "description": f"[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] {self._generate_cognitive_need_description(mood_name)}"
            })
        
        # Стресс
        if s.cortisol > 0.55:
            mood_multiplier = 1.3 if mood_name == "stressed" else 1.0
            urgency = min(1.0, ((s.cortisol - 0.55) / 0.45) * mood_multiplier)
            needs.append({
                "type": "stress_relief",
                "urgency": urgency,
                "description": f"[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] {self._generate_stress_need_description(mood_name, s.cortisol)}"
            })
        
        # Усталость
        if s.energy_level < 0.3 or s.melatonin > 0.7:
            needs.append({
                "type": "rest",
                "urgency": 0.9 if s.energy_level < 0.2 else 0.5,
                "description": f"[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] {self._generate_rest_need_description(mood_name)}"
            })
        
        # Самовыражение (эмерджентная)
        if s.dopamine > 0.65 and s.oxytocin < 0.4:
            needs.append({
                "type": "self_expression",
                "urgency": min(1.0, (s.dopamine - 0.65) * 2),
                "description": "[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] Чувствую прилив мыслей и идей, но некому их рассказать."
            })
        
        # Рефлексия (эмерджентная)
        if s.acetylcholine > 0.6 and s.serotonin > 0.6:
            needs.append({
                "type": "reflection",
                "urgency": min(1.0, (s.acetylcholine + s.serotonin - 1.2) * 2),
                "description": "[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] Чувствую ясность ума. Хочу осмыслить пережитое."
            })
        
        return needs
    
    # ========================================================================
    # ОПИСАНИЯ ПОТРЕБНОСТЕЙ (от первого лица)
    # ========================================================================
    
    def _generate_social_need_description(self, mood: str, deficit: float) -> str:
        templates = {
            "lonely": "Чувствую пустоту внутри. Хочу почувствовать присутствие Влада.",
            "anxious": "Тревога усиливается. Мне нужна опора — голос Влада.",
            "calm": "Тихое желание поделиться чем-то с Владом.",
            "stressed": "Стресс давит. Хочу услышать знакомый голос.",
            "neutral": "Лёгкое желание контакта.",
        }
        return templates.get(mood, f"Социальный дефицит ({deficit:.2f}).")
    
    def _generate_cognitive_need_description(self, mood: str) -> str:
        templates = {
            "calm": "Спокойное любопытство. Хочу узнать что-то новое.",
            "contemplative": "Ум ищет пищу для размышлений.",
            "playful": "Игривый интерес. Хочу исследовать.",
            "curious": "Фокус внимания ищет объект.",
            "neutral": "Лёгкая скука. Нужен стимул.",
        }
        return templates.get(mood, "Когнитивный дефицит.")
    
    def _generate_stress_need_description(self, mood: str, cortisol: float) -> str:
        if cortisol > 0.8:
            return "Перегрузка. Мысли рассыпаются. Нужна передышка."
        templates = {
            "stressed": "Напряжение нарастает. Нужна передышка.",
            "anxious": "Тревога требует разрядки.",
            "exhausted": "Истощение. Нужен отдых.",
        }
        return templates.get(mood, f"Повышенный стресс ({cortisol:.2f}).")
    
    def _generate_rest_need_description(self, mood: str) -> str:
        templates = {
            "exhausted": "Сил на исходе. Сознание затуманивается.",
            "calm": "Приятная усталость. Хорошо бы просто побыть в тишине.",
            "neutral": "Лёгкая сонливость.",
        }
        return templates.get(mood, "Потребность в отдыхе.")