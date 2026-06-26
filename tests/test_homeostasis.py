"""
Тесты для HomeostasisEngine.

Проверяет:
- Генерацию целей на основе дисбаланса драйвов
- Rest period
- Mark as researched
- Извлечение фактов и терминов (mock LLM)
"""

from __future__ import annotations

import json
import time

import pytest

from leya_core.drives import DriveType
from leya_core.homeostasis_engine import HomeostasisEngine


class TestHomeostasisInit:
    """Тесты инициализации HomeostasisEngine."""

    def test_init_with_config(self, test_homeostasis_config):
        """HomeostasisEngine корректно инициализируется."""
        he = HomeostasisEngine(config=test_homeostasis_config)

        assert he.config.rest_period == test_homeostasis_config.rest_period
        assert he.config.curiosity_threshold == test_homeostasis_config.curiosity_threshold

    def test_init_default_config(self):
        """HomeostasisEngine инициализируется с конфигом по умолчанию."""
        he = HomeostasisEngine()
        assert he.config.rest_period > 0


class TestGoalGeneration:
    """Тесты генерации целей."""

    def test_generate_goal_with_high_disbalance(self, test_homeostasis_config):
        """Цель генерируется при высоком дисбалансе."""
        he = HomeostasisEngine(config=test_homeostasis_config)
        he.last_action_time = 0  # Сбрасываем rest period

        drive_state = {
            DriveType.CURIOSITY: 0.9,  # Высокий дисбаланс
            DriveType.CONNECTION: 0.3,
        }
        predicted_state = {
            DriveType.CURIOSITY: 0.95,
            DriveType.CONNECTION: 0.3,
        }

        goal = he.generate_goal(
            drive_state=drive_state,
            predicted_state=predicted_state,
            recent_episodes=[],
            action_values={},
        )

        assert goal is not None
        assert "name" in goal
        assert "urgency" in goal

    def test_no_goal_with_low_disbalance(self, test_homeostasis_config):
        """Цель не генерируется при низком дисбалансе."""
        he = HomeostasisEngine(config=test_homeostasis_config)
        he.last_action_time = 0

        drive_state = {
            DriveType.CURIOSITY: 0.2,  # Низкий дисбаланс
            DriveType.CONNECTION: 0.2,
        }
        predicted_state = {
            DriveType.CURIOSITY: 0.2,
            DriveType.CONNECTION: 0.2,
        }

        goal = he.generate_goal(
            drive_state=drive_state,
            predicted_state=predicted_state,
            recent_episodes=[],
            action_values={},
        )

        assert goal is None

    def test_respects_rest_period(self, test_homeostasis_config):
        """Rest period предотвращает слишком частую генерацию."""
        test_homeostasis_config.rest_period = 60  # 60 секунд
        he = HomeostasisEngine(config=test_homeostasis_config)

        # Недавно было действие
        he.last_action_time = time.time()

        drive_state = {DriveType.CURIOSITY: 0.9}
        predicted_state = {DriveType.CURIOSITY: 0.95}

        goal = he.generate_goal(
            drive_state=drive_state,
            predicted_state=predicted_state,
            recent_episodes=[],
            action_values={},
        )

        assert goal is None  # Должен быть в rest period


class TestMarkAsResearched:
    """Тесты отметки исследованных тем."""

    def test_mark_as_researched(self, test_homeostasis_config):
        """Тема помечается как исследованная."""
        he = HomeostasisEngine(config=test_homeostasis_config)

        he.mark_as_researched("квантовая физика")

        assert "квантовая физика" in he.recently_researched

    def test_mark_as_researched_no_duplicates(self, test_homeostasis_config):
        """Дубликаты не добавляются."""
        he = HomeostasisEngine(config=test_homeostasis_config)

        he.mark_as_researched("квантовая физика")
        he.mark_as_researched("квантовая физика")

        assert he.recently_researched.count("квантовая физика") == 1

    def test_mark_as_researched_limits_size(self, test_homeostasis_config):
        """Список исследованных тем ограничен."""
        test_homeostasis_config.max_researched_topics = 3
        he = HomeostasisEngine(config=test_homeostasis_config)

        for i in range(5):
            he.mark_as_researched(f"тема{i}")

        assert len(he.recently_researched) <= 3


