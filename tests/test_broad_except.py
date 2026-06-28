"""Тесты задачи 1.3: замена broad except Exception на конкретные исключения.

Проверяем, что:
- memory._save_state превращает OSError/json/HMAC ошибки в LeyaAtomicWriteError
- llm_client.chat превращает aiohttp/timeout/json ошибки в LeyaLLMConnectionError/
  LeyaLLMTimeoutError/LeyaJSONParseError
- shutdown в LeyaOS не проглатывает ошибки молча, а логирует с контекстом
"""

import asyncio
import json
import os
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from LeyaOS import LeyaOS 
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from leya_core.exceptions import (
    LeyaAtomicWriteError,
    LeyaLLMConnectionError,
    LeyaLLMTimeoutError,
    LeyaJSONParseError,
    LeyaLLMError,
)


# =================================================================================
# MEMORY._save_state
# =================================================================================

class TestMemorySaveState:
    """Проверяем, что _save_state бросает LeyaAtomicWriteError на конкретных ошибках."""

    @pytest.fixture
    def memory_instance(self):
        """Создаёт минимальный mock памяти с нужными атрибутами для _save_state."""
        from leya_core.memory import MemorySystem
        from leya_core.config import MemoryConfig

        # Создаём объект без вызова __init__ (чтобы не трогать Chroma и т.д.)
        mem = MemorySystem.__new__(MemorySystem)
        mem.config = MemoryConfig()
        mem.engrams = {}
        mem.synapses = {}
        mem.self_model = "test self model"
        mem._state_version = 3
        return mem

    @pytest.mark.asyncio
    async def test_oserror_on_mkstemp_raises_atomic_write_error(self, memory_instance, tmp_path):
        """Если tempfile.mkstemp падает с OSError → LeyaAtomicWriteError."""
        memory_instance.config.brain_dir = str(tmp_path)
        with patch("tempfile.mkstemp", side_effect=OSError(28, "No space left on device")):
            with pytest.raises(LeyaAtomicWriteError) as exc_info:
                await memory_instance._save_state()
            assert "No space left" in str(exc_info.value) or "tempfile" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_oserror_on_replace_raises_atomic_write_error(self, memory_instance, tmp_path):
        """Если os.replace падает (например, cross-device) → LeyaAtomicWriteError."""
        memory_instance.config.brain_dir = str(tmp_path)
        with patch("os.replace", side_effect=OSError("cross-device link")):
            with pytest.raises(LeyaAtomicWriteError):
                await memory_instance._save_state()

    @pytest.mark.asyncio
    async def test_typeerror_on_json_dump_raises_atomic_write_error(self, memory_instance, tmp_path):
        """Если json.dump не может сериализовать (TypeError) → LeyaAtomicWriteError."""
        memory_instance.config.brain_dir = str(tmp_path)
        # Неподдерживаемый тип в engrams
        memory_instance.engrams = {"bad": object()}

        with pytest.raises(LeyaAtomicWriteError):
            await memory_instance._save_state()

    @pytest.mark.asyncio
    async def test_oserror_on_hmac_write_raises_atomic_write_error(self, memory_instance, tmp_path):
        """Если запись .hmac файла падает → LeyaAtomicWriteError."""
        memory_instance.config.brain_dir = str(tmp_path)
        memory_instance.config.hmac_key = "test_key"

        # Разрешаем tempfile и json, но ломаем запись hmac
        original_open = open
        call_count = {"n": 0}

        def fake_open(path, *args, **kwargs):
            call_count["n"] += 1
            # Первый open — json, второй — hmac. Ломаем второй.
            if str(path).endswith(".hmac"):
                raise OSError("Permission denied")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=fake_open):
            with pytest.raises(LeyaAtomicWriteError):
                await memory_instance._save_state()

    @pytest.mark.asyncio
    async def test_success_does_not_raise(self, memory_instance, tmp_path):
        """Успешный путь не должен бросать исключений."""
        memory_instance.config.brain_dir = str(tmp_path)
        memory_instance.config.hmac_key = "test_key"
        # Не должно упасть
        await memory_instance._save_state()
        assert (tmp_path / "memory_state.json").exists()
        assert (tmp_path / "memory_state.json.hmac").exists()


# =================================================================================
# LLM_CLIENT.chat
# =================================================================================

