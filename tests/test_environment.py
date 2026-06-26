"""
Тесты для environment.py.

Покрытие целевое: 35% → 70%

Проверяет:
- Tool dataclass
- ToolRegistry (регистрация, выполнение, ошибки)
- SoulFileManager (read, write, list)
- CLIEnvironment (listen, send_message)
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from leya_core.environment import (
    CLIEnvironment,
    Environment,
    SoulFileManager,
    Tool,
    ToolRegistry,
)
from leya_core.exceptions import (
    LeyaSoulError,
    LeyaToolError,
    LeyaToolExecutionError,
    LeyaToolNotFoundError,
)


# ============================================================================
# Тесты Tool dataclass
# ============================================================================


class TestToolDataclass:
    """Тесты модели Tool."""

    def test_tool_creation(self):
        """Tool корректно создаётся."""
        async def handler():
            return "result"

        tool = Tool(
            name="test_tool",
            description="Тестовый инструмент",
            handler=handler,
            parameters={"param1": "str"},
            category="test",
        )

        assert tool.name == "test_tool"
        assert tool.description == "Тестовый инструмент"
        assert tool.category == "test"


# ============================================================================
# Тесты ToolRegistry
# ============================================================================


class TestToolRegistry:
    """Тесты реестра инструментов."""

    def test_register_tool(self):
        """Инструмент регистрируется."""
        registry = ToolRegistry()

        async def handler():
            return "result"

        tool = Tool(name="test", description="test", handler=handler)
        registry.register(tool)

        assert "test" in registry.tools

    def test_register_invalid_tool(self):
        """Невалидный инструмент не регистрируется."""
        registry = ToolRegistry()

        tool = Tool(name="", description="", handler=None)

        with pytest.raises(LeyaToolError):
            registry.register(tool)

    def test_get_tool(self):
        """get_tool возвращает инструмент."""
        registry = ToolRegistry()

        async def handler():
            return "result"

        tool = Tool(name="test", description="test", handler=handler)
        registry.register(tool)

        retrieved = registry.get_tool("test")
        assert retrieved is tool

    def test_get_tool_not_found(self):
        """get_tool возвращает None для несуществующего."""
        registry = ToolRegistry()
        assert registry.get_tool("nonexistent") is None

    def test_get_all_descriptions(self):
        """get_all_descriptions возвращает непустую строку."""
        registry = ToolRegistry()
        descriptions = registry.get_all_descriptions()

        assert isinstance(descriptions, str)
        assert len(descriptions) > 0
        assert "ИНСТРУМЕНТ" in descriptions or "инструмент" in descriptions.lower()

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        """execute выполняет инструмент."""
        registry = ToolRegistry()

        async def handler(param1: str = "default"):
            return f"result: {param1}"

        tool = Tool(name="test", description="test", handler=handler)
        registry.register(tool)

        result = await registry.execute("test", {"param1": "value"})
        assert result == "result: value"

    @pytest.mark.asyncio
    async def test_execute_not_found(self):
        """execute бросает LeyaToolNotFoundError."""
        registry = ToolRegistry()

        with pytest.raises(LeyaToolNotFoundError):
            await registry.execute("nonexistent", {})

    @pytest.mark.asyncio
    async def test_execute_handler_error(self):
        """execute обрабатывает ошибку handler'а."""
        registry = ToolRegistry()

        async def failing_handler():
            raise ValueError("Ошибка")

        tool = Tool(name="failing", description="failing", handler=failing_handler)
        registry.register(tool)

        with pytest.raises(LeyaToolExecutionError):
            await registry.execute("failing", {})

    @pytest.mark.asyncio
    async def test_builtin_tools_registered(self):
        """Встроенные инструменты зарегистрированы."""
        registry = ToolRegistry()

        assert "wikipedia_search" in registry.tools
        assert "duckduckgo_search" in registry.tools
        assert "execute_python" in registry.tools
        assert "read_soul_file" in registry.tools
        assert "write_soul_file" in registry.tools
        assert "list_soul_files" in registry.tools


# ============================================================================
# Тесты SoulFileManager
# ============================================================================


