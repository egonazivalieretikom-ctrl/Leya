"""Тесты задачи 2.1: robust обработка пользовательских запросов.

Проверяем:
- 20+ вариаций формулировок одного намерения (parametrized)
- Трёхуровневая классификация (эвристика → cache → LLM)
- Confidence-based routing (если эвристика уверена — LLM не зовём)
- Graceful degradation при недоступности LLM
- Кэширование результатов
"""

from unittest.mock import AsyncMock

import pytest

from leya_core.exceptions import LeyaLLMError, LeyaLLMUnavailableError
from leya_core.request_classifier import (
    IntentClassification,
    RequestClassifier,
    UserIntent,
)

# =================================================================================
# ФИКСТУРЫ
# =================================================================================


@pytest.fixture
def mock_llm():
    """Мок LLM-клиента."""
    llm = AsyncMock()
    llm.chat = AsyncMock()
    return llm


@pytest.fixture
def mock_memory():
    """Мок памяти с retrieve_context."""
    mem = AsyncMock()
    mem.retrieve_context = AsyncMock(return_value=[])
    return mem


@pytest.fixture
def classifier(mock_llm, mock_memory):
    """RequestClassifier с моками."""
    return RequestClassifier(
        llm_client=mock_llm,
        memory=mock_memory,
        use_llm_threshold=0.6,  # ниже этого — LLM не зовём
    )


# =================================================================================
# PARAMETRIZED TESTS — 20+ вариаций формулировок
# =================================================================================


class TestIntentClassificationParametrized:
    """Parametrized тесты на 20+ вариаций формулировок одного намерения."""

    @pytest.mark.parametrize(
        "user_input,expected_intent",
        [
            # GREETING — 5 вариаций
            ("Привет!", UserIntent.GREETING),
            ("Здравствуй", UserIntent.GREETING),
            ("Добрый день", UserIntent.GREETING),
            ("Хеллоу", UserIntent.GREETING),
            ("Приветствую тебя", UserIntent.GREETING),
            # FAREWELL — 4 вариации
            ("Пока", UserIntent.FAREWELL),
            ("До свидания", UserIntent.FAREWELL),
            ("Увидимся", UserIntent.FAREWELL),
            ("Всего доброго", UserIntent.FAREWELL),
            # QUESTION — 5 вариаций
            ("Что такое квантовая физика?", UserIntent.QUESTION),
            ("Расскажи про Python", UserIntent.QUESTION),
            ("Объясни, как работает asyncio", UserIntent.QUESTION),
            ("Кто такой Эйнштейн?", UserIntent.QUESTION),
            ("Почему небо голубое?", UserIntent.QUESTION),
            # SEARCH — 3 вариации
            ("Поищи в интернете про нейросети", UserIntent.SEARCH),
            ("Найди информацию о погоде", UserIntent.SEARCH),
            ("Загугли последние новости", UserIntent.SEARCH),
            # REMEMBER — 3 вариации
            ("Запомни, что я люблю кофе", UserIntent.REMEMBER),
            ("Сохрани это: мой день рождения 1 января", UserIntent.REMEMBER),
            ("Запиши, что я программист", UserIntent.REMEMBER),
            # STATUS — 3 вариации
            ("Как ты себя чувствуешь?", UserIntent.STATUS),
            ("Какое у тебя состояние?", UserIntent.STATUS),
            ("Что ты сейчас делаешь?", UserIntent.STATUS),
        ],
    )
    @pytest.mark.asyncio
    async def test_variations_classified_correctly(self, classifier, user_input, expected_intent):
        """Разные формулировки одного намерения классифицируются правильно."""
        result = await classifier.classify(user_input)

        assert isinstance(result, IntentClassification)
        assert result.intent == expected_intent
        assert 0.0 <= result.confidence <= 1.0
        assert result.source in ("heuristic", "cache", "llm", "fallback")

    @pytest.mark.parametrize(
        "user_input",
        [
            "",  # пустой
            "   ",  # только пробелы
            "а",  # очень короткий
            "123",  # только цифры
        ],
    )
    @pytest.mark.asyncio
    async def test_edge_cases_do_not_crash(self, classifier, user_input):
        """Edge cases не роняют классификатор."""
        result = await classifier.classify(user_input)
        assert isinstance(result, IntentClassification)
        # Может быть UNKNOWN, но не crash


# =================================================================================
# CONFIDENCE-BASED ROUTING TESTS
# =================================================================================


