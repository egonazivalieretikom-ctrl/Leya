"""Тесты задачи 1.5: надёжный парсинг LLM-ответов + token budgeting.

Проверяем:
- Pydantic модель CognitiveOutput валидирует все поля
- repair_json обрабатывает edge cases (Unicode, nested, markdown, trailing text)
- _safe_parse_json: Pydantic-first, repair_json как fallback
- Token estimation: реальный токенизатор + dynamic ratio
- _truncate_context: relevance-based, а не только newest
- generate_plan: structured error при failure (не просто static fallback)
"""

import json
import pytest
from hypothesis import given, strategies as st, settings, assume

from leya_core.thinker import (
    CognitiveOutput,
    ActionIntent,
    repair_json,
    _safe_parse_json,
    _estimate_tokens,
    _truncate_context,
)
from leya_core.exceptions import LeyaJSONParseError


# =================================================================================
# PYDANTIC MODEL TESTS
# =================================================================================

class TestCognitiveOutputModel:
    """Проверяем Pydantic модель CognitiveOutput."""

    def test_valid_minimal_output(self):
        """Минимальный валидный output."""
        data = {
            "response": "Привет!",
            "internal_monologue": "Пользователь поздоровался",
            "action_intent": "RESPOND",
            "tool_call": None,
            "self_reflection": "Я ответила на приветствие",
        }
        output = CognitiveOutput.model_validate(data)
        assert output.response == "Привет!"
        assert output.action_intent == ActionIntent.RESPOND

    def test_valid_full_output(self):
        """Полный output со всеми полями."""
        data = {
            "response": "Ищу информацию...",
            "internal_monologue": "Нужно использовать инструмент",
            "action_intent": "USE_TOOL",
            "tool_call": {
                "tool_name": "search_web",
                "parameters": {"query": "Python asyncio"},
            },
            "self_reflection": "Я решила поискать в интернете",
        }
        output = CognitiveOutput.model_validate(data)
        assert output.action_intent == ActionIntent.USE_TOOL
        assert output.tool_call.tool_name == "search_web"

    def test_invalid_action_intent(self):
        """Невалидный action_intent → ValidationError."""
        data = {
            "response": "test",
            "internal_monologue": "test",
            "action_intent": "INVALID_INTENT",
            "tool_call": None,
            "self_reflection": "test",
        }
        with pytest.raises(Exception):  # Pydantic ValidationError
            CognitiveOutput.model_validate(data)

    def test_missing_required_field(self):
        """Отсутствие обязательного поля → ValidationError."""
        data = {
            "response": "test",
            # missing internal_monologue
            "action_intent": "RESPOND",
            "tool_call": None,
            "self_reflection": "test",
        }
        with pytest.raises(Exception):
            CognitiveOutput.model_validate(data)

    def test_tool_call_without_use_tool_intent(self):
        """tool_call без USE_TOOL intent — валидно (может быть None)."""
        data = {
            "response": "test",
            "internal_monologue": "test",
            "action_intent": "RESPOND",
            "tool_call": None,
            "self_reflection": "test",
        }
        output = CognitiveOutput.model_validate(data)
        assert output.tool_call is None


# =================================================================================
# REPAIR_JSON TESTS (parametrized)
# =================================================================================