class TestSoulFileManager:
    """Тесты менеджера файлов души."""

    def test_init_creates_directory(self, tmp_path):
        """SoulFileManager создаёт директорию."""
        soul_dir = tmp_path / "leya_soul"
        manager = SoulFileManager(soul_dir=str(soul_dir))

        assert soul_dir.exists()

    def test_init_creates_default_files(self, tmp_path):
        """SoulFileManager создаёт файлы по умолчанию."""
        soul_dir = tmp_path / "leya_soul"
        manager = SoulFileManager(soul_dir=str(soul_dir))

        assert (soul_dir / "personality.txt").exists()
        assert (soul_dir / "rules.txt").exists()
        assert (soul_dir / "values.txt").exists()

    def test_read_file(self, tmp_path):
        """read_file возвращает содержимое."""
        soul_dir = tmp_path / "leya_soul"
        manager = SoulFileManager(soul_dir=str(soul_dir))

        content = manager.read_file("personality.txt")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_read_file_invalid(self, tmp_path):
        """read_file бросает LeyaSoulError для неизвестного файла."""
        soul_dir = tmp_path / "leya_soul"
        manager = SoulFileManager(soul_dir=str(soul_dir))

        with pytest.raises(LeyaSoulError):
            manager.read_file("nonexistent.txt")

    def test_write_file(self, tmp_path):
        """write_file записывает содержимое."""
        soul_dir = tmp_path / "leya_soul"
        manager = SoulFileManager(soul_dir=str(soul_dir))

        new_content = "Новая личность Леи"
        result = manager.write_file("personality.txt", new_content)

        assert "✅" in result
        assert manager.read_file("personality.txt") == new_content

    def test_write_file_invalid(self, tmp_path):
        """write_file бросает LeyaSoulError для неизвестного файла."""
        soul_dir = tmp_path / "leya_soul"
        manager = SoulFileManager(soul_dir=str(soul_dir))

        with pytest.raises(LeyaSoulError):
            manager.write_file("nonexistent.txt", "content")

    def test_list_files(self, tmp_path):
        """list_files возвращает список файлов."""
        soul_dir = tmp_path / "leya_soul"
        manager = SoulFileManager(soul_dir=str(soul_dir))

        files = manager.list_files()

        assert isinstance(files, list)
        assert "personality.txt" in files
        assert "rules.txt" in files
        assert "values.txt" in files

    def test_get_all_contents(self, tmp_path):
        """get_all_contents возвращает dict содержимого."""
        soul_dir = tmp_path / "leya_soul"
        manager = SoulFileManager(soul_dir=str(soul_dir))

        contents = manager.get_all_contents()

        assert isinstance(contents, dict)
        assert "personality.txt" in contents
        assert "rules.txt" in contents
        assert "values.txt" in contents

    def test_caching(self, tmp_path):
        """read_file кэширует содержимое."""
        soul_dir = tmp_path / "leya_soul"
        manager = SoulFileManager(soul_dir=str(soul_dir))

        # Первый вызов
        content1 = manager.read_file("personality.txt")
        # Второй вызов (должен быть из кэша)
        content2 = manager.read_file("personality.txt")

        assert content1 == content2


# ============================================================================
# Тесты Environment.execute_tool_call
# ============================================================================


class TestEnvironmentExecuteToolCall:
    """Тесты выполнения tool_call через Environment."""

    @pytest.mark.asyncio
    async def test_execute_tool_call_dict(self, tmp_path):
        """execute_tool_call принимает dict."""
        mock_leya = MagicMock()
        env = CLIEnvironment(leya_os=mock_leya)

        # Регистрируем тестовый инструмент
        async def handler(param1: str = "default"):
            return f"result: {param1}"

        tool = Tool(name="test", description="test", handler=handler)
        env.tool_registry.register(tool)

        result = await env.execute_tool_call({
            "tool": "test",
            "parameters": {"param1": "value"},
        })

        assert result == "result: value"

    # tests/test_environment.py, строка ~308

    @pytest.mark.asyncio
    async def test_execute_tool_call_json_string(self, tmp_path):
        """execute_tool_call принимает JSON-строку."""
        mock_leya = MagicMock()
        env = CLIEnvironment(leya_os=mock_leya)

        async def handler():
            return "result"

        tool = Tool(name="test", description="test", handler=handler)
        env.tool_registry.register(tool)

        # Передаём параметры напрямую (без обёртки "parameters")
        import json
        json_payload = json.dumps({"tool": "test"})
        result = await env.execute_tool_call(json_payload)
        assert result == "result"

    @pytest.mark.asyncio
    async def test_execute_tool_call_invalid_json(self, tmp_path):
        """execute_tool_call бросает LeyaToolError на невалидный JSON."""
        mock_leya = MagicMock()
        env = CLIEnvironment(leya_os=mock_leya)

        with pytest.raises(LeyaToolError):
            await env.execute_tool_call("invalid json")

    @pytest.mark.asyncio
    async def test_execute_tool_call_missing_tool(self, tmp_path):
        """execute_tool_call бросает LeyaToolNotFoundError."""
        mock_leya = MagicMock()
        env = CLIEnvironment(leya_os=mock_leya)

        with pytest.raises(LeyaToolNotFoundError):
            await env.execute_tool_call({"parameters": {}})


# ============================================================================
# Тесты CLIEnvironment
# ============================================================================


class TestCLIEnvironment:
    """Тесты CLI-окружения."""

    @pytest.mark.asyncio
    async def test_send_message(self, capsys):
        """send_message выводит сообщение."""
        mock_leya = MagicMock()
        env = CLIEnvironment(leya_os=mock_leya)

        await env.send_message("Привет!")

        captured = capsys.readouterr()
        assert "Привет!" in captured.out

    @pytest.mark.asyncio
    async def test_listen_empty_queue(self):
        """listen возвращает None при пустой очереди."""
        mock_leya = MagicMock()
        env = CLIEnvironment(leya_os=mock_leya)

        # Не запускаем listener, чтобы не блокировать stdin
        result = await env.listen()

        # Должен вернуть None (очередь пуста)
        assert result is None

    @pytest.mark.asyncio
    async def test_listen_with_message(self):
        """listen возвращает сообщение из очереди."""
        mock_leya = MagicMock()
        env = CLIEnvironment(leya_os=mock_leya)

        # Добавляем сообщение в очередь
        await env.input_queue.put({
            "type": "user_message",
            "content": "Привет!",
            "source": "cli",
        })

        result = await env.listen()

        assert result is not None
        assert result["content"] == "Привет!"