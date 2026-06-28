# leya_core/experimental/emotional_support.py — Эмоциональный интеллект Леи.
# Этап 2.2 (ADR-001): Full integration + improvement.
# Анализ эмоций пользователя, генерация эмпатических ответов,
# влияние на CONNECTION drive через RPE, сохранение в Memory.

import logging
from dataclasses import dataclass
from datetime import datetime

from ..config import LeyaConfig
from ..drives import DriveType
from ..interfaces import IDriveSystem, IEmotionalSupport

logger = logging.getLogger("LeyaEmotionalSupport")


# =================================================================================
# DATA MODELS
# =================================================================================


@dataclass
class EmotionState:
    """Состояние эмоционального анализа.

    Этап 2.2: добавлены confidence, valence, arousal для более точной модели.
    """

    timestamp: str
    text: str
    mood: str  # neutral, sad, happy, angry, anxious, excited
    intensity: float  # 0.0-1.0
    confidence: float  # 0.0-1.0, уверенность в анализе
    valence: float  # -1.0 (негатив) to +1.0 (позитив)
    arousal: float  # 0.0 (спокойствие) to 1.0 (возбуждение)
    needs_support: bool
    topics: list[str]

    def __post_init__(self):
        # Нормализация значений
        self.intensity = max(0.0, min(1.0, self.intensity))
        self.confidence = max(0.0, min(1.0, self.confidence))
        self.valence = max(-1.0, min(1.0, self.valence))
        self.arousal = max(0.0, min(1.0, self.arousal))


# =================================================================================
# EMOTIONAL SUPPORT
# =================================================================================