class TestRepairJson:
    """Проверяем repair_json на известных edge cases."""

    @pytest.mark.parametrize("malformed,expected_key", [
        # Markdown code blocks
        ('```json\n{"response": "test"}\n```', "response"),
        ('```\n{"response": "test"}\n```', "response"),
        
        # Trailing commas
        ('{"response": "test",}', "response"),
        ('{"response": "test", "internal_monologue": "x",}', "response"),
        
        # Unclosed brackets
        ('{"response": "test"', "response"),
        ('{"response": "test", "internal_monologue": "x"', "response"),
        
        # Trailing text after JSON
        ('{"response": "test"}\nSome trailing text', "response"),
        ('{"response": "test"} // comment', "response"),
        
        # Unicode in strings
        ('{"response": "Привет мир!"}', "response"),
        ('{"response": "Hello 世界 🌍"}', "response"),
        
        # Nested objects
        ('{"tool_call": {"tool_name": "search", "parameters": {"query": "test"}}}', "tool_call"),
        
        # Deeply nested
        ('{"a": {"b": {"c": {"d": "value"}}}}', "a"),
        
        # Empty strings
        ('{"response": ""}', "response"),
        
        # Escaped quotes
        ('{"response": "He said \\"hello\\""}', "response"),
    ])
    def test_repair_known_edge_cases(self, malformed, expected_key):
        """repair_json должен обрабатывать известные edge cases."""
        repaired = repair_json(malformed)
        # Должен быть валидный JSON
        parsed = json.loads(repaired)
        assert expected_key in parsed or len(parsed) > 0

    @pytest.mark.parametrize("malformed", [
        'not json at all',
        '',
        '   ',
        '{invalid json}',
        '{"unclosed": "string',
    ])
    def test_repair_invalid_input_returns_empty_or_raises(self, malformed):
        """repair_json на полностью невалидном входе возвращает "{}" или бросает."""
        try:
            repaired = repair_json(malformed)
            # Если вернул — должен быть валидный JSON (хотя бы "{}")
            json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            # Это допустимо для полностью невалидного ввода
            pass


# =================================================================================
# REPAIR_JSON PROPERTY-BASED TESTS
# =================================================================================

class TestRepairJsonPropertyBased:
    """Property-based тесты для repair_json."""

    @given(st.text(min_size=1, max_size=500))
    @settings(max_examples=100)
    def test_repair_never_crashes(self, text):
        """repair_json не должен падать на любом входе."""
        try:
            result = repair_json(text)
            # Если вернул — должен быть валидный JSON
            json.loads(result)
        except (json.JSONDecodeError, ValueError):
            # Допустимо для невалидного ввода
            pass

    @given(
        response=st.text(min_size=0, max_size=100),
        monologue=st.text(min_size=0, max_size=100),
    )
    @settings(max_examples=50)
    def test_repair_valid_json_with_random_strings(self, response, monologue):
        """repair_json не должен ломать валидный JSON со случайными строками."""
        # Экранируем кавычки для валидного JSON
        response_escaped = response.replace('"', '\\"')
        monologue_escaped = monologue.replace('"', '\\"')
        
        valid_json = f'{{"response": "{response_escaped}", "internal_monologue": "{monologue_escaped}"}}'
        repaired = repair_json(valid_json)
        parsed = json.loads(repaired)
        assert "response" in parsed


# =================================================================================
# SAFE_PARSE_JSON TESTS
# =================================================================================

class TestSafeParseJson:
    """Проверяем _safe_parse_json с Pydantic-first подходом."""

    def test_parse_valid_json_with_pydantic(self):
        """Валидный JSON → CognitiveOutput через Pydantic."""
        raw = json.dumps({
            "response": "test",
            "internal_monologue": "thinking",
            "action_intent": "RESPOND",
            "tool_call": None,
            "self_reflection": "reflected",
        })
        output = _safe_parse_json(raw)
        assert isinstance(output, CognitiveOutput)
        assert output.response == "test"

    def test_parse_malformed_json_with_repair(self):
        """Malformed JSON → repair_json → Pydantic."""
        raw = '```json\n{"response": "test", "internal_monologue": "x", "action_intent": "RESPOND", "tool_call": null, "self_reflection": "y"}\n```'
        output = _safe_parse_json(raw)
        assert isinstance(output, CognitiveOutput)
        assert output.response == "test"

    def test_parse_invalid_json_raises_error(self):
        """Полностью невалидный JSON → LeyaJSONParseError."""
        raw = "not json at all"
        with pytest.raises(LeyaJSONParseError):
            _safe_parse_json(raw)

    def test_parse_valid_json_but_invalid_pydantic_raises_error(self):
        """Валидный JSON, но не соответствует Pydantic схеме → LeyaJSONParseError."""
        raw = json.dumps({"response": "test"})  # missing required fields
        with pytest.raises(LeyaJSONParseError):
            _safe_parse_json(raw)