class TestConfidenceBasedRouting:
    """Проверяем, что LLM не зовём, если эвристика уверена."""

    @pytest.mark.asyncio
    async def test_high_confidence_heuristic_skips_llm(self, classifier, mock_llm):
        """Если эвристика даёт confidence ≥ threshold — LLM не вызывается."""
        result = await classifier.classify("Привет!")

        assert result.intent == UserIntent.GREETING
        assert result.confidence >= 0.8
        assert result.source == "heuristic"
        # LLM не должен был вызываться
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_low_confidence_heuristic_calls_llm(self, classifier, mock_llm):
        """Если эвристика не уверена — вызывается LLM."""
        # Мокаем LLM ответ
        mock_llm.chat.return_value = (
            '{"intent": "QUESTION", "confidence": 0.9, "topic": "квантовая физика"}'
        )

        # Неоднозначный запрос
        result = await classifier.classify("Мне интересно узнать что-то новое")

        # LLM должен был вызваться
        mock_llm.chat.assert_called()
        assert result.source == "llm"


# =================================================================================
# GRACEFUL DEGRADATION TESTS
# =================================================================================


class TestGracefulDegradation:
    """Проверяем, что классификатор работает при недоступности LLM."""

    @pytest.mark.asyncio
    async def test_llm_unavailable_falls_back_to_heuristic(self, classifier, mock_llm):
        """Если LLM недоступен (Circuit Breaker OPEN) — fallback на эвристику."""
        mock_llm.chat.side_effect = LeyaLLMUnavailableError("LLM unavailable")

        # Неоднозначный запрос, который обычно требует LLM
        result = await classifier.classify("Мне интересно узнать что-то новое")

        # Не должно упасть, должен быть fallback
        assert isinstance(result, IntentClassification)
        assert result.source in ("heuristic", "fallback")

    @pytest.mark.asyncio
    async def test_llm_error_falls_back_to_heuristic(self, classifier, mock_llm):
        """Если LLM вернул ошибку — fallback на эвристику."""
        mock_llm.chat.side_effect = LeyaLLMError("LLM error")

        result = await classifier.classify("Сложный запрос")

        assert isinstance(result, IntentClassification)
        assert result.source in ("heuristic", "fallback")


# =================================================================================
# SEMANTIC CACHE TESTS
# =================================================================================


class TestSemanticCache:
    """Проверяем кэширование через memory."""

    @pytest.mark.asyncio
    async def test_similar_query_uses_cache(self, classifier, mock_memory):
        """Если похожий запрос уже был обработан — используем кэш."""
        # Мокаем memory, который возвращает похожий запрос
        mock_memory.retrieve_context.return_value = [
            {
                "content": "Привет, как дела?",
                "metadata": {
                    "intent": "GREETING",
                    "confidence": 0.95,
                    "topic": None,
                },
                "similarity": 0.92,
            }
        ]

        result = await classifier.classify("Привет, как ты?")

        # Должен использовать cache
        assert result.intent == UserIntent.GREETING
        assert result.source == "cache"
        assert result.confidence >= 0.85

    @pytest.mark.asyncio
    async def test_no_similar_query_skips_cache(self, classifier, mock_memory):
        """Если похожих запросов нет — cache не используется."""
        mock_memory.retrieve_context.return_value = []

        result = await classifier.classify("Привет!")

        # Не должен использовать cache
        assert result.source != "cache"


# =================================================================================
# TOPIC EXTRACTION TESTS
# =================================================================================


class TestTopicExtraction:
    """Проверяем извлечение темы из запроса."""

    @pytest.mark.asyncio
    async def test_topic_extracted_from_question(self, classifier, mock_llm):
        """Тема извлекается из вопроса."""
        mock_llm.chat.return_value = (
            '{"intent": "QUESTION", "confidence": 0.9, "topic": "квантовая физика"}'
        )

        result = await classifier.classify("Что такое квантовая физика?")

        assert result.topic is not None
        assert len(result.topic) > 0

    @pytest.mark.asyncio
    async def test_topic_none_for_greeting(self, classifier):
        """Для приветствия тема не извлекается."""
        result = await classifier.classify("Привет!")

        assert result.topic is None or result.topic == ""


# =================================================================================
# INTEGRATION TESTS
# =================================================================================


class TestRequestClassifierIntegration:
    """Интеграционные тесты полного цикла."""

    @pytest.mark.asyncio
    async def test_full_pipeline_heuristic(self, classifier):
        """Полный цикл: эвристика → возврат."""
        result = await classifier.classify("Пока!")

        assert result.intent == UserIntent.FAREWELL
        assert result.confidence >= 0.8
        assert result.source == "heuristic"

    @pytest.mark.asyncio
    async def test_full_pipeline_with_llm(self, classifier, mock_llm):
        """Полный цикл: эвристика (low confidence) → LLM → возврат."""
        mock_llm.chat.return_value = (
            '{"intent": "SEARCH", "confidence": 0.85, "topic": "нейросети"}'
        )

        result = await classifier.classify("Хочу узнать что-то интересное")

        assert result.intent == UserIntent.SEARCH
        assert result.source == "llm"