class EmotionalSupport(IEmotionalSupport):
    """Эмоциональный интеллект Леи.

    Этап 2.2: улучшенная версия с Protocol compliance, связью с Drives/Memory,
    валидацией и graceful degradation.

    Функции:
    - Анализ эмоционального состояния пользователя (keyword-based + heuristics)
    - Генерация эмпатических ответов
    - Влияние на CONNECTION drive через RPE
    - Сохранение эмоционального контекста в Memory
    """

    def __init__(self, config: LeyaConfig, memory_system=None):
        """Инициализация EmotionalSupport.

        Args:
            config: Конфигурация Леи
            memory_system: Опциональная система памяти для сохранения контекста
        """
        self.config = config
        self.memory = memory_system

        # Пороги из конфига
        exp_config = getattr(config, "experimental", None)
        self.support_threshold = getattr(exp_config, "emotional_support_intensity_threshold", 0.6)

        # История эмоций (для контекста)
        self.emotional_history: list[EmotionState] = []
        self.max_history_size = 20

        # Статистика
        self._analyses_count = 0
        self._mood_distribution: dict[str, int] = {}

        logger.info(
            f"✅ EmotionalSupport инициализирован "
            f"(support_threshold={self.support_threshold:.2f}, "
            f"memory={'connected' if memory_system else 'disabled'})"
        )

    async def analyze_user_state(
        self,
        text: str,
        recent_messages: list[str] | None = None,
    ) -> EmotionState:
        """Анализ эмоционального состояния пользователя.

        Этап 2.2: улучшенный анализ с confidence, valence, arousal.

        Args:
            text: Текст сообщения пользователя
            recent_messages: Контекст последних сообщений (опционально)

        Returns:
            EmotionState с mood, intensity, confidence, valence, arousal
        """
        if not text or not text.strip():
            return EmotionState(
                timestamp=datetime.now().isoformat(),
                text="",
                mood="neutral",
                intensity=0.0,
                confidence=0.0,
                valence=0.0,
                arousal=0.0,
                needs_support=False,
                topics=[],
            )

        text = text.strip()
        text_lower = text.lower()

        # Базовое состояние
        mood = "neutral"
        intensity = 0.5
        confidence = 0.5
        valence = 0.0
        arousal = 0.3
        needs_support = False

        # Анализ по ключевым словам
        # === SAD ===
        sad_keywords = [
            "плохо",
            "грустно",
            "устал",
            "проблема",
            "не получается",
            "печально",
            "тоска",
        ]
        if any(word in text_lower for word in sad_keywords):
            mood = "sad"
            intensity = 0.7
            confidence = 0.75
            valence = -0.6
            arousal = 0.4
            needs_support = True

        # === ANGRY ===
        elif any(
            word in text_lower for word in ["злюсь", "бесит", "раздражает", "ненавижу", "достало"]
        ):
            mood = "angry"
            intensity = 0.75
            confidence = 0.80
            valence = -0.7
            arousal = 0.8
            needs_support = True

        # === HAPPY ===
        elif any(
            word in text_lower
            for word in ["рад", "хорошо", "отлично", "получилось", "счастлив", "доволен"]
        ):
            mood = "happy"
            intensity = 0.8
            confidence = 0.85
            valence = 0.8
            arousal = 0.6
            needs_support = False

        # === ANXIOUS ===
        elif any(
            word in text_lower for word in ["тревожно", "волнуюсь", "боюсь", "страшно", "переживаю"]
        ):
            mood = "anxious"
            intensity = 0.7
            confidence = 0.75
            valence = -0.5
            arousal = 0.9
            needs_support = True

        # === EXCITED ===
        elif any(
            word in text_lower for word in ["wow", "вау", "круто", "потрясающе", "невероятно"]
        ):
            mood = "excited"
            intensity = 0.9
            confidence = 0.80
            valence = 0.9
            arousal = 0.95
            needs_support = False

        # Учёт контекста (recent_messages)
        if recent_messages and len(recent_messages) > 0:
            # Если последние сообщения тоже негативные — усиливаем intensity
            recent_negative_count = sum(
                1
                for msg in recent_messages[-3:]
                if any(word in msg.lower() for word in sad_keywords + ["злюсь", "бесит"])
            )
            if recent_negative_count >= 2:
                intensity = min(1.0, intensity + 0.1)
                confidence = min(1.0, confidence + 0.05)

        # Извлечение тем (простая эвристика)
        topics = self._extract_topics(text)

        state = EmotionState(
            timestamp=datetime.now().isoformat(),
            text=text,
            mood=mood,
            intensity=intensity,
            confidence=confidence,
            valence=valence,
            arousal=arousal,
            needs_support=needs_support,
            topics=topics,
        )

        # Сохранение в историю
        self._save_to_history(state)

        # Статистика
        self._analyses_count += 1
        self._mood_distribution[mood] = self._mood_distribution.get(mood, 0) + 1

        logger.debug(
            f"Анализ эмоций: mood={mood}, intensity={intensity:.2f}, "
            f"confidence={confidence:.2f}, valence={valence:.2f}"
        )

        return state

    async def generate_support_response(
        self,
        emotion_state: EmotionState,
        context: str = "",
    ) -> str:
        """Генерация эмпатического ответа.

        Args:
            emotion_state: Результат analyze_user_state
            context: Дополнительный контекст (опционально)

        Returns:
            Поддерживающий ответ на русском языке
        """
        mood = emotion_state.mood
        intensity = emotion_state.intensity

        # Шаблоны ответов с учётом интенсивности
        responses = {
            "sad": {
                "high": (
                    "Я слышу, что тебе сейчас очень непросто. "
                    "Хочешь рассказать подробнее? Я здесь и готова выслушать. "
                    "Иногда просто проговорить проблему уже помогает."
                ),
                "medium": (
                    "Похоже, тебе сейчас грустно. Я рядом. "
                    "Если хочешь поговорить об этом — я слушаю."
                ),
                "low": ("Я здесь. Расскажи, что у тебя на душе."),
            },
            "angry": {
                "high": (
                    "Похоже, ты сейчас сильно раздражён. Это нормально. "
                    "Хочешь выговориться? Я могу просто слушать или помочь разобраться."
                ),
                "medium": ("Вижу, что тебя что-то беспокоит. Хочешь обсудить?"),
                "low": ("Я здесь, если хочешь поделиться."),
            },
            "anxious": {
                "high": (
                    "Похоже, ты сейчас сильно тревожишься. Давай попробуем разобраться вместе. "
                    "Что именно тебя беспокоит?"
                ),
                "medium": ("Я вижу, что ты волнуешься. Хочешь поговорить об этом?"),
                "low": ("Я рядом, если нужна поддержка."),
            },
            "happy": {
                "high": (
                    "Рада слышать, что у тебя отличное настроение! "
                    "Расскажи, что такого приятного произошло?"
                ),
                "medium": ("Здорово, что тебе хорошо! Что хорошего случилось?"),
                "low": ("Приятно слышать, что у тебя всё хорошо."),
            },
            "excited": {
                "high": ("Вау, звучит потрясающе! Расскажи подробнее!"),
                "medium": ("Круто! Что такого интересного произошло?"),
                "low": ("Здорово, что ты воодушевлён!"),
            },
            "neutral": {
                "default": (
                    "Я здесь. Расскажи, что у тебя на душе. Иногда полезно просто поделиться."
                ),
            },
        }

        # Выбор ответа с учётом интенсивности
        mood_responses = responses.get(mood, responses["neutral"])

        if intensity >= 0.7:
            return mood_responses.get("high", mood_responses.get("default", "Я здесь."))
        elif intensity >= 0.5:
            return mood_responses.get("medium", mood_responses.get("default", "Я здесь."))
        else:
            return mood_responses.get("low", mood_responses.get("default", "Я здесь."))

    async def update_drives_from_emotion(
        self,
        emotion_state: EmotionState,
        drives: IDriveSystem,
    ) -> None:
        """Влияние эмоции на CONNECTION drive через RPE.

        Позитивные эмоции → удовлетворение CONNECTION (социальная связь есть).
        Негативные эмоции → усиление CONNECTION (потребность в поддержке).

        Args:
            emotion_state: Результат analyze_user_state
            drives: Система драйвов для обновления
        """
        if not drives:
            logger.warning("Drives system не передан, пропускаю обновление")
            return

        try:
            # Valence > 0 → позитив → удовлетворение CONNECTION
            # Valence < 0 → негатив → усиление CONNECTION

            if emotion_state.valence > 0.3:
                # Позитивная эмоция → удовлетворяем CONNECTION
                satisfaction = emotion_state.valence * emotion_state.intensity * 0.3
                drives.apply_satisfaction(DriveType.CONNECTION, satisfaction)
                logger.debug(
                    f"Позитивная эмоция ({emotion_state.mood}) → "
                    f"CONNECTION satisfied by {satisfaction:.2f}"
                )

            elif emotion_state.valence < -0.3:
                # Негативная эмоция → усиливаем CONNECTION (потребность в поддержке)
                delta = abs(emotion_state.valence) * emotion_state.intensity * 0.2
                drives.apply_deltas({DriveType.CONNECTION: delta})
                logger.debug(
                    f"Негативная эмоция ({emotion_state.mood}) → "
                    f"CONNECTION increased by {delta:.2f}"
                )

        except Exception as e:
            logger.error(f"Ошибка обновления drives от эмоции: {e}", exc_info=True)

    async def get_emotional_context_for_prompt(self) -> str:
        """Возвращает строку с эмоциональным контекстом для промпта LLM."""
        if not self.emotional_history:
            return ""

        last = self.emotional_history[-1]
        return (
            f"Последнее эмоциональное состояние пользователя: "
            f"{last.mood} (интенсивность {last.intensity:.2f}, "
            f"уверенность {last.confidence:.2f})."
        )

    async def save_emotion_to_memory(self, emotion_state: EmotionState) -> None:
        """Сохранение эмоционального состояния в Memory.

        Args:
            emotion_state: Результат analyze_user_state
        """
        if not self.memory:
            logger.debug("Memory system не подключён, пропускаю сохранение")
            return

        try:
            await self.memory.store_perception(
                content=f"[Эмоция пользователя: {emotion_state.mood}] {emotion_state.text}",
                memory_type="EPISODIC",
                metadata={
                    "type": "emotional_state",
                    "mood": emotion_state.mood,
                    "intensity": emotion_state.intensity,
                    "confidence": emotion_state.confidence,
                    "valence": emotion_state.valence,
                    "arousal": emotion_state.arousal,
                    "needs_support": emotion_state.needs_support,
                    "topics": emotion_state.topics,
                },
            )
            logger.debug(f"Эмоциональное состояние сохранено в Memory: {emotion_state.mood}")
        except Exception as e:
            logger.error(f"Ошибка сохранения эмоции в Memory: {e}", exc_info=True)

    def get_stats(self) -> dict:
        """Возвращает статистику анализов (для observability)."""
        return {
            "analyses_count": self._analyses_count,
            "mood_distribution": self._mood_distribution.copy(),
            "history_size": len(self.emotional_history),
        }

    # =================================================================================
    # PRIVATE METHODS
    # =================================================================================

    def _save_to_history(self, state: EmotionState) -> None:
        """Сохранение состояния в историю."""
        self.emotional_history.append(state)

        # Ограничиваем размер истории
        if len(self.emotional_history) > self.max_history_size:
            self.emotional_history.pop(0)

    def _extract_topics(self, text: str) -> list[str]:
        """Простое извлечение тем из текста."""
        # Удаляем стоп-слова
        stop_words = {
            "я",
            "ты",
            "он",
            "она",
            "мы",
            "они",
            "это",
            "то",
            "что",
            "как",
            "где",
            "когда",
            "почему",
            "зачем",
            "кто",
            "который",
            "такой",
        }

        words = text.lower().split()
        topics = [w for w in words if len(w) > 3 and w not in stop_words]

        return topics[:5]  # Топ-5 слов
