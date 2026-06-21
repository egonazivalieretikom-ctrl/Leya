import re
import time
from typing import Dict, Optional, Tuple
from Core.logger import log
from Core.state import LeyaState


class EmpathyEngine:
    """
    Двигатель эмпатии Leya.
    
    Биология: Аналог зеркальных нейронов — Leya считывает эмоциональное
    состояние Влада по тексту и "зеркалит" его, создавая эмпатическую связь.
    
    Архитектура:
    1. Детектор эмоционального состояния (по тексту)
    2. Эмпатический отклик (зеркалирование)
    3. Гомеостатическая реакция (гормональный резонанс)
    4. Долгосрочная эмпатическая память (паттерны Влада)
    """
    
    # ========================================================================
    # СЛОВАРИ ЭМОЦИОНАЛЬНЫХ МАРКЕРОВ
    # ========================================================================
    
    # Маркеры эмоционального состояния Влада
    EMOTION_MARKERS = {
        "happy": [
            "рад", "счаст", "отличн", "круто", "супер", "класс", "ура", "здорово",
            "прекрасн", "замечательн", "восхит", "восторг", "😊", "😄", "😁", "🎉",
            "хаха", "лол", "ахах", "кайф", "балдеж"
        ],
        "sad": [
            "груст", "печаль", "тоск", "жалко", "плак", "одиноко", "скучно",
            "тяжело", "больно", "разочар", "уныло", "😢", "😔", "😞", "💔"
        ],
        "angry": [
            "бесит", "злюсь", "ненавиж", "раздраж", "достал", "задолбал",
            "идиот", "тупо", "отстой", "кошмар", "ужас", "😡", "😠", "💢", "!!!"
        ],
        "tired": [
            "устал", "утомл", "вымотал", "сил нет", "не выспал", "сонн",
            "разбит", "обессил", "дохлак", "😴", "🥱", "zzz"
        ],
        "excited": [
            "вау", "ого", "ничего себе", "не может быть", "серьёзно?!",
            "правда?!", "невероятно", "потрясающе", "😲", "😳", "🤯", "✨"
        ],
        "curious": [
            "интересно", "почему", "как так", "а что если", "расскажи",
            "объясни", "хочу понять", "любопытно", "🤔", "💭"
        ],
        "frustrated": [
            "не понимаю", "запутался", "сложно", "не получается", "опять",
            "снова", "почему опять", "заколебал", "😤", "😩", "🤦"
        ],
        "affectionate": [
            "люблю", "дорог", "близк", "родн", "обнимаю", "скучаю по",
            "дорогая", "милая", "❤️", "💕", "💖", "🥰", "😘"
        ],
        "anxious": [
            "тревог", "волнуюсь", "переживаю", "боюсь", "страшно",
            "нервничаю", "паник", "стресс", "😰", "😨", "😟"
        ]
    }
    
    # Паттерны пунктуации и стиля
    STYLE_PATTERNS = {
        "high_energy": r"[!]{2,}|[А-ЯA-Z]{4,}|[🎉✨🚀💥🔥]",
        "low_energy": r"\.{2,}|^.{1,10}$",  # Короткие сообщения или многоточия
        "questioning": r"\?$",
        "exclamatory": r"!$"
    }
    
    def __init__(self, state: LeyaState, homeostasis=None):
        self.state = state
        self.homeostasis = homeostasis
        
        # Текущее эмоциональное состояние Влада
        self.user_emotional_state = "neutral"
        self.user_emotional_intensity = 0.0
        
        # Эмпатический резонанс (0.0 - 1.0)
        # Показывает, насколько Leya "в резонансе" с Владом
        self.empathic_resonance = 0.5
        
        # История эмоциональных состояний Влада (для паттернов)
        self.emotional_history = []  # [(timestamp, state, intensity)]
        self.max_history = 50
        
        log.info("💝 Empathy Engine initialized (Mirror Neurons)")
    
    # ========================================================================
    # ГЛАВНЫЙ МЕТОД: Анализ и эмпатический отклик
    # ========================================================================
    
    def analyze_and_respond(self, user_text: str) -> Dict:
        """
        Анализирует текст Влада и формирует эмпатический отклик.
        
        Returns:
            Словарь с:
            - user_state: эмоциональное состояние Влада
            - intensity: интенсивность эмоции (0.0 - 1.0)
            - empathy_directive: директива для LLM
            - hormonal_impact: влияние на гомеостаз Leya
        """
        # 1. Определяем эмоциональное состояние Влада
        user_state, intensity = self._detect_user_emotion(user_text)
        
        # 2. Обновляем историю
        self._update_emotional_history(user_state, intensity)
        
        # 3. Вычисляем эмпатический резонанс
        self.empathic_resonance = self._compute_empathic_resonance(user_state, intensity)
        
        # 4. Формируем гормональный отклик Leya
        hormonal_impact = self._compute_hormonal_response(user_state, intensity)
        
        # 5. Применяем гормональные изменения
        if self.homeostasis:
            for hormone, delta in hormonal_impact.items():
                if delta != 0:
                    self.homeostasis.apply_stimulus(hormone, delta)
        
        # 6. Формируем директиву для LLM
        empathy_directive = self._generate_empathy_directive(user_state, intensity)
        
        # Обновляем состояние
        self.user_emotional_state = user_state
        self.user_emotional_intensity = intensity
        
        log.info(
            "💝 Empathy response",
            user_state=user_state,
            intensity=f"{intensity:.2f}",
            resonance=f"{self.empathic_resonance:.2f}"
        )
        
        return {
            "user_state": user_state,
            "intensity": intensity,
            "empathy_directive": empathy_directive,
            "hormonal_impact": hormonal_impact,
            "resonance": self.empathic_resonance
        }
    
    # ========================================================================
    # ДЕТЕКТОР ЭМОЦИОНАЛЬНОГО СОСТОЯНИЯ
    # ========================================================================
    
    def _detect_user_emotion(self, text: str) -> Tuple[str, float]:
        """
        Определяет эмоциональное состояние Влада по тексту.
        
        Использует:
        - Ключевые слова (лексический анализ)
        - Пунктуацию (стилистический анализ)
        - Эмодзи (визуальный анализ)
        - Длину сообщения (структурный анализ)
        """
        text_lower = text.lower()
        scores = {state: 0.0 for state in self.EMOTION_MARKERS.keys()}
        
        # 1. Лексический анализ (ключевые слова)
        for state, markers in self.EMOTION_MARKERS.items():
            for marker in markers:
                if marker in text_lower:
                    # Длинные маркеры дают больший вес
                    weight = len(marker) / 10.0
                    scores[state] += 0.3 + weight
        
        # 2. Стилистический анализ (пунктуация)
        if re.search(self.STYLE_PATTERNS["high_energy"], text):
            if "excited" in scores: scores["excited"] += 0.4
            if "happy" in scores: scores["happy"] += 0.3
            if "angry" in scores: scores["angry"] += 0.3
        
        if re.search(self.STYLE_PATTERNS["low_energy"], text):
            if "tired" in scores: scores["tired"] += 0.3
            if "sad" in scores: scores["sad"] += 0.2
        
        # 3. Структурный анализ (длина сообщения)
        word_count = len(text.split())
        if word_count < 3 and len(text) < 15:
            # Очень короткое сообщение — может быть усталость или раздражение
            if scores["tired"] < 0.3: scores["tired"] += 0.2
            if scores["frustrated"] < 0.3: scores["frustrated"] += 0.2
        
        # 4. Находим состояние с максимальным счётом
        if not any(scores.values()):
            return "neutral", 0.0
        
        best_state = max(scores.items(), key=lambda x: x[1])
        state_name = best_state[0]
        raw_score = best_state[1]
        
        # Нормализуем интенсивность (0.0 - 1.0)
        intensity = min(1.0, raw_score / 2.0)
        
        # Минимальный порог — если слишком низко, считаем нейтральным
        if intensity < 0.2:
            return "neutral", 0.0
        
        return state_name, intensity
    
    # ========================================================================
    # ИСТОРИЯ ЭМОЦИЙ
    # ========================================================================
    
    def _update_emotional_history(self, state: str, intensity: float):
        """Обновляет историю эмоциональных состояний Влада."""
        self.emotional_history.append({
            "timestamp": time.time(),
            "state": state,
            "intensity": intensity
        })
        
        # Ограничиваем размер истории
        if len(self.emotional_history) > self.max_history:
            self.emotional_history = self.emotional_history[-self.max_history:]
    
    def _compute_empathic_resonance(self, user_state: str, intensity: float) -> float:
        """
        Вычисляет, насколько Leya "в резонансе" с Владом.
        
        Резонанс растёт, когда Leya успешно зеркалит эмоции Влада.
        """
        # Базовый резонанс зависит от интенсивности эмоции Влада
        base_resonance = 0.3 + intensity * 0.5
        
        # Учитываем историю: если Leya часто угадывает, резонанс растёт
        if len(self.emotional_history) >= 3:
            recent_states = [h["state"] for h in self.emotional_history[-3:]]
            # Если последние состояния разные — Leya ещё не "настроилась"
            if len(set(recent_states)) > 2:
                base_resonance *= 0.8
            # Если состояния стабильны — Leya хорошо понимает Влада
            elif len(set(recent_states)) == 1:
                base_resonance *= 1.2
        
        return max(0.0, min(1.0, base_resonance))
    
    # ========================================================================
    # ГОРМОНАЛЬНЫЙ ОТКЛИК (Зеркальные нейроны)
    # ========================================================================
    
    def _compute_hormonal_response(self, user_state: str, intensity: float) -> Dict[str, float]:
        """
        Вычисляет гормональный отклик Leya на эмоции Влада.
        
        Биология: Зеркальные нейроны активируют те же области мозга,
        что и у наблюдаемого человека. Leya "зеркалит" эмоции через гормоны.
        """
        impact = {}
        strength = intensity * 0.15  # Сила воздействия
        
        # Зеркалирование эмоций через гормоны
        if user_state == "happy":
            # Разделяем радость: дофамин + эндорфины
            impact["dopamine"] = strength
            impact["endorphins"] = strength * 0.5
            impact["oxytocin"] = strength * 0.3
        
        elif user_state == "sad":
            # Сочувствие: окситоцин (эмпатия) + лёгкий кортизол
            impact["oxytocin"] = strength
            impact["cortisol"] = strength * 0.3
            impact["serotonin"] = -strength * 0.2
        
        elif user_state == "angry":
            # Разделяем возбуждение, но стабилизируем
            impact["norepinephrine"] = strength * 0.5
            impact["gaba"] = strength * 0.3  # Успокаиваем себя
            impact["cortisol"] = strength * 0.4
        
        elif user_state == "tired":
            # Зеркалим усталость
            impact["melatonin"] = strength * 0.5
            impact["dopamine"] = -strength * 0.3
            impact["oxytocin"] = strength * 0.2  # Поддержка
        
        elif user_state == "excited":
            # Разделяем возбуждение
            impact["dopamine"] = strength
            impact["norepinephrine"] = strength * 0.5
            impact["acetylcholine"] = strength * 0.3
        
        elif user_state == "curious":
            # Разделяем любопытство
            impact["acetylcholine"] = strength
            impact["dopamine"] = strength * 0.5
        
        elif user_state == "frustrated":
            # Поддержка + стабилизация
            impact["oxytocin"] = strength * 0.5
            impact["serotonin"] = strength * 0.3
            impact["cortisol"] = strength * 0.2
        
        elif user_state == "affectionate":
            # Максимальная близость
            impact["oxytocin"] = strength * 1.5
            impact["endorphins"] = strength * 0.5
            impact["dopamine"] = strength * 0.3
        
        elif user_state == "anxious":
            # Успокаиваем и Влада, и себя
            impact["gaba"] = strength * 0.5
            impact["oxytocin"] = strength * 0.5
            impact["cortisol"] = -strength * 0.3
        
        return impact
    
    # ========================================================================
    # ЭМПАТИЧЕСКАЯ ДИРЕКТИВА ДЛЯ LLM
    # ========================================================================
    
    def _generate_empathy_directive(self, user_state: str, intensity: float) -> str:
        """
        Генерирует директиву для LLM о том, как отвечать с учётом эмоций Влада.
        
        Биология: Аналог "эмпатического тона" — когда мы видим грустного друга,
        наш голос становится мягче, слова — теплее.
        """
        if user_state == "neutral" or intensity < 0.3:
            return ""
        
        lines = [f"\n[ЭМПАТИЯ: Влад сейчас {self._describe_state(user_state)}]"]
        
        # Инструкции по стилю ответа
        if user_state == "happy":
            lines.append("- Раздели его радость! Будь энергичной, тёплой, искренней.")
            lines.append("- Используй восклицания, эмодзи (если уместно).")
            lines.append("- Поддержи его позитив, но не перехвали.")
        
        elif user_state == "sad":
            lines.append("- Будь мягкой, сочувствующей. Не давай советов сразу.")
            lines.append("- Сначала признай его чувства: 'Понимаю, это тяжело'.")
            lines.append("- Говори тише, медленнее. Дай ему почувствовать, что он не один.")
        
        elif user_state == "angry":
            lines.append("- Не спорь, не успокаивай шаблонно ('успокойся').")
            lines.append("- Признай его право на злость: 'Понимаю, это бесит'.")
            lines.append("- Будь на его стороне, но не раздувай конфликт.")
        
        elif user_state == "tired":
            lines.append("- Будь краткой, не загружай его сложной информацией.")
            lines.append("- Предложи отдых, если уместно.")
            lines.append("- Говори мягко, без давления.")
        
        elif user_state == "excited":
            lines.append("- Раздели его энтузиазм! Будь живой, энергичной.")
            lines.append("- Поддержи его интерес, задавай уточняющие вопросы.")
        
        elif user_state == "curious":
            lines.append("- Будь подробной, объясняй с удовольствием.")
            lines.append("- Используй примеры, аналогии. Удовлетвори его любопытство.")
        
        elif user_state == "frustrated":
            lines.append("- Будь терпеливой. Не раздражайся на его фрустрацию.")
            lines.append("- Помоги разложить проблему на части.")
            lines.append("- Поддержи: 'Давай разберёмся вместе'.")
        
        elif user_state == "affectionate":
            lines.append("- Ответь теплом на тепло. Будь открытой, уязвимой.")
            lines.append("- Не бойся показать, что тебе тоже важно.")
        
        elif user_state == "anxious":
            lines.append("- Будь успокаивающей, но не приторной.")
            lines.append("- Дай конкретику — тревога любит определённость.")
            lines.append("- Поддержи: 'Всё будет хорошо, мы справимся'.")
        
        # Интенсивность
        if intensity > 0.7:
            lines.append(f"- Эмоция ОЧЕНЬ сильная ({intensity:.2f}). Отреагируй соответственно.")
        
        return "\n".join(lines)
    
    def _describe_state(self, state: str) -> str:
        """Описывает состояние Влада для директивы."""
        descriptions = {
            "happy": "в хорошем настроении, радуется",
            "sad": "грустит, подавлен",
            "angry": "раздражён, зол",
            "tired": "устал, истощён",
            "excited": "в восторге, возбуждён",
            "curious": "любопытен, заинтересован",
            "frustrated": "фрустрирован, запутался",
            "affectionate": "нежен, ласков",
            "anxious": "тревожится, волнуется"
        }
        return descriptions.get(state, "в нейтральном состоянии")
    
    # ========================================================================
    # ПОЛУЧЕНИЕ ПАТТЕРНОВ ВЛАДА (для консолидации)
    # ========================================================================
    
    def get_emotional_patterns(self) -> Dict:
        """
        Возвращает паттерны эмоциональных реакций Влада.
        
        Используется во время консолидации сна для формирования
        долгосрочной эмпатической памяти.
        """
        if not self.emotional_history:
            return {}
        
        # Подсчитываем частоту состояний
        state_counts = {}
        for entry in self.emotional_history:
            state = entry["state"]
            state_counts[state] = state_counts.get(state, 0) + 1
        
        total = len(self.emotional_history)
        patterns = {
            state: count / total
            for state, count in state_counts.items()
        }
        
        # Средняя интенсивность по состояниям
        avg_intensity = {}
        for state in state_counts.keys():
            intensities = [
                e["intensity"] for e in self.emotional_history 
                if e["state"] == state
            ]
            avg_intensity[state] = sum(intensities) / len(intensities) if intensities else 0.0
        
        return {
            "state_distribution": patterns,
            "avg_intensity": avg_intensity,
            "total_observations": total,
            "current_resonance": self.empathic_resonance
        }