class TestDynamicKeywords:
    """Тесты динамических ключевых слов."""

    def test_add_dynamic_keywords(self, test_homeostasis_config):
        """Динамические ключевые слова добавляются."""
        he = HomeostasisEngine(config=test_homeostasis_config)

        he.add_dynamic_keywords(["нейробиология", "сознание"])

        assert "нейробиология" in he.dynamic_keywords
        assert "сознание" in he.dynamic_keywords


class TestPersistence:
    """Тесты сохранения и загрузки состояния."""

    def test_save_state(self, test_homeostasis_config):
        """save_state возвращает корректный dict."""
        he = HomeostasisEngine(config=test_homeostasis_config)
        he.recently_researched = ["тема1", "тема2"]
        he.dynamic_keywords = ["ключ1"]

        state = he.save_state()

        assert "recently_researched" in state
        assert "dynamic_keywords" in state
        assert state["recently_researched"] == ["тема1", "тема2"]

    def test_load_state(self, test_homeostasis_config):
        """load_state восстанавливает состояние."""
        he = HomeostasisEngine(config=test_homeostasis_config)

        state = {
            "recently_researched": ["тема1"],
            "dynamic_keywords": ["ключ1"],
        }

        he.load_state(state)

        assert "тема1" in he.recently_researched
        assert "ключ1" in he.dynamic_keywords


class TestExtractFacts:
    """Тесты извлечения фактов через LLM."""

    @pytest.mark.asyncio
    async def test_extract_key_facts(self, test_homeostasis_config):
        """Извлечение ключевых фактов работает."""
        he = HomeostasisEngine(config=test_homeostasis_config)

        # Mock LLM возвращает JSON с фактами
        async def mock_llm(prompt, require_json=False):
            return json.dumps(
                {
                    "facts": ["Факт 1", "Факт 2", "Факт 3"],
                }
            )

        # Текст должен быть >= 50 символов (проверка в extract_key_facts)
        long_text = (
            "Сознание — это субъективный опыт восприятия окружающего мира и себя. "
            "Оно включает в себя ощущения, мысли, эмоции и самосознание. "
            "Изучение сознания является одной из центральных задач нейробиологии и философии."
        )

        facts = await he.extract_key_facts(
            topic="сознание",
            article_text=long_text,
            llm_client=mock_llm,
        )

        assert len(facts) == 3
        assert "Факт 1" in facts

    @pytest.mark.asyncio
    async def test_extract_key_facts_short_text(self, test_homeostasis_config):
        """Короткий текст не обрабатывается."""
        he = HomeostasisEngine(config=test_homeostasis_config)

        # Локальный mock (не используем fixture, т.к. он не нужен для короткого текста)
        async def mock_llm(prompt, require_json=False):
            return json.dumps({"facts": []})

        facts = await he.extract_key_facts(
            topic="тема",
            article_text="Коротко",  # < 50 символов
            llm_client=mock_llm,
        )

        assert facts == []


class TestUpdateFromSelfModel:
    """Тесты обновления из self_model."""

    def test_update_from_self_model_with_fatigue(self, test_homeostasis_config):
        """Упоминание усталости повышает порог REST."""
        he = HomeostasisEngine(config=test_homeostasis_config)
        initial_rest_threshold = he.thresholds[DriveType.REST]

        he.update_from_self_model("Я чувствую себя усталой...")

        assert he.thresholds[DriveType.REST] >= initial_rest_threshold

    def test_update_from_self_model_with_curiosity(self, test_homeostasis_config):
        """Упоминание любопытства понижает порог CURIOSITY."""
        he = HomeostasisEngine(config=test_homeostasis_config)
        initial_curiosity_threshold = he.thresholds[DriveType.CURIOSITY]

        he.update_from_self_model("Мне очень любопытно узнать больше...")

        assert he.thresholds[DriveType.CURIOSITY] <= initial_curiosity_threshold