class TestLLMClientChat:
    """Проверяем, что chat превращает низкоуровневые ошибки в LeyaLLM*."""

    @pytest.fixture
    def client(self):
        from leya_core.llm_client import OllamaClient
        from leya_core.config import OllamaConfig
    
        cfg = OllamaConfig()
    
        # Создаём OllamaClient с отдельными параметрами (как в LeyaOS.py)
        c = OllamaClient(
            base_url=cfg.base_url,
            model=cfg.model,
            timeout=cfg.timeout,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            top_k=cfg.top_k,
            max_tokens=cfg.max_tokens,
            repeat_penalty=cfg.repeat_penalty,
        )
    
        # Мокаем сессию и breaker
        c._session = AsyncMock()
        c._breaker = MagicMock()
        c._breaker.is_available.return_value = True
        c._breaker.record_success = MagicMock()
        c._breaker.record_failure = MagicMock()
    
        return c

    @pytest.mark.asyncio
    async def test_aiohttp_client_error_raises_connection_error(self, client):
        """aiohttp.ClientError → LeyaLLMConnectionError."""
        import aiohttp
        mock_resp = AsyncMock()
        mock_resp.__aenter__.return_value = MagicMock()
        mock_resp.__aenter__.return_value.status = 200
        mock_resp.__aenter__.return_value.json = AsyncMock(
            side_effect=aiohttp.ClientConnectionError("connection refused")
        )
        client._session.post.return_value = mock_resp

        with pytest.raises(LeyaLLMConnectionError):
            await client.chat("hi")

    @pytest.mark.asyncio
    async def test_timeout_error_raises_timeout(self, client):
        """asyncio.TimeoutError → LeyaLLMTimeoutError."""
        client._session.post.side_effect = asyncio.TimeoutError()

        with pytest.raises(LeyaLLMTimeoutError):
            await client.chat("hi")

    @pytest.mark.asyncio
    async def test_invalid_json_response_raises_parse_error(self, client):
        """Невалидный JSON от сервера → LeyaJSONParseError."""
        mock_resp = AsyncMock()
        mock_resp.__aenter__.return_value = MagicMock()
        mock_resp.__aenter__.return_value.status = 200
        mock_resp.__aenter__.return_value.text = AsyncMock(return_value="{not valid json")
        client._session.post.return_value = mock_resp

        # require_json=True заставляет парсить как JSON
        with pytest.raises((LeyaJSONParseError, LeyaLLMError)):
            await client.chat("hi", require_json=True)

    @pytest.mark.asyncio
    async def test_http_error_status_raises_llm_error(self, client):
        """HTTP 500 → LeyaLLMError (не Connection, не Timeout)."""
        mock_resp = AsyncMock()
        mock_resp.__aenter__.return_value = MagicMock()
        mock_resp.__aenter__.return_value.status = 500
        mock_resp.__aenter__.return_value.text = AsyncMock(return_value="Internal Server Error")
        client._session.post.return_value = mock_resp

        with pytest.raises(LeyaLLMError):
            await client.chat("hi")

    @pytest.mark.asyncio
    async def test_unexpected_exception_wrapped_as_llm_error(self, client):
        """Неожиданное исключение оборачивается в LeyaLLMError с сохранением оригинала."""
        client._session.post.side_effect = RuntimeError("weird internal bug")

        with pytest.raises(LeyaLLMError) as exc_info:
            await client.chat("hi")
        # Оригинал должен быть сохранён как __cause__
        assert isinstance(exc_info.value.__cause__, RuntimeError)


# =================================================================================
# LEYA OS SHUTDOWN
# =================================================================================

class TestLeyaShutdown:
    """Проверяем, что shutdown логирует ошибки, но не падает и не проглатывает их молча."""

    @pytest.mark.asyncio
    async def test_shutdown_logs_errors_but_does_not_crash(self, caplog):
        """Если один из компонентов падает при сохранении — shutdown продолжается и логирует."""
        import logging
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from LeyaOS import LeyaOS
        from leya_core.config import LeyaConfig

        # Создаём OS без полного init
        os_instance = LeyaOS.__new__(LeyaOS)
        os_instance.config = LeyaConfig()
        os_instance.memory = AsyncMock()
        os_instance.memory._save_state = AsyncMock(side_effect=LeyaAtomicWriteError("disk full"))
        os_instance.drives = MagicMock()
        os_instance.homeostasis = MagicMock()
        os_instance._shutdown_event = asyncio.Event()
        os_instance._background_tasks = []  # ✅ ДОБАВЛЕНО
        os_instance.llm_client = None  # ✅ ДОБАВЛЕНО

        with caplog.at_level(logging.ERROR):
            # Не должно упасть
            await os_instance.shutdown()

        # Ошибка должна быть залогирована
        assert any("disk full" in rec.message or "atomic" in rec.message.lower()
                   for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_shutdown_succeeds_when_all_components_ok(self):
        """Если всё ок — shutdown проходит без ошибок."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from LeyaOS import LeyaOS
        from leya_core.config import LeyaConfig

        os_instance = LeyaOS.__new__(LeyaOS)
        os_instance.config = LeyaConfig()
        os_instance.memory = AsyncMock()
        os_instance.memory._save_state = AsyncMock()
        os_instance.drives = MagicMock()
        os_instance.homeostasis = MagicMock()
        os_instance._shutdown_event = asyncio.Event()
        os_instance._background_tasks = []  # ✅ ДОБАВЛЕНО
        os_instance.llm_client = None  # ✅ ДОБАВЛЕНО

        await os_instance.shutdown()
        os_instance.memory._save_state.assert_awaited()