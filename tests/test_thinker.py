"""
Unit-тесты для leya_core/thinker.py
Покрывает: _build_cognitive_prompt, _safe_parse_json, repair_json,
_estimate_tokens, _truncate_context, CoreThinker.

Этап 3.4: Полное покрытие с проверкой Pydantic-модели,
token budgeting, relevance-based truncation, structured error.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from leya_core.config import ThinkerConfig
from leya_core.exceptions import LeyaJSONParseError, LeyaLLMError, LeyaLLMTimeoutError
from leya_core.thinker import (
    ActionIntent,
    CognitiveOutput,
    CoreThinker,
    ToolCall,
    _estimate_tokens,
    _safe_parse_json,
    _truncate_context,
    repair_json,
)


# =============================================================================
# PYDANTIC MODEL TESTS
# =============================================================================

class TestCognitiveOutputModel:
    """Тесты Pydantic-модели CognitiveOutput."""

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
        assert output.tool_call is None

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
        assert output.tool_call.parameters["query"] == "Python asyncio"

    def test_invalid_action_intent_raises_error(self):
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
        """Отсутствие action_intent заполняется дефолтом (RESPOND)."""
        invalid_json = '{"response": "test"}'
        result = _safe_parse_json(invalid_json)
        assert result.action_intent == ActionIntent.RESPOND
        assert result.response == "test"

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

    def test_all_action_intents(self):
        """Все значения ActionIntent валидны."""
        for intent in ActionIntent:
            data = {
                "response": "test",
                "internal_monologue": "test",
                "action_intent": intent.value,
                "tool_call": None,
                "self_reflection": "test",
            }
            output = CognitiveOutput.model_validate(data)
            assert output.action_intent == intent

    def test_tool_call_model(self):
        """ToolCall модель валидируется корректно."""
        tool = ToolCall(tool_name="test", parameters={"key": "value"})
        assert tool.tool_name == "test"
        assert tool.parameters["key"] == "value"

    def test_tool_call_dump(self):
        """ToolCall.model_dump() возвращает dict."""
        tool = ToolCall(tool_name="test", parameters={"key": "value"})
        dumped = tool.model_dump()
        assert dumped["tool_name"] == "test"
        assert dumped["parameters"]["key"] == "value"


# =============================================================================
# TOKEN ESTIMATION TESTS
# =============================================================================

class TestEstimateTokens:
    """Тесты _estimate_tokens с tiktoken и fallback."""

    def test_estimate_short_text(self):
        """Короткий текст → разумная оценка."""
        text = "Hello world"
        tokens = _estimate_tokens(text)
        assert 2 <= tokens <= 10

    def test_estimate_long_text(self):
        """Длинный текст → пропорциональная оценка."""
        text = "word " * 100
        tokens = _estimate_tokens(text)
        assert 50 <= tokens <= 200

    def test_estimate_unicode_text(self):
        """Unicode текст → корректная оценка."""
        text = "Привет мир 世界 🌍"
        tokens = _estimate_tokens(text)
        assert 5 <= tokens <= 20

    def test_estimate_empty_text(self):
        """Пустой текст → 0 токенов."""
        tokens = _estimate_tokens("")
        assert tokens == 0

    def test_estimate_none_text(self):
        """None текст → 0 токенов."""
        tokens = _estimate_tokens(None)
        assert tokens == 0

    def test_estimate_custom_ratio(self):
        """Кастомный ratio влияет на оценку (только без tiktoken)."""
        import leya_core.thinker as thinker_module
    
        # Сохраняем оригинальное значение
        original_use_real = thinker_module._USE_REAL_TOKENIZER
    
        try:
            # Отключаем tiktoken для теста
            thinker_module._USE_REAL_TOKENIZER = False
        
            text = "a" * 100
            tokens_low = _estimate_tokens(text, ratio=2.0)
            tokens_high = _estimate_tokens(text, ratio=5.0)
            assert tokens_low > tokens_high
        finally:
            # Восстанавливаем оригинальное значение
            thinker_module._USE_REAL_TOKENIZER = original_use_real

    def test_estimate_with_tiktoken(self):
        """С tiktoken оценка точнее."""
        text = "Hello world, this is a test"
        tokens = _estimate_tokens(text)
        # tiktoken должен дать ~7-8 токенов
        assert 5 <= tokens <= 15

    def test_estimate_unicode_adjustment(self):
        """Unicode >30% → adjusted_ratio."""
        text = "Привет мир " * 10  # Много Unicode
        tokens = _estimate_tokens(text, ratio=3.5)
        # Должно быть больше, чем без Unicode adjustment
        assert tokens > 0


# =============================================================================
# REPAIR JSON TESTS
# =============================================================================

class TestRepairJson:
    """Тесты repair_json на edge cases."""

    @pytest.mark.parametrize(
        "malformed,expected_key",
        [
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
            (
                '{"tool_call": {"tool_name": "search", "parameters": {"query": "test"}}}',
                "tool_call",
            ),
            # Deeply nested
            ('{"a": {"b": {"c": {"d": "value"}}}}', "a"),
            # Empty strings
            ('{"response": ""}', "response"),
            # Escaped quotes
            ('{"response": "He said \\"hello\\""}', "response"),
            # Unicode escape sequences
            ('{"response": "\\u041f\\u0440\\u0438\\u0432\\u0435\\u0442"}', "response"),
            # Mixed escape sequences
            ('{"response": "Line1\\nLine2\\tTab"}', "response"),
        ],
    )
    def test_repair_known_edge_cases(self, malformed, expected_key):
        """repair_json должен обрабатывать известные edge cases."""
        repaired = repair_json(malformed)
        parsed = json.loads(repaired)
        assert expected_key in parsed or len(parsed) > 0

    @pytest.mark.parametrize(
        "malformed",
        [
            "not json at all",
            "",
            "    ",
            "{invalid json}",
            '{"unclosed": "string',
        ],
    )
    def test_repair_invalid_input_returns_empty_or_raises(self, malformed):
        """repair_json на полностью невалидном входе возвращает "{}" или бросает."""
        try:
            repaired = repair_json(malformed)
            json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            pass  # Допустимо для полностью невалидного ввода

    def test_repair_preserves_unicode_escape(self):
        """repair_json сохраняет Unicode escape sequences."""
        malformed = '{"response": "\\u041f\\u0440\\u0438\\u0432\\u0435\\u0442"}'
        repaired = repair_json(malformed)
        parsed = json.loads(repaired)
        assert "response" in parsed
        # Должно декодироваться в "Привет"
        assert parsed["response"] == "Привет"

    def test_repair_handles_nested_strings_with_braces(self):
        """repair_json не считает braces внутри строк."""
        malformed = '{"response": "Text with {braces} inside"}'
        repaired = repair_json(malformed)
        parsed = json.loads(repaired)
        assert parsed["response"] == "Text with {braces} inside"

    def test_repair_max_length_limit(self):
        """repair_json отклоняет слишком длинные невалидные строки."""
        from leya_core.thinker import REPAIR_JSON_MAX_LENGTH

        # Создаём НЕВАЛИДНЫЙ JSON с превышением длины
        # (незакрытая скобка, чтобы не сработал early return)
        huge_json = '{"response": "' + "a" * (REPAIR_JSON_MAX_LENGTH + 1)
    
        with pytest.raises(LeyaJSONParseError):
            repair_json(huge_json)


# =============================================================================
# SAFE PARSE JSON TESTS
# =============================================================================

class TestSafeParseJson:
    """Тесты _safe_parse_json с Pydantic-first подходом."""

    def test_parse_valid_json_with_pydantic(self):
        """Валидный JSON → CognitiveOutput через Pydantic."""
        raw = json.dumps(
            {
                "response": "test",
                "internal_monologue": "thinking",
                "action_intent": "RESPOND",
                "tool_call": None,
                "self_reflection": "reflected",
            }
        )
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
        invalid_json = "not json at all"
        with pytest.raises(LeyaJSONParseError):
            _safe_parse_json(invalid_json)

    def test_parse_valid_json_but_invalid_pydantic_raises_error(self):
        """Валидный JSON, но невалидная схема → LeyaJSONParseError."""
        valid_json_but_wrong_schema = '{"foo": "bar"}'
        with pytest.raises(LeyaJSONParseError):
            _safe_parse_json(valid_json_but_wrong_schema)

    def test_parse_empty_response_raises_error(self):
        """Пустой response и internal_monologue → LeyaJSONParseError."""
        raw = json.dumps(
            {
                "response": "",
                "internal_monologue": "",
                "action_intent": "RESPOND",
                "tool_call": None,
                "self_reflection": "test",
            }
        )
        with pytest.raises(LeyaJSONParseError):
            _safe_parse_json(raw)

    def test_parse_whitespace_only_response_raises_error(self):
        """Whitespace-only response и internal_monologue → LeyaJSONParseError."""
        raw = json.dumps(
            {
                "response": "   ",
                "internal_monologue": "  ",
                "action_intent": "RESPOND",
                "tool_call": None,
                "self_reflection": "test",
            }
        )
        with pytest.raises(LeyaJSONParseError):
            _safe_parse_json(raw)


# =============================================================================
# TRUNCATE CONTEXT TESTS
# =============================================================================

class TestTruncateContext:
    """Тесты _truncate_context с relevance-based подходом."""

    def test_truncate_by_token_budget(self):
        """Truncation по token budget."""
        context = [
            {"content": "word " * 100, "relevance_score": 0.9},
            {"content": "word " * 100, "relevance_score": 0.5},
            {"content": "word " * 100, "relevance_score": 0.1},
        ]
        max_tokens = 150
        truncated = _truncate_context(context, max_tokens)
        assert len(truncated) <= 2

    def test_truncate_preserves_high_relevance(self):
        """Truncation сохраняет высокорелевантные записи."""
        context = [
            {"content": "short", "relevance_score": 0.99},
            {"content": "word " * 1000, "relevance_score": 0.01},
        ]
        max_tokens = 50
        truncated = _truncate_context(context, max_tokens)
        assert any("short" in item["content"] for item in truncated)

    def test_truncate_empty_context(self):
        """Пустой контекст → пустой результат."""
        truncated = _truncate_context([], 100)
        assert truncated == []

    def test_truncate_sorts_by_relevance(self):
        """Truncation сортирует по relevance_score."""
        context = [
            {"content": "low", "relevance_score": 0.1},
            {"content": "high", "relevance_score": 0.9},
            {"content": "medium", "relevance_score": 0.5},
        ]
        max_tokens = 1000
        truncated = _truncate_context(context, max_tokens)
        # Должны быть отсортированы по relevance_score desc
        assert truncated[0]["content"] == "high"
        assert truncated[1]["content"] == "medium"
        assert truncated[2]["content"] == "low"

    def test_truncate_without_relevance_score(self):
        """Без relevance_score — fallback на порядок."""
        context = [
            {"content": "first"},
            {"content": "second"},
            {"content": "third"},
        ]
        max_tokens = 1000
        truncated = _truncate_context(context, max_tokens)
        assert len(truncated) == 3

    def test_truncate_with_custom_ratio(self):
        """Кастомный ratio влияет на truncation."""
        context = [{"content": "word " * 100, "relevance_score": 0.5}]
        truncated_low = _truncate_context(context, 100, ratio=2.0)
        truncated_high = _truncate_context(context, 100, ratio=5.0)
        # С низким ratio должно быть больше токенов
        assert len(truncated_low) >= len(truncated_high)


# =============================================================================
# BUILD COGNITIVE PROMPT TESTS
# =============================================================================

class TestBuildCognitivePrompt:
    """Тесты _build_cognitive_prompt."""

    @pytest.fixture
    def thinker(self):
        """CoreThinker с моком LLM-клиента."""
        from leya_core.llm_backend import LLMBackend
    
        config = ThinkerConfig()
        llm_client = MagicMock(spec=LLMBackend)
        return CoreThinker(config, llm_client)

    def test_prompt_contains_soul_context(self, thinker):
        """Prompt содержит soul_context."""
        prompt = thinker._build_cognitive_prompt(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="Я — Лея, цифровое сознание",
            drive_context="Любопытство: 0.5",
            memory_context=[],
            tools=[],
        )
        assert "Я — Лея, цифровое сознание" in prompt

    def test_prompt_contains_drive_context(self, thinker):
        """Prompt содержит drive_context."""
        prompt = thinker._build_cognitive_prompt(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="Любопытство: 0.8",
            memory_context=[],
            tools=[],
        )
        assert "Любопытство: 0.8" in prompt

    def test_prompt_contains_memory_context(self, thinker):
        """Prompt содержит memory_context."""
        memory = [
            {"content": "Воспоминание 1", "relevance_score": 0.9},
            {"content": "Воспоминание 2", "relevance_score": 0.5},
        ]
        prompt = thinker._build_cognitive_prompt(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="test",
            memory_context=memory,
            tools=[],
        )
        assert "Воспоминание 1" in prompt

    def test_prompt_contains_tools(self, thinker):
        """Prompt содержит tools."""
        tools = [
            {"name": "search_web", "description": "Поиск в интернете"},
        ]
        prompt = thinker._build_cognitive_prompt(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=tools,
        )
        assert "search_web" in prompt

    def test_prompt_contains_stimulus(self, thinker):
        """Prompt содержит stimulus."""
        stimulus = {"type": "USER_MESSAGE", "content": "Привет, Лея!"}
        prompt = thinker._build_cognitive_prompt(
            stimulus=stimulus,
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=[],
        )
        assert "Привет, Лея!" in prompt

    def test_prompt_instructs_json_output(self, thinker):
        """Prompt инструктирует вернуть JSON."""
        prompt = thinker._build_cognitive_prompt(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=[],
        )
        assert "СТРОГО JSON" in prompt or "JSON" in prompt

    def test_prompt_contains_required_fields(self, thinker):
        """Prompt содержит все требуемые поля CognitiveOutput."""
        prompt = thinker._build_cognitive_prompt(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=[],
        )
        assert "response" in prompt
        assert "internal_monologue" in prompt
        assert "action_intent" in prompt
        assert "tool_call" in prompt
        assert "self_reflection" in prompt

    def test_prompt_truncates_memory_by_token_budget(self, thinker):
        """Prompt обрезает memory_context по token budget."""
        # Увеличиваем размер контекста, чтобы он превысил budget
        # available_for_memory ≈ 4994 токенов
        # 5000 "word" = 25000 символов ≈ 7142 токенов > 4994
        memory = [
            {"content": "word " * 5000, "relevance_score": 0.9},
            {"content": "word " * 5000, "relevance_score": 0.1},
        ]
        prompt = thinker._build_cognitive_prompt(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="test",
            memory_context=memory,
            tools=[],
        )
        # Prompt не должен содержать все 10000 "word" (5000 + 5000)
        assert prompt.count("word") < 10000


# =============================================================================
# CORE THINKER TESTS
# =============================================================================

class TestCoreThinker:
    """Тесты CoreThinker."""

    @pytest.fixture
    def thinker(self):
        """CoreThinker с моком LLM-клиента."""
        from leya_core.llm_backend import LLMBackend
    
        config = ThinkerConfig()
        # Используем spec для создания мока, который проходит isinstance проверку
        llm_client = MagicMock(spec=LLMBackend)
        return CoreThinker(config, llm_client)

    @pytest.mark.asyncio
    async def test_generate_plan_success(self, thinker):
        """generate_plan успешно возвращает CognitiveOutput."""
        valid_json = json.dumps(
            {
                "response": "Привет!",
                "internal_monologue": "Пользователь поздоровался",
                "action_intent": "RESPOND",
                "tool_call": None,
                "self_reflection": "Я ответила",
            }
        )
        thinker.llm_client.chat = AsyncMock(return_value=valid_json)

        result = await thinker.generate_plan(
            stimulus={"type": "USER_MESSAGE", "content": "Привет"},
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=[],
        )

        assert result["response"] == "Привет!"
        assert result["action_intent"] == "RESPOND"

    @pytest.mark.asyncio
    async def test_generate_plan_with_tool_call(self, thinker):
        """generate_plan с tool_call."""
        valid_json = json.dumps(
            {
                "response": "Ищу информацию...",
                "internal_monologue": "Нужно использовать инструмент",
                "action_intent": "USE_TOOL",
                "tool_call": {
                    "tool_name": "search_web",
                    "parameters": {"query": "test"},
                },
                "self_reflection": "Я решила поискать",
            }
        )
        thinker.llm_client.chat = AsyncMock(return_value=valid_json)

        result = await thinker.generate_plan(
            stimulus={"type": "USER_MESSAGE", "content": "Найди информацию"},
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=[],
        )

        assert result["action_intent"] == "USE_TOOL"
        assert result["tool_call"]["tool_name"] == "search_web"

    @pytest.mark.asyncio
    async def test_generate_plan_json_parse_error(self, thinker):
        """generate_plan при JSON parse error возвращает structured error."""
        thinker.llm_client.chat = AsyncMock(return_value="not valid json")

        result = await thinker.generate_plan(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=[],
        )

        assert "error" in result
        assert result["error"]["type"] == "JSON_PARSE_ERROR"
        assert result["error"]["fallback_used"] is True

    @pytest.mark.asyncio
    async def test_generate_plan_llm_timeout(self, thinker):
        """generate_plan при LLM timeout возвращает structured error."""
        thinker.llm_client.chat = AsyncMock(
            side_effect=LeyaLLMTimeoutError("Timeout")
        )

        result = await thinker.generate_plan(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=[],
        )

        assert "error" in result
        assert result["error"]["type"] == "LLM_TIMEOUT"

    @pytest.mark.asyncio
    async def test_generate_plan_llm_error(self, thinker):
        """generate_plan при LLM error возвращает structured error."""
        thinker.llm_client.chat = AsyncMock(
            side_effect=LeyaLLMError("Connection failed")
        )

        result = await thinker.generate_plan(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=[],
        )

        assert "error" in result
        assert result["error"]["type"] == "LLM_ERROR"

    @pytest.mark.asyncio
    async def test_generate_plan_unexpected_error(self, thinker):
        """generate_plan при неожиданной ошибке возвращает structured error."""
        thinker.llm_client.chat = AsyncMock(
            side_effect=RuntimeError("Unexpected")
        )

        result = await thinker.generate_plan(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=[],
        )

        assert "error" in result
        assert result["error"]["type"] == "UNEXPECTED_ERROR"

    def test_build_structured_error(self, thinker):
        """_build_structured_error возвращает корректную структуру."""
        error = thinker._build_structured_error(
            error_type="TEST_ERROR",
            error_message="Test message",
            partial_data='{"response": "partial"}',
        )

        assert error["error"]["type"] == "TEST_ERROR"
        assert error["error"]["message"] == "Test message"
        assert error["error"]["fallback_used"] is True
        assert "response" in error

    def test_build_structured_error_extracts_response(self, thinker):
        """_build_structured_error извлекает response из partial_data."""
        error = thinker._build_structured_error(
            error_type="TEST_ERROR",
            error_message="Test",
            partial_data='{"response": "Извлечённый ответ"}',
        )

        assert error["response"] == "Извлечённый ответ"

    def test_build_structured_error_fallback_response(self, thinker):
        """_build_structured_error использует fallback response."""
        error = thinker._build_structured_error(
            error_type="TEST_ERROR",
            error_message="Test",
            partial_data="",
        )

        assert "Извини" in error["response"] or "не смогла" in error["response"]


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestThinkerIntegration:
    """Интеграционные тесты полного цикла."""

    @pytest.mark.asyncio
    async def test_full_cycle_with_valid_json(self):
        """Полный цикл: stimulus → prompt → LLM → parse → output."""
        from leya_core.llm_backend import LLMBackend
    
        config = ThinkerConfig()
        llm_client = MagicMock(spec=LLMBackend)

        valid_json = json.dumps(
            {
                "response": "Привет! Как дела?",
                "internal_monologue": "Пользователь поздоровался",
                "action_intent": "RESPOND",
                "tool_call": None,
                "self_reflection": "Я ответила на приветствие",
            }
        )
        llm_client.chat = AsyncMock(return_value=valid_json)

        thinker = CoreThinker(config, llm_client)
        result = await thinker.generate_plan(
            stimulus={"type": "USER_MESSAGE", "content": "Привет!"},
            soul_context="Я — Лея",
            drive_context="Любопытство: 0.5",
            memory_context=[],
            tools=[],
        )

        assert result["response"] == "Привет! Как дела?"
        assert result["action_intent"] == "RESPOND"
        llm_client.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_cycle_with_malformed_json(self):
        """Полный цикл с malformed JSON → repair_json → parse."""
        from leya_core.llm_backend import LLMBackend
    
        config = ThinkerConfig()
        llm_client = MagicMock(spec=LLMBackend)

        malformed_json = '```json\n{"response": "test", "internal_monologue": "x", "action_intent": "RESPOND", "tool_call": null, "self_reflection": "y"}\n```'
        llm_client.chat = AsyncMock(return_value=malformed_json)

        thinker = CoreThinker(config, llm_client)
        result = await thinker.generate_plan(
            stimulus={"type": "USER_MESSAGE", "content": "test"},
            soul_context="test",
            drive_context="test",
            memory_context=[],
            tools=[],
        )

        assert result["response"] == "test"
        assert result["action_intent"] == "RESPOND"