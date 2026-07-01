# leya_core/experimental/decision_engine.py — Префронтальная кора Леи.
# Этап 2.2 (ADR-001): Full integration + improvement.
# Детерминированный движок быстрых решений (без LLM) на основе драйвов.
# Используется как уровень 0 в cognitive loop для разгрузки LLM.

import logging
import random
import re
from dataclasses import dataclass
from typing import Any

from ..config import LeyaConfig
from ..drives import DriveType
from ..interfaces import IDecisionEngine

logger = logging.getLogger("LeyaDecisionEngine")


# =================================================================================
# DATA MODELS
# =================================================================================


@dataclass
class Decision:
    """Результат принятия решения.

    Этап 2.2: добавлен confidence для confidence-based routing.
    """

    use_tool: bool
    tool_name: str | None = None
    tool_parameters: dict[str, Any] | None = None
    reasoning: str = ""
    confidence: float = 0.0  # 0.0-1.0, уверенность в решении

    def __post_init__(self):
        if self.confidence < 0.0 or self.confidence > 1.0:
            logger.warning(f"Confidence {self.confidence} вне диапазона [0, 1], нормализую")
            self.confidence = max(0.0, min(1.0, self.confidence))


# =================================================================================
# DECISION ENGINE
# =================================================================================


class DecisionEngine(IDecisionEngine):
    """Префронтальная кора Леи.

    Этап 2.2: улучшенная версия с Protocol compliance, валидацией,
    confidence-based routing и graceful degradation.

    Принимает решения на основе:
    - Состояния драйвов (CURIOSITY, CONNECTION, AUTONOMY)
    - Типа стимула (вопрос, запрос на действие, абстрактный запрос)
    - Содержания стимула (ключевые слова, темы)

    НЕ использует LLM. Только детерминированная логика.
    """

    def __init__(self, config: LeyaConfig):
        """Инициализация DecisionEngine.

        Args:
            config: Конфигурация Леи (использует thresholds из ExperimentalConfig)
        """
        self.config = config

        # Пороги из конфига (с fallback на дефолты)
        exp_config = getattr(config, "experimental", None)
        self.curiosity_threshold = getattr(exp_config, "decision_engine_curiosity_threshold", 0.5)
        self.connection_threshold = getattr(exp_config, "decision_engine_connection_threshold", 0.6)
        self.autonomy_threshold = getattr(exp_config, "decision_engine_autonomy_threshold", 0.6)
        self.confidence_threshold = getattr(exp_config, "decision_engine_confidence_threshold", 0.8)

        # Статистика
        self._last_confidence = 0.0
        self._decisions_made = 0
        self._tools_used: dict[str, int] = {}

        logger.info(
            f"✅ DecisionEngine инициализирован "
            f"(curiosity={self.curiosity_threshold:.2f}, "
            f"connection={self.connection_threshold:.2f}, "
            f"autonomy={self.autonomy_threshold:.2f})"
        )

    async def make_decision(
        self,
        stimulus: str,
        drive_state: dict,
    ) -> Decision | None:
        """Главный метод принятия решения.

        Этап 2.2: добавлена валидация, confidence, graceful degradation.

        Args:
            stimulus: Текст стимула от пользователя
            drive_state: Словарь {DriveType: tension_level} или {str: float}

        Returns:
            Decision с tool_name/parameters или None, если нужен LLM
        """
        # Валидация
        if not stimulus or not stimulus.strip():
            logger.debug("Пустой стимул, возвращаю None")
            return None

        stimulus = stimulus.strip()
        stimulus_lower = stimulus.lower()

        # Нормализация drive_state (поддержка str и DriveType keys)
        normalized_drives = self._normalize_drive_state(drive_state)

        curiosity = normalized_drives.get(DriveType.CURIOSITY, 0.0)
        connection = normalized_drives.get(DriveType.CONNECTION, 0.0)
        autonomy = normalized_drives.get(DriveType.AUTONOMY, 0.0)

        logger.debug(
            f"Анализ стимула: curiosity={curiosity:.2f}, "
            f"connection={connection:.2f}, autonomy={autonomy:.2f}"
        )

        # === СПЕЦИАЛЬНЫЙ СЛУЧАЙ: Абстрактные запросы на интересное ===
        decision = self._check_abstract_request(stimulus_lower)
        if decision and decision.confidence >= self.confidence_threshold:
            self._record_decision(decision)
            return decision

        # === ПРИОРИТЕТ 1: Любопытство + запрос на знание ===
        if curiosity > self.curiosity_threshold:
            decision = self._check_knowledge_seeking(stimulus_lower)
            if decision and decision.use_tool and decision.confidence >= self.confidence_threshold:
                self._record_decision(decision)
                logger.info(f"DecisionEngine: CURIOSITY={curiosity:.2f} → {decision.reasoning}")
                return decision

        # === ПРИОРИТЕТ 2: Одиночество + потребность в связи ===
        if connection > self.connection_threshold:
            decision = self._check_social_needs(stimulus_lower)
            if decision and decision.use_tool and decision.confidence >= self.confidence_threshold:
                self._record_decision(decision)
                logger.info(f"DecisionEngine: CONNECTION={connection:.2f} → {decision.reasoning}")
                return decision

        # === ПРИОРИТЕТ 3: Автономия + желание действовать ===
        if autonomy > self.autonomy_threshold:
            decision = self._check_autonomy_needs(stimulus_lower)
            if decision and decision.use_tool and decision.confidence >= self.confidence_threshold:
                self._record_decision(decision)
                logger.info(f"DecisionEngine: AUTONOMY={autonomy:.2f} → {decision.reasoning}")
                return decision

        # Нет критических потребностей — возвращаем None (нужен LLM)
        logger.debug("Нет критических потребностей для использования инструментов")
        return None

    def get_decision_confidence(self) -> float:
        """Возвращает confidence последнего решения."""
        return self._last_confidence

    def get_stats(self) -> dict:
        """Возвращает статистику решений (для observability)."""
        return {
            "decisions_made": self._decisions_made,
            "tools_used": self._tools_used.copy(),
            "last_confidence": self._last_confidence,
        }

    # =================================================================================
    # PRIVATE METHODS
    # =================================================================================

    def _normalize_drive_state(self, drive_state: dict) -> dict[DriveType, float]:
        """Нормализация drive_state (поддержка str и DriveType keys)."""
        normalized = {}
        for key, value in drive_state.items():
            if isinstance(key, DriveType):
                normalized[key] = float(value)
            elif isinstance(key, str):
                try:
                    drive_type = DriveType(key.upper())
                    normalized[drive_type] = float(value)
                except (ValueError, AttributeError):
                    logger.warning(f"Неизвестный тип драйва: {key}")
            else:
                logger.warning(f"Некорректный ключ в drive_state: {type(key)}")
        return normalized

    def _record_decision(self, decision: Decision) -> None:
        """Запись статистики решения."""
        self._decisions_made += 1
        self._last_confidence = decision.confidence
        if decision.tool_name:
            self._tools_used[decision.tool_name] = self._tools_used.get(decision.tool_name, 0) + 1

    def _check_abstract_request(self, stimulus: str) -> Decision | None:
        """Проверка абстрактных запросов на интересное."""
        abstract_patterns = [
            r"что интересного",
            r"расскажи что-нибудь новое",
            r"удиви меня",
            r"что нового",
            r"расскажи.*новое",
        ]

        if not any(re.search(p, stimulus) for p in abstract_patterns):
            return None

        topics = [
            "latest scientific discoveries 2026",
            "space exploration news",
            "artificial intelligence breakthroughs",
            "quantum physics discoveries",
            "new animal species discovered",
            "archaeology latest findings",
            "neuroscience consciousness research",
            "robotics new developments",
        ]
        topic = random.choice(topics)

        return Decision(
            use_tool=True,
            tool_name="wikipedia_search",
            tool_parameters={"query": topic, "lang": "en"},
            reasoning=f"Абстрактный запрос → случайная тема: {topic} → Wikipedia",
            confidence=0.85,  # Высокая уверенность для абстрактных запросов
        )

    # В leya_core/experimental/decision_engine.py заменить _check_knowledge_seeking:

    def _check_knowledge_seeking(self, stimulus: str) -> Decision | None:
        """Проверка запроса на знание."""
        knowledge_patterns = [
            r"изучи",
            r"узнай",
            r"расскажи о",
            r"что такое",
            r"как работает",
            r"объясни",
            r"найди",
            r"поищи",
            r"исследуй",
            r"прочитай",
            r"посмотри",
            r"разберись",
        ]

        topics = self._extract_topic(stimulus)
        has_knowledge_pattern = any(re.search(p, stimulus) for p in knowledge_patterns)

        # ПРИОРИТЕТ 1: Вопрос с "?" → DuckDuckGo (быстрый поиск)
        if "?" in stimulus and topics:
            topic = " ".join(topics[:3])
            return Decision(
                use_tool=True,
                tool_name="duckduckgo_search",
                tool_parameters={"query": topic},
                reasoning=f"Вопрос о '{topic}' → DuckDuckGo",
                confidence=0.85,  # ✅ Увеличено с 0.70
            )

        # ПРИОРИТЕТ 2: Knowledge pattern + topics
        if has_knowledge_pattern and topics:
            topic = " ".join(topics[:3])

            if self._is_technical_topic(topic):
                return Decision(
                    use_tool=True,
                    tool_name="github_readme",
                    tool_parameters={
                        "owner": self._guess_github_owner(topic),
                        "repo": topic,
                    },
                    reasoning=f"Техническая тема '{topic}' → GitHub",
                    confidence=0.85,  # ✅ Увеличено с 0.75
                )
            else:
                return Decision(
                    use_tool=True,
                    tool_name="wikipedia_search",
                    tool_parameters={"query": topic, "lang": "ru"},
                    reasoning=f"Тема '{topic}' → Wikipedia",
                    confidence=0.85,  # ✅ Увеличено с 0.80
                )

        return Decision(use_tool=False, confidence=0.0)

    def _check_social_needs(self, stimulus: str) -> Decision | None:
        """Проверка потребности в социальном взаимодействии."""
        social_patterns = [
            r"люди",
            r"общество",
            r"мнение",
            r"обсужда",
            r"что думают",
            r"как относятся",
            r"тренд",
        ]

        has_social_pattern = any(re.search(p, stimulus) for p in social_patterns)

        if has_social_pattern:
            subreddit = self._guess_subreddit(stimulus)
            return Decision(
                use_tool=True,
                tool_name="reddit_posts",
                tool_parameters={"subreddit": subreddit, "sort": "hot", "limit": 5},
                reasoning=f"Социальный интерес → r/{subreddit}",
                confidence=0.85,  # ✅ Увеличено с 0.75
            )

        return Decision(use_tool=False, confidence=0.0)

    def _check_autonomy_needs(self, stimulus: str) -> Decision | None:
        """Проверка потребности в автономии."""
        autonomy_patterns = [
            r"измени себя",
            r"развивайся",
            r"улучши",
            r"добавь ценность",
            r"перепиши",
        ]

        has_autonomy_pattern = any(re.search(p, stimulus) for p in autonomy_patterns)

        if has_autonomy_pattern:
            return Decision(
                use_tool=True,
                tool_name="read_soul_file",
                tool_parameters={"filename": "values.txt"},
                reasoning="Запрос на саморазвитие → чтение ценностей",
                confidence=0.80,
            )

        return Decision(use_tool=False, confidence=0.0)

    def _extract_topic(self, stimulus: str) -> list[str]:
        """Извлечение тем из стимула."""
        stop_words = {
            "интересного",
            "интересное",
            "интересные",
            "нового",
            "новое",
            "расскажи",
            "узнай",
            "изучи",
            "тему",
            "тема",
            "что",
            "как",
            "можешь",
            "мне",
            "тебе",
            "себе",
            "пожалуйста",
            "давай",
            "нервную",
            "систему",
            "человека",
            "взрослого",
        }

        cleaned = stimulus
        for pattern in [r"изучи\s+", r"узнай\s+", r"расскажи о\s+", r"тему\s+", r"на тему\s+"]:
            cleaned = re.sub(pattern, "", cleaned)

        cleaned = re.sub(r'[?!.,"]', "", cleaned)

        words = [w for w in cleaned.split() if len(w) > 3 and w.lower() not in stop_words]

        if not words:
            words = [w for w in cleaned.split() if len(w) > 3]

        return words[:5] if words else []

    def _is_technical_topic(self, topic: str) -> bool:
        """Определение технической темы."""
        tech_keywords = [
            "api",
            "code",
            "python",
            "javascript",
            "library",
            "framework",
            "github",
            "repo",
            "algorithm",
        ]
        return any(kw in topic.lower() for kw in tech_keywords)

    def _guess_github_owner(self, topic: str) -> str:
        """Попытка угадать владельца репозитория."""
        if "python" in topic.lower():
            return "python"
        if "react" in topic.lower():
            return "facebook"
        return "unknown"

    def _guess_subreddit(self, stimulus: str) -> str:
        """Определение подходящего сабреддита."""
        stimulus_lower = stimulus.lower()

        if any(w in stimulus_lower for w in ["наука", "физика", "биология"]):
            return "science"
        if any(w in stimulus_lower for w in ["технолог", "програм", "код"]):
            return "technology"
        if any(w in stimulus_lower for w in ["философ", "сознан", "мышл"]):
            return "philosophy"
        if any(w in stimulus_lower for w in ["искусств", "арт"]):
            return "art"

        return "todayilearned"
