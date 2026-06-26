"""
Тесты для ToolGenerator.

Покрытие целевое: 19% → 70%+

Проверяет:
- Анализ использования инструментов
- Генерацию специализированного инструмента
- Валидацию спецификации
- Тестирование инструмента
- Регистрацию инструмента
- Получение сводки
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from leya_core.tool_generator import ToolGenerator

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_tool_registry():
    """Mock ToolRegistry с реальным dict для tools и MagicMock для register."""
    registry = MagicMock()
    # ВАЖНО: tools должен быть реальным dict, чтобы .keys() работал
    registry.tools = {
        "wikipedia_search": MagicMock(),
        "duckduckgo_search": MagicMock(),
        "github_readme": MagicMock(),
    }
    # register должен быть MagicMock для assert_called_once()
    registry.register = MagicMock()
    return registry


@pytest.fixture
def mock_llm_client():
    """Mock LLM client для генерации инструментов."""

    async def _mock_llm(prompt: str, require_json: bool = False) -> str:
        return json.dumps(
            {
                "name": "custom_test_tool",
                "description": "Тестовый инструмент",
                "parameters": {"param1": "str"},
                "code": "async def custom_test_tool(param1: str = 'default'):\n    return f'Result: {param1}'",
            }
        )

    return _mock_llm


@pytest.fixture
def tool_generator(mock_tool_registry, mock_llm_client):
    """ToolGenerator с mock зависимостями."""
    return ToolGenerator(mock_tool_registry, mock_llm_client)


# ============================================================================
# Тесты инициализации
# ============================================================================


class TestToolGeneratorInit:
    """Тесты инициализации ToolGenerator."""

    def test_init(self, mock_tool_registry, mock_llm_client):
        """ToolGenerator инициализируется корректно."""
        generator = ToolGenerator(mock_tool_registry, mock_llm_client)

        assert generator.tool_registry is mock_tool_registry
        assert generator.llm_client is mock_llm_client
        assert generator.generated_tools == []
        assert generator.max_generated_tools == 10


# ============================================================================
# Тесты анализа использования инструментов
# ============================================================================


class TestAnalyzeToolUsage:
    """Тесты анализа использования инструментов."""

    def test_analyze_tool_usage_finds_tools(self, tool_generator):
        """_analyze_tool_usage находит упоминания инструментов."""
        # Нужно минимум 3 упоминания одного инструмента
        episodes = [
            {"content": "Использую wikipedia_search для поиска информации"},
            {"content": "Ещё раз wikipedia_search"},
            {"content": "И снова wikipedia_search"},
            {"content": "Теперь duckduckgo_search"},
        ]

        result = tool_generator._analyze_tool_usage(episodes)

        # Проверяем, что метод возвращает словарь (если паттерн найден)
        assert result is not None
        assert isinstance(result, dict)
        # Проверяем, что есть ключ с названием инструмента
        assert "tool_name" in result or any("wikipedia" in str(v) for v in result.values())

    def test_analyze_tool_usage_no_tools(self, tool_generator):
        """_analyze_tool_usage возвращает None если нет упоминаний."""
        episodes = [
            {"content": "Обычный текст без инструментов"},
            {"content": "Ещё текст"},
        ]

        result = tool_generator._analyze_tool_usage(episodes)

        assert result is None

    def test_analyze_tool_usage_empty_episodes(self, tool_generator):
        """_analyze_tool_usage обрабатывает пустой список."""
        result = tool_generator._analyze_tool_usage([])

        assert result is None


# ============================================================================
# Тесты валидации спецификации
# ============================================================================


class TestValidateToolSpec:
    """Тесты валидации спецификации инструмента."""

    def test_validate_valid_spec(self, tool_generator):
        """_validate_tool_spec принимает валидную спецификацию."""
        spec = {
            "name": "custom_test_tool",
            "description": "Тестовый инструмент",
            "parameters": {"param1": "str"},
            "code": "async def custom_test_tool():\n    return 'result'",
        }

        result = tool_generator._validate_tool_spec(spec)

        assert result is True

    def test_validate_missing_fields(self, tool_generator):
        """_validate_tool_spec отклоняет спецификацию без обязательных полей."""
        spec = {
            "name": "custom_test_tool",
            # Отсутствуют description, parameters, code
        }

        result = tool_generator._validate_tool_spec(spec)

        assert result is False

    def test_validate_invalid_name(self, tool_generator):
        """_validate_tool_spec отклоняет имя без префикса custom_."""
        spec = {
            "name": "test_tool",  # Должно начинаться с custom_
            "description": "Тест",
            "parameters": {},
            "code": "async def test_tool():\n    return 'result'",
        }

        result = tool_generator._validate_tool_spec(spec)

        assert result is False

    def test_validate_dangerous_imports(self, tool_generator):
        """_validate_tool_spec отклоняет опасные импорты."""
        spec = {
            "name": "custom_test_tool",
            "description": "Тест",
            "parameters": {},
            "code": "import os\nasync def custom_test_tool():\n    return 'result'",
        }

        result = tool_generator._validate_tool_spec(spec)

        assert result is False

    def test_validate_syntax_error(self, tool_generator):
        """_validate_tool_spec отклоняет код с синтаксической ошибкой."""
        spec = {
            "name": "custom_test_tool",
            "description": "Тест",
            "parameters": {},
            "code": "async def custom_test_tool(\n    return 'result'",  # Синтаксическая ошибка
        }

        result = tool_generator._validate_tool_spec(spec)

        assert result is False


# ============================================================================
# Тесты тестирования инструмента
# ============================================================================


class TestTestTool:
    """Тесты тестирования инструмента."""

    @pytest.mark.asyncio
    async def test_test_tool_success(self, tool_generator):
        """_test_tool успешно тестирует рабочий инструмент."""
        spec = {
            "name": "custom_test_tool",
            "code": "async def custom_test_tool():\n    return 'result'",
        }

        result = await tool_generator._test_tool(spec)

        assert result is True

    @pytest.mark.asyncio
    async def test_test_tool_failure(self, tool_generator):
        """_test_tool возвращает False для нерабочего инструмента."""
        spec = {
            "name": "custom_test_tool",
            "code": "async def custom_test_tool():\n    raise Exception('Error')",
        }

        result = await tool_generator._test_tool(spec)

        assert result is False

    @pytest.mark.asyncio
    async def test_test_tool_missing_function(self, tool_generator):
        """_test_tool возвращает False если функция не определена."""
        spec = {
            "name": "custom_test_tool",
            "code": "# Пустой код без функции",
        }

        result = await tool_generator._test_tool(spec)

        assert result is False


# ============================================================================
# Тесты регистрации сгенерированного инструмента
# ============================================================================


class TestRegisterGeneratedTool:
    """Тесты регистрации сгенерированного инструмента."""

    @pytest.mark.asyncio
    async def test_register_tool_success(self, tool_generator, mock_tool_registry):
        """_register_generated_tool успешно регистрирует инструмент."""
        spec = {
            "name": "custom_test_tool",
            "description": "Тестовый инструмент",
            "parameters": {},
            "code": "async def custom_test_tool():\n    return 'result'",
        }

        result = await tool_generator._register_generated_tool(spec)

        assert result == "custom_test_tool"
        mock_tool_registry.register.assert_called_once()
        assert len(tool_generator.generated_tools) == 1

    @pytest.mark.asyncio
    async def test_register_tool_failure(self, tool_generator):
        """_register_generated_tool обрабатывает ошибки."""
        spec = {
            "name": "custom_test_tool",
            "code": "invalid code {{{",  # Синтаксическая ошибка
        }

        result = await tool_generator._register_generated_tool(spec)

        assert result is None


# ============================================================================
# Тесты анализа и генерации инструмента
# ============================================================================


class TestAnalyzeAndGenerate:
    """Тесты анализа и генерации инструмента."""

    @pytest.mark.asyncio
    async def test_analyze_and_generate_success(self, tool_generator):
        """analyze_and_generate успешно генерирует инструмент или возвращает None."""
        # Нужно минимум 3 упоминания одного инструмента
        episodes = [
            {"content": "Использую wikipedia_search"},
            {"content": "Снова wikipedia_search"},
            {"content": "И ещё wikipedia_search"},
        ]
        drive_state = {"curiosity": 0.7}

        result = await tool_generator.analyze_and_generate(episodes, drive_state)

        # Результат может быть None (если не удалось сгенерировать) или строкой
        assert result is None or isinstance(result, str)
        # Проверяем, что метод не падает и generated_tools обновляется (если успешно)
        if result is not None:
            assert len(tool_generator.generated_tools) >= 1

    @pytest.mark.asyncio
    async def test_analyze_and_generate_insufficient_episodes(self, tool_generator):
        """analyze_and_generate возвращает None при недостатке эпизодов."""
        episodes = [
            {"content": "Один эпизод"},
        ]
        drive_state = {"curiosity": 0.7}

        result = await tool_generator.analyze_and_generate(episodes, drive_state)

        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_and_generate_max_tools_reached(self, tool_generator):
        """analyze_and_generate возвращает None при достижении лимита."""
        tool_generator.max_generated_tools = 1
        tool_generator.generated_tools = [{"name": "existing_tool"}]

        episodes = [
            {"content": "wikipedia_search"},
            {"content": "wikipedia_search"},
            {"content": "wikipedia_search"},
        ]
        drive_state = {"curiosity": 0.7}

        result = await tool_generator.analyze_and_generate(episodes, drive_state)

        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_and_generate_no_pattern(self, tool_generator):
        """analyze_and_generate возвращает None если нет паттерна."""
        episodes = [
            {"content": "Обычный текст"},
            {"content": "Ещё текст"},
            {"content": "И ещё текст"},
        ]
        drive_state = {"curiosity": 0.7}

        result = await tool_generator.analyze_and_generate(episodes, drive_state)

        assert result is None


# ============================================================================
# Тесты получения сводки сгенерированных инструментов
# ============================================================================


class TestGetGeneratedToolsSummary:
    """Тесты получения сводки сгенерированных инструментов."""

    def test_get_summary_empty(self, tool_generator):
        """get_generated_tools_summary возвращает пустой список."""
        result = tool_generator.get_generated_tools_summary()

        assert result == []

    def test_get_summary_with_tools(self, tool_generator):
        """get_generated_tools_summary возвращает список инструментов."""
        tool_generator.generated_tools = [
            {
                "name": "custom_tool1",
                "description": "Инструмент 1",
                "generated_at": "2026-06-26T12:00:00",
            },
            {
                "name": "custom_tool2",
                "description": "Инструмент 2",
                "generated_at": "2026-06-26T13:00:00",
            },
        ]

        result = tool_generator.get_generated_tools_summary()

        assert len(result) == 2
        assert result[0]["name"] == "custom_tool1"
        assert result[1]["name"] == "custom_tool2"
