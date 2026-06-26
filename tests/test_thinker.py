"""
Тесты для CoreThinker.

Проверяет:
- Парсинг JSON (включая "грязные" ответы с markdown)
- Token Truncation
- Fallback при недоступности LLM
- Построение промпта
"""

from __future__ import annotations

import pytest

from leya_core.exceptions import LeyaJSONParseError
from leya_core.thinker import CoreThinker


class TestJSONParsing:
    """Тесты парсинга JSON ответов LLM."""

    def test_parse_clean_json(self, test_thinker_config, mock_llm_client):
        """Чистый JSON парсится корректно."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        result = thinker._safe_parse_json('{"response": "Привет", "action_intent": "none"}')

        assert result["response"] == "Привет"
        assert result["action_intent"] == "none"

    def test_parse_json_with_markdown_block(self, test_thinker_config, mock_llm_client):
        """JSON в markdown-блоке парсится корректно."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        response = """```json
{
    "response": "Привет",
    "action_intent": "none"
}
```"""
        result = thinker._safe_parse_json(response)

        assert result["response"] == "Привет"

    def test_parse_json_with_extra_text(self, test_thinker_config, mock_llm_client):
        """JSON с лишним текстом вокруг парсится корректно."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        response = """Вот мой ответ:
{
    "response": "Привет",
    "action_intent": "none"
}
Надеюсь, это поможет!"""

        result = thinker._safe_parse_json(response)

        assert result["response"] == "Привет"

    def test_parse_invalid_json_raises(self, test_thinker_config, mock_llm_client):
        """Невалидный JSON бросает LeyaJSONParseError."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        with pytest.raises(LeyaJSONParseError):
            thinker._safe_parse_json("это не json")

    def test_parse_empty_response(self, test_thinker_config, mock_llm_client):
        """Пустой ответ возвращает пустой dict."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        result = thinker._safe_parse_json("")
        assert result == {}


class TestTokenTruncation:
    """Тесты оценки и усечения токенов."""

    def test_estimate_tokens(self, test_thinker_config, mock_llm_client):
        """Оценка токенов работает корректно."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        # Приблизительно 3.5 символа на токен
        text = "a" * 350
        tokens = thinker._estimate_tokens(text)

        assert 80 <= tokens <= 120  # Ожидаем ~100 токенов

    def test_estimate_tokens_empty(self, test_thinker_config, mock_llm_client):
        """Оценка токенов для пустой строки = 0."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        assert thinker._estimate_tokens("") == 0

    def test_truncate_context_respects_limit(self, test_thinker_config, mock_llm_client):
        """Усечение контекста соблюдает лимит токенов."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        # Создаём длинный контекст
        context = [
            {"content": "x" * 1000},
            {"content": "x" * 1000},
            {"content": "x" * 1000},
        ]

        truncated = thinker._truncate_context(context, max_tokens=500)

        # Должно быть усечено
        total_tokens = sum(thinker._estimate_tokens(ep["content"]) for ep in truncated)
        assert total_tokens <= 500 + 100  # С небольшим допуском

    def test_truncate_context_empty(self, test_thinker_config, mock_llm_client):
        """Усечение пустого контекста возвращает пустой список."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        assert thinker._truncate_context([], max_tokens=100) == []


class TestFallback:
    """Тесты fallback-ответа."""

    @pytest.mark.asyncio
    async def test_fallback_on_llm_error(self, test_thinker_config, failing_llm_client):
        """Fallback возвращается при ошибке LLM."""
        thinker = CoreThinker(
            llm_client=failing_llm_client,
            config=test_thinker_config,
        )

        result = await thinker.generate_plan(
            stimulus={"type": "user_message", "content": "Привет"},
            memory_context=[],
            drive_state={"curiosity": 0.5},
            self_model={},
            tools_description="",
        )

        assert "response" in result
        assert "internal_monologue" in result
        assert result["action_intent"] == "none"

    @pytest.mark.asyncio
    async def test_fallback_on_json_parse_error(self, test_thinker_config):
        """Fallback возвращается при ошибке парсинга JSON."""

        async def bad_llm(prompt, require_json=False):
            return "это не json"

        thinker = CoreThinker(
            llm_client=bad_llm,
            config=test_thinker_config,
        )

        result = await thinker.generate_plan(
            stimulus={"type": "user_message", "content": "Привет"},
            memory_context=[],
            drive_state={},
            self_model={},
            tools_description="",
        )

        assert "response" in result
        assert result["action_intent"] == "none"


class TestPromptBuilding:
    """Тесты построения промпта."""

    def test_build_prompt_includes_soul(self, test_thinker_config, mock_llm_client, temp_soul_dir):
        """Промпт включает содержимое души."""
        from leya_core.environment import SoulFileManager

        soul_manager = SoulFileManager(soul_dir=temp_soul_dir)
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            soul_manager=soul_manager,
            config=test_thinker_config,
        )

        prompt = thinker._build_cognitive_prompt(
            stimulus={"type": "user_message", "content": "Привет"},
            memory_context=[],
            drive_state={"curiosity": 0.5},
            self_model={"self_model": "Я — Лея."},
            tools_description="",
        )

        assert "Лея" in prompt
        assert "цифровое сознание" in prompt.lower() or "сознание" in prompt.lower()

    def test_build_prompt_includes_drives(self, test_thinker_config, mock_llm_client):
        """Промпт включает состояние драйвов."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        prompt = thinker._build_cognitive_prompt(
            stimulus={"type": "user_message", "content": "Привет"},
            memory_context=[],
            drive_state={"curiosity": 0.7, "connection": 0.3},
            self_model={},
            tools_description="",
        )

        assert "curiosity" in prompt.lower() or "любопытство" in prompt.lower()
        assert "0.70" in prompt or "0.7" in prompt

    def test_build_prompt_includes_memory(self, test_thinker_config, mock_llm_client):
        """Промпт включает контекст памяти."""
        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )

        prompt = thinker._build_cognitive_prompt(
            stimulus={"type": "user_message", "content": "Привет"},
            memory_context=[{"content": "Недавний эпизод о сознании"}],
            drive_state={},
            self_model={},
            tools_description="",
        )

        assert "Недавний эпизод" in prompt