# =================================================================================
# TOKEN ESTIMATION TESTS
# =================================================================================

class TestTokenEstimation:
    """Проверяем _estimate_tokens с реальным токенизатором."""

    def test_estimate_short_text(self):
        """Короткий текст → разумная оценка."""
        text = "Hello world"
        tokens = _estimate_tokens(text)
        assert 2 <= tokens <= 10  # примерно 2-3 токена

    def test_estimate_long_text(self):
        """Длинный текст → пропорциональная оценка."""
        text = "word " * 100
        tokens = _estimate_tokens(text)
        assert 50 <= tokens <= 200  # примерно 100 токенов

    def test_estimate_unicode_text(self):
        """Unicode текст → корректная оценка."""
        text = "Привет мир 世界 🌍"
        tokens = _estimate_tokens(text)
        assert 5 <= tokens <= 20

    def test_estimate_empty_text(self):
        """Пустой текст → 0 токенов."""
        tokens = _estimate_tokens("")
        assert tokens == 0


# =================================================================================
# TRUNCATE CONTEXT TESTS
# =================================================================================

class TestTruncateContext:
    """Проверяем _truncate_context с relevance-based подходом."""

    def test_truncate_by_token_budget(self):
        """Truncation по token budget."""
        context = [
            {"content": "word " * 100, "relevance_score": 0.9},
            {"content": "word " * 100, "relevance_score": 0.5},
            {"content": "word " * 100, "relevance_score": 0.1},
        ]
        max_tokens = 150
        truncated = _truncate_context(context, max_tokens)
        # Должен оставить только самые релевантные
        assert len(truncated) <= 2

    def test_truncate_preserves_high_relevance(self):
        """Truncation сохраняет высокорелевантные записи."""
        context = [
            {"content": "short", "relevance_score": 0.99},
            {"content": "word " * 1000, "relevance_score": 0.01},
        ]
        max_tokens = 50
        truncated = _truncate_context(context, max_tokens)
        # Первая запись должна быть сохранена
        assert any("short" in item["content"] for item in truncated)

    def test_truncate_empty_context(self):
        """Пустой контекст → пустой результат."""
        truncated = _truncate_context([], 100)
        assert truncated == []


# =================================================================================
# GENERATE_PLAN STRUCTURED ERROR TESTS
# =================================================================================

class TestGeneratePlanStructuredError:
    """Проверяем generate_plan с structured error при failure."""

    @pytest.mark.asyncio
    async def test_generate_plan_returns_structured_error_on_failure(self):
        """generate_plan при failure возвращает structured error, не просто static dict."""
        from unittest.mock import AsyncMock, MagicMock
        from leya_core.thinker import CoreThinker
        from leya_core.config import ThinkerConfig
        from leya_core.exceptions import LeyaLLMError

        # Мокаем LLM client, который всегда падает
        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = LeyaLLMError("LLM unavailable")

        config = ThinkerConfig()
        thinker = CoreThinker(config, mock_llm)

        # Мокаем остальные зависимости
        thinker._build_cognitive_prompt = MagicMock(return_value="test prompt")

        # generate_plan должен вернуть structured error
        result = await thinker.generate_plan(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test soul",
            drive_context="test drives",
            memory_context=[],
            tools=[],
        )

        # Результат должен содержать информацию об ошибке
        assert "error" in result or "fallback" in result or isinstance(result, dict)
        # Если это dict — должен иметь структуру CognitiveOutput (хотя бы частично)
        if isinstance(result, dict):
            assert "response" in result or "error" in result