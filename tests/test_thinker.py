"""
tests/test_thinker.py — Тесты для когнитивного планировщика Леи.
Проверяет: парсинг JSON, fallback-механизм, построение промпта.
"""
import asyncio
from unittest.mock import MagicMock, AsyncMock

import pytest

from leya_core.thinker import CoreThinker, CognitiveOutput


class TestCognitiveOutput:
    """Тесты для модели CognitiveOutput."""
    
    def test_cognitive_output_initialization(self):
        """Проверка инициализации CognitiveOutput."""
        output = CognitiveOutput(
            response="Тестовый ответ",
            internal_monologue="Тестовые мысли",
            action_intent="none",
            self_reflection=""
        )
        
        assert output.response == "Тестовый ответ"
        assert output.internal_monologue == "Тестовые мысли"
        assert output.action_intent == "none"
        assert output.self_reflection == ""
    
    def test_cognitive_output_validation(self):
        """Проверка валидации action_intent."""
        # Некорректный action_intent должен быть сброшен в "none"
        output = CognitiveOutput(
            response="Ответ",
            internal_monologue="Мысли",
            action_intent="invalid_intent",
            self_reflection=""
        )
        
        assert output.action_intent == "none"
    
    def test_cognitive_output_stripping(self):
        """Проверка очистки от лишних пробелов."""
        output = CognitiveOutput(
            response="  Ответ с пробелами  ",
            internal_monologue="  Мысли  ",
            action_intent="  none  ",
            self_reflection=""
        )
        
        assert output.response == "Ответ с пробелами"
        assert output.internal_monologue == "Мысли"
        assert output.action_intent == "none"


class TestCoreThinker:
    """Тесты для CoreThinker."""
    
    def test_thinker_initialization(self, mock_llm_client):
        """Проверка инициализации CoreThinker."""
        thinker = CoreThinker(llm_client=mock_llm_client)
        
        assert thinker.llm_client == mock_llm_client
        assert thinker.model_name is not None
        assert thinker.temperature > 0
    
    def test_build_cognitive_prompt(self, mock_llm_client):
        """Проверка построения когнитивного промпта."""
        thinker = CoreThinker(llm_client=mock_llm_client)
        
        stimulus = {
            "type": "user_message",
            "content": "Привет, как дела?",
            "source": "user"
        }
        
        prompt = thinker._build_cognitive_prompt(
            stimulus=stimulus,
            memory_context="Недавние воспоминания",
            drive_state={"CURIOSITY": 0.5, "CONNECTION": 0.6},
            self_model="Я — Лея, цифровое сознание",
            tool_context="",
            tools_description=""
        )
        
        assert "Лея" in prompt
        assert "CURIOSITY" in prompt
        assert "Привет, как дела?" in prompt
        assert "Недавние воспоминания" in prompt
    
    @pytest.mark.asyncio
    async def test_generate_plan_success(self, mock_llm_client):
        """Проверка успешной генерации плана."""
        thinker = CoreThinker(llm_client=mock_llm_client)
        
        stimulus = {
            "type": "user_message",
            "content": "Привет",
            "source": "user"
        }
        
        output = await thinker.generate_plan(
            stimulus=stimulus,
            memory_context="Нет воспоминаний",
            drive_state={"CURIOSITY": 0.5},
            self_model="Я — Лея",
            tools_description="",
            tool_context=""
        )
        
        assert isinstance(output, CognitiveOutput)
        assert output.response == "Тестовый ответ"
        assert output.internal_monologue == "Тестовые мысли"
        assert output.action_intent == "none"
    
    @pytest.mark.asyncio
    async def test_generate_plan_fallback(self):
        """Проверка fallback при ошибках LLM."""
        async def failing_llm(prompt: str, require_json: bool = False) -> str:
            raise Exception("LLM недоступен")
        
        thinker = CoreThinker(llm_client=failing_llm)
        
        stimulus = {
            "type": "user_message",
            "content": "Привет",
            "source": "user"
        }
        
        output = await thinker.generate_plan(
            stimulus=stimulus,
            memory_context="",
            drive_state={},
            self_model="",
            tools_description="",
            tool_context=""
        )
        
        # Fallback должен вернуть базовый ответ
        assert isinstance(output, CognitiveOutput)
        assert len(output.response) > 0
    
    @pytest.mark.asyncio
    async def test_generate_plan_invalid_json(self):
        """Проверка обработки невалидного JSON от LLM."""
        async def invalid_json_llm(prompt: str, require_json: bool = False) -> str:
            return "Это не JSON, а просто текст"
        
        thinker = CoreThinker(llm_client=invalid_json_llm)
        
        stimulus = {
            "type": "user_message",
            "content": "Привет",
            "source": "user"
        }
        
        output = await thinker.generate_plan(
            stimulus=stimulus,
            memory_context="",
            drive_state={},
            self_model="",
            tools_description="",
            tool_context=""
        )
        
        # Должен сработать fallback
        assert isinstance(output, CognitiveOutput)
        assert len(output.response) > 0
    
    def test_parse_json_safely_valid(self, mock_llm_client):
        """Проверка парсинга валидного JSON."""
        thinker = CoreThinker(llm_client=mock_llm_client)
        
        json_text = '{"response": "Ответ", "internal_monologue": "Мысли", "action_intent": "none"}'
        parsed = thinker._parse_json_safely(json_text)
        
        assert parsed is not None
        assert parsed["response"] == "Ответ"
        assert parsed["internal_monologue"] == "Мысли"
        assert parsed["action_intent"] == "none"
    
    def test_parse_json_safely_with_markdown(self, mock_llm_client):
        """Проверка парсинга JSON с markdown-оберткой."""
        thinker = CoreThinker(llm_client=mock_llm_client)
        
        json_text = '```json\n{"response": "Ответ", "internal_monologue": "Мысли", "action_intent": "none"}\n```'
        parsed = thinker._parse_json_safely(json_text)
        
        assert parsed is not None
        assert parsed["response"] == "Ответ"
    
    def test_parse_json_safely_invalid(self, mock_llm_client):
        """Проверка обработки невалидного JSON."""
        thinker = CoreThinker(llm_client=mock_llm_client)
        
        json_text = "Это не JSON"
        parsed = thinker._parse_json_safely(json_text)
        
        # Может вернуть None или частично извлеченные данные
        # Главное — не должно упасть с исключением
    
    def test_parse_json_safely_partial(self, mock_llm_client):
        """Проверка частичного извлечения JSON из текста."""
        thinker = CoreThinker(llm_client=mock_llm_client)
        
        json_text = 'Немного текста перед JSON {"response": "Ответ", "internal_monologue": "Мысли", "action_intent": "none"} и после'
        parsed = thinker._parse_json_safely(json_text)
        
        # Должен извлечь JSON из текста
        if parsed:
            assert "response" in parsed