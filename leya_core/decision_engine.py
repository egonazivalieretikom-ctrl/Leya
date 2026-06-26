"""
leya_core/decision_engine.py — Префронтальная кора Леи.
Принимает решения на основе состояния драйвов и контекста.
НЕ использует LLM — только детерминированная логика.
"""

import logging
import random
import re
from dataclasses import dataclass
from typing import Any

from leya_core.drives import DriveType

logger = logging.getLogger("DecisionEngine")


@dataclass
class Decision:
    """Результат принятия решения"""

    use_tool: bool
    tool_name: str | None = None
    tool_parameters: dict[str, Any] | None = None
    reasoning: str = ""


class DecisionEngine:
    """
    Префронтальная кора. Принимает решения на основе:
    - Состояния драйвов
    - Типа стимула
    - Содержания стимула

    НЕ использует LLM. Только логика.
    """

    def __init__(self):
        # Пороги для принятия решений
        self.CURIOSITY_THRESHOLD = 0.5
        self.CONNECTION_THRESHOLD = 0.6
        self.AUTONOMY_THRESHOLD = 0.6

    def make_decision(self, stimulus: str, drive_state: dict[DriveType, float]) -> Decision:
        """Главный метод принятия решения."""
        curiosity = drive_state.get(DriveType.CURIOSITY, 0.0)
        connection = drive_state.get(DriveType.CONNECTION, 0.0)
        autonomy = drive_state.get(DriveType.AUTONOMY, 0.0)

        stimulus_lower = stimulus.lower()

        # === СПЕЦИАЛЬНЫЙ СЛУЧАЙ: Абстрактные запросы на интересное ===
        abstract_patterns = [
            r"что интересного",
            r"расскажи что-нибудь новое",
            r"удиви меня",
            r"что нового",
            r"расскажи.*новое",
        ]

        if any(re.search(p, stimulus_lower) for p in abstract_patterns):
            # Используем АНГЛИЙСКИЕ запросы для DuckDuckGo
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

            # Сначала пробуем Wikipedia (надёжнее для научных тем)
            return Decision(
                use_tool=True,
                tool_name="wikipedia_search",
                tool_parameters={"query": topic, "lang": "en"},
                reasoning=f"Абстрактный запрос → случайная тема: {topic} → Wikipedia",
            )

        # === ПРИОРИТЕТ 1: Любопытство + запрос на знание ===
        if curiosity > self.CURIOSITY_THRESHOLD:
            decision = self._check_knowledge_seeking(stimulus_lower)
            if decision.use_tool:
                logger.info(f"DecisionEngine: CURIOSITY={curiosity:.2f} → {decision.reasoning}")
                return decision

        # === ПРИОРИТЕТ 2: Одиночество + потребность в связи ===
        if connection > self.CONNECTION_THRESHOLD:
            decision = self._check_social_needs(stimulus_lower)
            if decision.use_tool:
                logger.info(f"DecisionEngine: CONNECTION={connection:.2f} → {decision.reasoning}")
                return decision

        # === ПРИОРИТЕТ 3: Автономия + желание действовать ===
        if autonomy > self.AUTONOMY_THRESHOLD:
            decision = self._check_autonomy_needs(stimulus_lower)
            if decision.use_tool:
                logger.info(f"DecisionEngine: AUTONOMY={autonomy:.2f} → {decision.reasoning}")
                return decision

        return Decision(
            use_tool=False, reasoning="Нет критических потребностей для использования инструментов"
        )

    def _check_knowledge_seeking(self, stimulus: str) -> Decision:
        """Проверяет, есть ли в стимуле запрос на знание"""

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

        if has_knowledge_pattern and topics:
            topic = " ".join(topics[:3])

            if self._is_technical_topic(topic):
                return Decision(
                    use_tool=True,
                    tool_name="github_readme",
                    tool_parameters={"owner": self._guess_github_owner(topic), "repo": topic},
                    reasoning=f"Техническая тема '{topic}' → GitHub",
                )
            else:
                return Decision(
                    use_tool=True,
                    tool_name="wikipedia_search",
                    tool_parameters={"query": topic, "lang": "ru"},
                    reasoning=f"Тема '{topic}' → Wikipedia",
                )

        if "?" in stimulus and topics:
            topic = " ".join(topics[:3])
            return Decision(
                use_tool=True,
                tool_name="duckduckgo_search",
                tool_parameters={"query": topic},
                reasoning=f"Вопрос о '{topic}' → DuckDuckGo",
            )

        return Decision(use_tool=False)

    def _check_social_needs(self, stimulus: str) -> Decision:
        """Проверяет потребность в социальном взаимодействии"""

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
            )

        return Decision(use_tool=False)

    def _check_autonomy_needs(self, stimulus: str) -> Decision:
        """Проверяет потребность в автономии"""

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
            )

        return Decision(use_tool=False)

    def _extract_topic(self, stimulus: str) -> list:
        """Извлекает темы из стимула"""
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
            # Если ничего не осталось, берём все значимые слова
            words = [w for w in cleaned.split() if len(w) > 3]

        return words[:5] if words else []

    def _is_technical_topic(self, topic: str) -> bool:
        """Определяет, техническая ли тема"""
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
        """Пытается угадать владельца репозитория"""
        if "python" in topic.lower():
            return "python"
        if "react" in topic.lower():
            return "facebook"
        return "unknown"

    def _guess_subreddit(self, stimulus: str) -> str:
        """Определяет подходящий сабреддит"""
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
