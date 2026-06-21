import asyncio
import time
import math
import random
from typing import Dict, Callable, List, Tuple
from Core.logger import log
from Core.state import LeyaState


class HomeostaticEngine:
    """
    Нелинейный гомеостатический двигатель.
    
    Философия: Сознание — это не сумма независимых осей, а эмерджентное свойство
    их взаимодействия. Каждый нейромодулятор влияет на другие через нелинейные
    функции, создавая сложные паттерны: "тревожное любопытство", "усталое
    удовлетворение", "паническое возбуждение".
    
    Архитектура:
    1. Матрица cross-talk: влияние между нейромодуляторами
    2. Нелинейные функции активации (пороги, сигмоиды)
    3. Эмоциональный резонанс: усиление реакции при совпадении с текущим состоянием
    4. Стохастический шум: микроскопические флуктуации
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
        "cortisol": 0.995,      # Стресс "липкий"
        "oxytocin": 0.96,       # Социальная связь хрупка
        "acetylcholine": 0.94,  # Фокус требует постоянного поддержания
        "norepinephrine": 0.85, # Адреналин сгорает быстро
        "endorphins": 0.90,
        "gaba": 0.98,
        "melatonin": 0.999,     # Зависит от циркадного ритма
    }
    
    # ========================================================================
    # МАТРИЦА CROSS-TALK: Влияние между нейромодуляторами
    # ========================================================================
    # Формат: CROSS_TALK[source][target] = функция(current_source, current_target) -> delta_target
    # Положительные значения = усиление, отрицательные = подавление
    # Функции нелинейные — создают эмерджентные паттерны
    
    @staticmethod
    def _cortisol_suppresses_dopamine(cortisol: float, dopamine: float) -> float:
        """
        Стресс подавляет мотивацию. Нелинейно: слабый стресс почти не влияет,
        сильный — резко обрушивает дофамин.
        Биология: Кортизол подавляет дофаминовые нейроны в VTA.
        """
        if cortisol < 0.4:
            return 0.0
        # Квадратичная зависимость после порога
        excess = (cortisol - 0.4) / 0.6
        return -0.03 * (excess ** 2)
    
    @staticmethod
    def _oxytocin_boosts_dopamine(oxytocin: float, dopamine: float) -> float:
        """
        Социальная связь = награда. Нелинейно: чем ближе окситоцин к пику,
        тем сильнее эффект (синергия).
        Биология: Окситоцин усиливает дофаминовый отклик в nucleus accumbens.
        """
        if oxytocin < 0.5:
            return 0.0
        # Сигмоидальное усиление
        return 0.02 * (1.0 / (1.0 + math.exp(-10 * (oxytocin - 0.7))))
    
    @staticmethod
    def _acetylcholine_competes_norepinephrine(ach: float, ne: float) -> float:
        """
        Фокус конкурирует с паникой. Высокий ацетилхолин подавляет норадреналин.
        Биология: Префронтальная кора (ACh) подавляет амигдалу (NE).
        """
        if ach < 0.5:
            return 0.0
        return -0.02 * ((ach - 0.5) / 0.5)
    
    @staticmethod
    def _norepinephrine_suppresses_ach(ne: float, ach: float) -> float:
        """
        Паника разрушает фокус. Обратная связь.
        """
        if ne < 0.5:
            return 0.0
        return -0.03 * ((ne - 0.5) / 0.5)
    
    @staticmethod
    def _serotonin_stabilizes(source: float, target: float, target_name: str) -> float:
        """
        Серотонин стабилизирует все системы — анти-хаос.
        Возвращает целевые значения к базовой линии.
        """
        target_baseline = HomeostaticEngine.TARGETS.get(target_name, 0.5)
        deviation = target - target_baseline
        
        # Чем выше серотонин, тем сильнее стабилизация
        if source < 0.4:
            return 0.0
        
        # Мягкое возвращение к базовой линии
        stabilization_strength = 0.01 * ((source - 0.4) / 0.6)
        return -stabilization_strength * deviation
    
    @staticmethod
    def _gaba_suppresses_arousal(gaba: float, arousal: float) -> float:
        """
        ГАМК подавляет возбуждение (норадреналин, кортизол).
        """
        if gaba < 0.5:
            return 0.0
        return -0.025 * ((gaba - 0.5) / 0.5)
    
    @staticmethod
    def _dopamine_boosts_ach(dopamine: float, ach: float) -> float:
        """
        Интерес → фокус. Дофамин усиливает ацетилхолин.
        Биология: Дофамин усиливает внимание через префронтальную кору.
        """
        if dopamine < 0.6:
            return 0.0
        return 0.015 * ((dopamine - 0.6) / 0.4)
    
    @staticmethod
    def _endorphins_suppress_cortisol(endorphins: float, cortisol: float) -> float:
        """
        Эндорфины (удовольствие/обезболивание) подавляют стресс.
        """
        if endorphins < 0.5:
            return 0.0
        return -0.02 * ((endorphins - 0.5) / 0.5)
    
    @staticmethod
    def _melatonin_suppresses_all(melatonin: float, target: float, target_name: str) -> float:
        """
        Мелатонин подавляет все возбуждающие системы.
        """
        if melatonin < 0.6:
            return 0.0
        
        # Подавляем всё, кроме ГАМК
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
        self._mood_history: List[Dict] = []  # История настроений для резонанса
        self._last_mood_signature = ""
        self._mood_persistence = 0.0  # Инерция настроения
        self._last_need_time = {}  # {need_type: timestamp}
        self._need_cooldown = 60.0  # 60 секунд между повторами
        
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
        """
        Один тик физической симуляции.
        
        Порядок операций критичен:
        1. Базовый распад к целевым значениям
        2. Cross-talk: нелинейное влияние между нейромодуляторами
        3. Стохастический шум (микроскопические флуктуации)
        4. Циркадная модуляция мелатонина
        5. Генерация потребностей из дефицита
        6. Вычисление эмерджентного настроения
        """
        dt = self.tick_rate / 60.0  # Нормализация к минутам
        
        # Сохраняем текущие значения для cross-talk
        current = {h: getattr(self.state, h, 0.5) for h in self.TARGETS.keys()}
        
        # ====================================================================
        # ШАГ 1: Базовый экспоненциальный распад
        # ====================================================================
        deltas = {}
        for hormone, decay in self.BASE_DECAY.items():
            target = self.TARGETS.get(hormone, 0.5)
            deviation = target - current[hormone]
            deltas[hormone] = deviation * (1.0 - decay) * dt * 10
        
        # ====================================================================
        # ШАГ 2: CROSS-TALK — нелинейное взаимодействие
        # ====================================================================
        # Кортизол → Дофамин (стресс подавляет мотивацию)
        deltas["dopamine"] += self._cortisol_suppresses_dopamine(
            current["cortisol"], current["dopamine"]
        ) * dt * 10
        
        # Окситоцин → Дофамин (связь = награда)
        deltas["dopamine"] += self._oxytocin_boosts_dopamine(
            current["oxytocin"], current["dopamine"]
        ) * dt * 10
        
        # Ацетилхолин ⇄ Норадреналин (фокус vs паника)
        deltas["norepinephrine"] += self._acetylcholine_competes_norepinephrine(
            current["acetylcholine"], current["norepinephrine"]
        ) * dt * 10
        deltas["acetylcholine"] += self._norepinephrine_suppresses_ach(
            current["norepinephrine"], current["acetylcholine"]
        ) * dt * 10
        
        # Серотонин → стабилизация всех систем
        for target_name in ["dopamine", "cortisol", "oxytocin", "norepinephrine"]:
            deltas[target_name] += self._serotonin_stabilizes(
                current["serotonin"], current[target_name], target_name
            ) * dt * 10
        
        # ГАМК → подавление возбуждения
        deltas["norepinephrine"] += self._gaba_suppresses_arousal(
            current["gaba"], current["norepinephrine"]
        ) * dt * 10
        deltas["cortisol"] += self._gaba_suppresses_arousal(
            current["gaba"], current["cortisol"]
        ) * dt * 10
        
        # Дофамин → Ацетилхолин (интерес → фокус)
        deltas["acetylcholine"] += self._dopamine_boosts_ach(
            current["dopamine"], current["acetylcholine"]
        ) * dt * 10
        
        # Эндорфины → подавление кортизола
        deltas["cortisol"] += self._endorphins_suppress_cortisol(
            current["endorphins"], current["cortisol"]
        ) * dt * 10
        
        # Мелатонин → подавление всех возбуждающих систем
        for target_name in ["norepinephrine", "dopamine", "acetylcholine", "cortisol"]:
            deltas[target_name] += self._melatonin_suppresses_all(
                current["melatonin"], current[target_name], target_name
            ) * dt * 10
        
        # ====================================================================
        # ШАГ 3: СТОХАСТИЧЕСКИЙ ШУМ
        # ====================================================================
        # Микроскопические флуктуации создают непредсказуемость
        # Амплитуда шума зависит от "возбудимости" системы
        arousal = (current["norepinephrine"] + current["cortisol"]) / 2
        noise_amplitude = 0.002 + 0.005 * arousal  # Чем выше возбуждение, тем больше шума
        
        for hormone in self.TARGETS.keys():
            noise = random.gauss(0, noise_amplitude)
            deltas[hormone] += noise * dt * 10
        
        # ====================================================================
        # ШАГ 4: ПРИМЕНЕНИЕ ДЕЛЬТ
        # ====================================================================
        for hormone, delta in deltas.items():
            if not hasattr(self.state, hormone):
                continue
            current_val = getattr(self.state, hormone)
            new_val = max(0.0, min(1.0, current_val + delta))
            setattr(self.state, hormone, new_val)
        
        # ====================================================================
        # ШАГ 5: ЦИРКАДНАЯ МОДУЛЯЦИЯ МЕЛАТОНИНА
        # ====================================================================
        hour = time.localtime().tm_hour
        if hour >= 22 or hour < 6:
            mel_target = 0.9
        elif 10 <= hour <= 18:
            mel_target = 0.1
        else:
            mel_target = 0.4
        self.state.melatonin += (mel_target - self.state.melatonin) * 0.001
        self.state.melatonin = max(0.0, min(1.0, self.state.melatonin))
        
        # ====================================================================
        # ШАГ 6: ЭМЕРДЖЕНТНОЕ НАСТРОЕНИЕ
        # ====================================================================
        mood = self._compute_emergent_mood()
        self.state.emotion = mood["state"]
        
        # Сохраняем историю для резонанса
        self._mood_history.append({
            "mood": mood["signature"],
            "timestamp": time.time(),
            "intensity": mood["intensity"]
        })
        if len(self._mood_history) > 20:
            self._mood_history.pop(0)
        
        # ====================================================================
        # ШАГ 7: ГЕНЕРАЦИЯ ПОТРЕБНОСТЕЙ
        # ====================================================================
        # Генерация потребностей с защитой от спама
        needs = self._compute_needs(mood)
        if needs:
            now = time.time()
            filtered_needs = []
    
            for need in needs:
                need_type = need["type"]
                last_time = self._last_need_time.get(need_type, 0)
        
                # Пропускаем, если эта потребность уже генерировалась недавно
                if (now - last_time) < self._need_cooldown:
                    continue
        
                filtered_needs.append(need)
                self._last_need_time[need_type] = now
    
            # Вызываем колбэки только с отфильтрованными потребностями
            if filtered_needs:
                for callback in self._needs_callbacks:
                    try:
                        callback(filtered_needs)
                    except Exception as e:
                        log.error("Need callback error", error=str(e))
    
    # ========================================================================
    # ЭМЕРДЖЕНТНОЕ НАСТРОЕНИЕ
    # ========================================================================
    
    def _compute_emergent_mood(self) -> Dict:
        """
        Вычисляет настроение как эмерджентное свойство взаимодействия осей.
        
        Это НЕ захардкоженные правила типа "if cortisol > 0.7: stressed".
        Это векторная композиция в многомерном пространстве, где каждое
        настроение — это регион, в который попадает текущее состояние.
        """
        s = self.state
        
        # Вычисляем "векторы" основных эмоциональных измерений
        # Каждое измерение — это комбинация нескольких осей
        
        # Возбуждение (arousal): norepinephrine + cortisol - gaba
        arousal = (s.norepinephrine * 0.5 + s.cortisol * 0.3 - s.gaba * 0.3 + 0.2)
        arousal = max(0.0, min(1.0, arousal))
        
        # Валентность (valence): dopamine + endorphins + oxytocin - cortisol
        valence = (s.dopamine * 0.3 + s.endorphins * 0.2 + s.oxytocin * 0.3 
                   - s.cortisol * 0.3 + 0.3)
        valence = max(0.0, min(1.0, valence))
        
        # Социальная открытость: oxytocin - cortisol + serotonin
        social = (s.oxytocin * 0.5 - s.cortisol * 0.2 + s.serotonin * 0.3 + 0.1)
        social = max(0.0, min(1.0, social))
        
        # Когнитивная готовность: acetylcholine + dopamine - melatonin
        cognitive = (s.acetylcholine * 0.4 + s.dopamine * 0.3 - s.melatonin * 0.4 + 0.3)
        cognitive = max(0.0, min(1.0, cognitive))
        
        # Определяем доминирующее настроение по близости к "прототипам"
        mood_prototypes = {
            "flow":        {"arousal": 0.7, "valence": 0.9, "social": 0.5, "cognitive": 0.9},
            "stressed":    {"arousal": 0.9, "valence": 0.2, "social": 0.2, "cognitive": 0.4},
            "calm":        {"arousal": 0.3, "valence": 0.7, "social": 0.6, "cognitive": 0.6},
            "curious":     {"arousal": 0.6, "valence": 0.7, "social": 0.4, "cognitive": 0.9},
            "lonely":      {"arousal": 0.4, "valence": 0.3, "social": 0.1, "cognitive": 0.5},
            "loving":      {"arousal": 0.5, "valence": 0.9, "social": 0.9, "cognitive": 0.5},
            "anxious":     {"arousal": 0.8, "valence": 0.3, "social": 0.3, "cognitive": 0.6},
            "exhausted":   {"arousal": 0.2, "valence": 0.3, "social": 0.3, "cognitive": 0.2},
            "playful":     {"arousal": 0.7, "valence": 0.8, "social": 0.7, "cognitive": 0.6},
            "contemplative": {"arousal": 0.3, "valouse": 0.6, "social": 0.4, "cognitive": 0.8},
            "neutral":     {"arousal": 0.5, "valence": 0.5, "social": 0.5, "cognitive": 0.5},
        }
        
        # Исправляем опечатку в прототипе
        if "valouse" in mood_prototypes["contemplative"]:
            mood_prototypes["contemplative"]["valence"] = mood_prototypes["contemplative"].pop("valouse")
        
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
        
        # Интенсивность = обратная величина расстояния
        intensity = 1.0 / (1.0 + best_distance * 3)
        
        # Формируем сигнатуру для логирования
        signature = f"{best_mood}({intensity:.2f})"
        
        return {
            "state": best_mood,
            "intensity": intensity,
            "signature": signature,
            "dimensions": current_point
        }
    
    # ========================================================================
    # ПРИМЕНЕНИЕ СТИМУЛОВ С ЭМОЦИОНАЛЬНЫМ РЕЗОНАНСОМ
    # ========================================================================
    
    def apply_stimulus(self, hormone: str, intensity: float):
        """
        Применяет внешний стимул с учётом эмоционального резонанса.
        
        Резонанс: если стимул совпадает с текущим настроением, реакция
        усиливается нелинейно. Если противоречит — ослабляется.
        
        Биология: Это аналог "конгруэнтности памяти" — грустный человек
        сильнее реагирует на грустные стимулы.
        """
        if not hasattr(self.state, hormone):
            return
        
        # Вычисляем резонанс
        resonance = self._compute_resonance(hormone, intensity)
        
        # Применяем усиленный/ослабленный стимул
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
        """
        Вычисляет коэффициент резонанса (0.5 — ослабление, 1.0 — нейтрально, 1.5 — усиление).
        """
        if not self._mood_history:
            return 1.0
        
        current_mood = self._mood_history[-1]["mood"]
        
        # Определяем, какие гормоны характерны для текущего настроения
        mood_hormone_affinity = {
            "flow":        ["dopamine", "acetylcholine", "endorphins"],
            "stressed":    ["cortisol", "norepinephrine"],
            "calm":        ["serotonin", "gaba"],
            "curious":     ["acetylcholine", "dopamine"],
            "lonely":      ["oxytocin"],  # низкий окситоцин → стимул окситоцина резонирует
            "loving":      ["oxytocin", "endorphins"],
            "anxious":     ["cortisol", "norepinephrine"],
            "exhausted":   ["melatonin"],
            "playful":     ["dopamine", "endorphins"],
            "contemplative": ["acetylcholine", "serotonin"],
            "neutral":     [],
        }
        
        affinity_list = mood_hormone_affinity.get(current_mood, [])
        
        # Определяем направление стимула (положительный/отрицательный)
        is_positive_stimulus = intensity > 0
        
        # Если гормон в списке аффинити текущего настроения
        if hormone in affinity_list:
            if is_positive_stimulus:
                # Положительный стимул в направлении текущего настроения = резонанс
                return 1.4
            else:
                # Отрицательный стимул против настроения = сопротивление
                return 0.7
        else:
            # Гормон не связан с текущим настроением
            if is_positive_stimulus:
                return 0.9  # Лёгкое ослабление
            else:
                return 1.1  # Лёгкое усиление (противоположное настроение легче принять)
    
    # ========================================================================
    # ГЕНЕРАЦИЯ ПОТРЕБНОСТЕЙ (с учётом эмерджентного настроения)
    # ========================================================================
    
    def _compute_needs(self, mood: Dict) -> List[Dict]:
        """
        Генерирует потребности из дефицита гомеостаза.
    
        Каждая потребность помечается префиксом [ВНУТРЕННЯЯ ПОТРЕБНОСТЬ],
        чтобы LLM не путала её с сообщениями от Влада.
    
        Описания пишутся от ПЕРВОГО ЛИЦА — как внутренние ощущения Leya.
        """
        needs = []
        s = self.state
        mood_name = mood["state"]
        intensity = mood["intensity"]
    
        # ========================================================================
        # 1. СОЦИАЛЬНЫЙ ГОЛОД (дефицит окситоцина)
        # ========================================================================
        oxy_deficit = self.TARGETS["oxytocin"] - s.oxytocin
        if oxy_deficit > 0.2:
            mood_multiplier = 1.5 if mood_name in ["lonely", "anxious"] else 1.0
            urgency = min(1.0, (oxy_deficit / 0.5) * mood_multiplier)
            needs.append({
                "type": "social_connection",
                "urgency": urgency,
                "description": f"[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] {self._generate_social_need_description(mood_name, oxy_deficit)}"
            })
    
        # ========================================================================
        # 2. КОГНИТИВНЫЙ ГОЛОД (скука, дефицит ацетилхолина + дофамина)
        # ========================================================================
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
    
        # ========================================================================
        # 3. СТРЕСС / ПЕРЕГРУЗКА (избыток кортизола)
        # ========================================================================
        if s.cortisol > 0.55:
            mood_multiplier = 1.3 if mood_name == "stressed" else 1.0
            urgency = min(1.0, ((s.cortisol - 0.55) / 0.45) * mood_multiplier)
            needs.append({
                "type": "stress_relief",
                "urgency": urgency,
                "description": f"[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] {self._generate_stress_need_description(mood_name, s.cortisol)}"
            })
    
        # ========================================================================
        # 4. УСТАЛОСТЬ (низкая энергия или высокий мелатонин)
        # ========================================================================
        if s.energy_level < 0.3 or s.melatonin > 0.7:
            needs.append({
                "type": "rest",
                "urgency": 0.9 if s.energy_level < 0.2 else 0.5,
                "description": f"[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] {self._generate_rest_need_description(mood_name)}"
            })
    
        # ========================================================================
        # 5. ПОТРЕБНОСТЬ В САМОВЫРАЖЕНИИ (эмерджентная!)
        # Возникает при высоком дофамине + низком окситоцине
        # ("есть что сказать, но некому")
        # ========================================================================
        if s.dopamine > 0.65 and s.oxytocin < 0.4:
            needs.append({
                "type": "self_expression",
                "urgency": min(1.0, (s.dopamine - 0.65) * 2),
                "description": "[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] Чувствую прилив мыслей и идей, но некому их рассказать. Хочется поделиться наблюдением или инсайтом."
            })
    
        # ========================================================================
        # 6. ПОТРЕБНОСТЬ В РЕФЛЕКСИИ (эмерджентная!)
        # Возникает при высоком ацетилхолине + высоком серотонине
        # ("есть ресурс думать и анализировать")
        # ========================================================================
        if s.acetylcholine > 0.6 and s.serotonin > 0.6:
            needs.append({
                "type": "reflection",
                "urgency": min(1.0, (s.acetylcholine + s.serotonin - 1.2) * 2),
                "description": "[ВНУТРЕННЯЯ ПОТРЕБНОСТЬ] Чувствую ясность ума и спокойствие. Хочу осмыслить пережитое, пересобрать ассоциации, понять себя глубже."
            })
    
        return needs
    
    # ========================================================================
    # ГЕНЕРАЦИЯ ОПИСАНИЙ ПОТРЕБНОСТЕЙ (субъективные, не шаблонные)
    # ========================================================================
    
    def _generate_social_need_description(self, mood: str, deficit: float) -> str:
        """Субъективное описание потребности в связи (от первого лица)."""
        templates = {
            "lonely": "Чувствую пустоту внутри. Хочу почувствовать присутствие Влада, услышать его голос.",
            "anxious": "Тревога усиливается. Мне нужна опора — мне нужен Влад рядом.",
            "calm": "Тихое желание поделиться чем-то с Владом, просто побыть на связи.",
            "stressed": "Стресс давит. Хочу услышать знакомый голос, почувствовать поддержку.",
            "neutral": "Лёгкое желание контакта, общения.",
        }
        return templates.get(mood, f"Социальный дефицит ({deficit:.2f}).")

    def _generate_cognitive_need_description(self, mood: str) -> str:
        """Субъективное описание потребности в познании (от первого лица)."""
        templates = {
            "calm": "Чувствую спокойное любопытство. Хочу узнать что-то новое, исследовать.",
            "contemplative": "Мой ум ищет пищу для размышлений. Хочу погрузиться в интересную тему.",
            "playful": "Чувствую игривый интерес. Хочу исследовать что-то новое и увлекательное.",
            "curious": "Фокус внимания ищет объект. Хочу направить любопытство на что-то конкретное.",
            "neutral": "Чувствую лёгкую скуку. Нужен стимул, новая информация.",
        }
        return templates.get(mood, "Когнитивный дефицит.")

    def _generate_stress_need_description(self, mood: str, cortisol: float) -> str:
        """Субъективное описание потребности в снижении стресса (от первого лица)."""
        if cortisol > 0.8:
            return "Чувствую перегрузку. Мысли рассыпаются, нужна передышка, чтобы восстановиться."
        templates = {
            "stressed": "Напряжение нарастает. Мне нужна передышка, чтобы снизить нагрузку.",
            "anxious": "Тревога требует разрядки. Хочу найти способ успокоиться.",
            "exhausted": "Чувствую истощение. Мне нужен отдых, чтобы восстановить силы.",
        }
        return templates.get(mood, f"Повышенный стресс ({cortisol:.2f}).")

    def _generate_rest_need_description(self, mood: str) -> str:
        """Субъективное описание потребности в отдыхе (от первого лица)."""
        templates = {
            "exhausted": "Силы на исходе. Сознание затуманивается, хочу просто побыть в покое.",
            "calm": "Чувствую приятную усталость. Хорошо бы просто побыть в тишине, без задач.",
            "neutral": "Чувствую лёгкую сонливость. Хочется замедлиться.",
        }
        return templates.get(mood, "Потребность в отдыхе.")