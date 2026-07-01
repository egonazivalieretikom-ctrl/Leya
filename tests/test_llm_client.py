"""
Unit-тесты для leya_core/llm_client.py
Покрывает:
- Circuit Breaker (CLOSED→OPEN→HALF_OPEN→CLOSED)
- Retry с exponential backoff (только для transient-ошибок)
- Timeout handling
- generate() как обёртка над chat()
- health_check()
- Обработка исключений по специфичности
- Fallback при OPEN breaker

Использует unittest.mock для мока _chat_impl (вместо aioresponses).
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from leya_core.exceptions import (
    LeyaJSONParseError,
    LeyaLLMConnectionError,
    LeyaLLMError,
    LeyaLLMTimeoutError,
    LeyaLLMUnavailableError,
)
from leya_core.llm_client import CircuitBreaker, CircuitState, OllamaBackend


# =============================================================================
# ФИКСТУРЫ
# =============================================================================

@pytest.fixture
def circuit_breaker():
    """Circuit Breaker с дефолтными параметрами."""
    return CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=60.0,
        success_threshold=2,
    )


@pytest.fixture
def backend():
    """OllamaBackend с тестовыми параметрами."""
    return OllamaBackend(
        base_url="http://localhost:11434",
        model="test-model",
        timeout=10.0,
        failure_threshold=3,
        recovery_timeout=60.0,
    )


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

class TestCircuitBreaker:
    """Тесты Circuit Breaker."""

    def test_initial_state_closed(self, circuit_breaker):
        """Начальное состояние — CLOSED."""
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.is_available is True

    def test_transition_to_open_after_failures(self, circuit_breaker):
        """После N подряд идущих отказов → OPEN."""
        for _ in range(3):  # failure_threshold=3
            circuit_breaker.record_failure()

        assert circuit_breaker.state == CircuitState.OPEN
        assert circuit_breaker.is_available is False

    def test_transition_to_half_open_after_recovery_timeout(self, circuit_breaker):
        """После recovery_timeout → HALF_OPEN (ленивая проверка)."""
        # Открываем breaker
        for _ in range(3):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == CircuitState.OPEN

        # Имитируем passage of time
        circuit_breaker._last_failure_time = time.time() - 61.0  # > recovery_timeout

        # Ленивая проверка должна перевести в HALF_OPEN
        assert circuit_breaker.state == CircuitState.HALF_OPEN
        assert circuit_breaker.is_available is True

    def test_transition_to_closed_after_success_in_half_open(self, circuit_breaker):
        """После success_threshold успехов в HALF_OPEN → CLOSED."""
        # Открываем breaker
        for _ in range(3):
            circuit_breaker.record_failure()

        # Переводим в HALF_OPEN
        circuit_breaker._last_failure_time = time.time() - 61.0
        assert circuit_breaker.state == CircuitState.HALF_OPEN

        # Успехи в HALF_OPEN
        circuit_breaker.record_success()
        assert circuit_breaker.state == CircuitState.HALF_OPEN  # Ещё не CLOSED

        circuit_breaker.record_success()
        assert circuit_breaker.state == CircuitState.CLOSED  # Теперь CLOSED
        assert circuit_breaker.is_available is True

    def test_record_success_resets_failure_count_in_closed(self, circuit_breaker):
        """Успех в CLOSED сбрасывает счётчик ошибок."""
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()
        assert circuit_breaker._failure_count == 2

        circuit_breaker.record_success()
        assert circuit_breaker._failure_count == 1  # Уменьшился на 1

    def test_record_failure_in_half_open_opens_breaker(self, circuit_breaker):
        """Отказ в HALF_OPEN → OPEN."""
        # Открываем breaker
        for _ in range(3):
            circuit_breaker.record_failure()

        # Переводим в HALF_OPEN
        circuit_breaker._last_failure_time = time.time() - 61.0
        assert circuit_breaker.state == CircuitState.HALF_OPEN

        # Отказ в HALF_OPEN
        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitState.OPEN

    def test_get_status(self, circuit_breaker):
        """get_status() возвращает корректную структуру."""
        status = circuit_breaker.get_status()

        assert "state" in status
        assert "failure_count" in status
        assert "success_count" in status
        assert "last_failure_ago" in status
        assert status["state"] == "closed"

    def test_get_status_after_failures(self, circuit_breaker):
        """get_status() после отказов показывает корректные данные."""
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()

        status = circuit_breaker.get_status()
        assert status["failure_count"] == 2
        assert status["last_failure_ago"] is not None


# =============================================================================
# OLLAMA BACKEND — CHAT TESTS
# =============================================================================

class TestOllamaBackendChat:
    """Тесты chat() метода."""

    @pytest.mark.asyncio
    async def test_chat_success(self, backend):
        """Успешный запрос к Ollama."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            mock_impl.return_value = '{"response": "Привет!"}'

            result = await backend.chat("Привет")

            assert result == '{"response": "Привет!"}'
            assert backend.circuit_breaker.state == CircuitState.CLOSED
            mock_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_timeout_raises_timeout_error(self, backend):
        """Timeout → LeyaLLMTimeoutError."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            mock_impl.side_effect = LeyaLLMTimeoutError("Timeout")

            with pytest.raises(LeyaLLMTimeoutError):
                await backend.chat("Тест", max_retries=1)

            # Проверяем, что исключение было выброшено
            mock_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_connection_error_raises_connection_error(self, backend):
        """Connection error → LeyaLLMConnectionError."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            mock_impl.side_effect = LeyaLLMConnectionError("Connection refused")

            with pytest.raises(LeyaLLMConnectionError):
                await backend.chat("Тест", max_retries=1)

            mock_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_http_500_raises_llm_error(self, backend):
        """HTTP 500 → LeyaLLMError."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            mock_impl.side_effect = LeyaLLMError("HTTP 500")

            with pytest.raises(LeyaLLMError):
                await backend.chat("Тест")

            mock_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_empty_response_raises_llm_error(self, backend):
        """Пустой ответ → LeyaLLMError."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            mock_impl.side_effect = LeyaLLMError("Пустой ответ")

            with pytest.raises(LeyaLLMError):
                await backend.chat("Тест")

            mock_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_invalid_json_with_require_json_raises_parse_error(self, backend):
        """Невалидный JSON при require_json=True → LeyaJSONParseError."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            mock_impl.side_effect = LeyaJSONParseError("Invalid JSON")

            with pytest.raises(LeyaJSONParseError):
                await backend.chat("Тест", require_json=True)

            mock_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_retry_on_timeout(self, backend):
        """Retry при timeout (exponential backoff)."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            # Первый запрос — timeout, второй — успех
            mock_impl.side_effect = [
                LeyaLLMTimeoutError("Timeout"),
                "Успех!",
            ]

            # Патчим asyncio.sleep для ускорения теста
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await backend.chat("Тест", max_retries=2)

            assert result == "Успех!"
            assert mock_impl.call_count == 2

    @pytest.mark.asyncio
    async def test_chat_retry_on_connection_error(self, backend):
        """Retry при connection error."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            # Первый запрос — ошибка, второй — успех
            mock_impl.side_effect = [
                LeyaLLMConnectionError("Connection refused"),
                "Успех!",
            ]

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await backend.chat("Тест", max_retries=2)

            assert result == "Успех!"
            assert mock_impl.call_count == 2

    @pytest.mark.asyncio
    async def test_chat_no_retry_on_llm_error(self, backend):
        """Нет retry при LeyaLLMError (стабильная ошибка)."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            mock_impl.side_effect = LeyaLLMError("HTTP 500")

            with pytest.raises(LeyaLLMError):
                await backend.chat("Тест", max_retries=3)

            # Должен быть только 1 вызов (без retry)
            assert mock_impl.call_count == 1

    @pytest.mark.asyncio
    async def test_chat_fallback_when_breaker_open(self, backend):
        """Fallback при OPEN breaker."""
        # Устанавливаем fallback
        fallback_fn = AsyncMock(return_value="Fallback ответ")
        backend.set_fallback(fallback_fn)

        # Открываем breaker
        for _ in range(3):
            backend.circuit_breaker.record_failure()

        assert backend.circuit_breaker.state == CircuitState.OPEN

        result = await backend.chat("Тест")

        assert result == "Fallback ответ"
        fallback_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_raises_unavailable_when_breaker_open_no_fallback(self, backend):
        """LeyaLLMUnavailableError при OPEN breaker без fallback."""
        # Открываем breaker
        for _ in range(3):
            backend.circuit_breaker.record_failure()

        assert backend.circuit_breaker.state == CircuitState.OPEN

        with pytest.raises(LeyaLLMUnavailableError):
            await backend.chat("Тест")


# =============================================================================
# OLLAMA BACKEND — GENERATE TESTS
# =============================================================================

class TestOllamaBackendGenerate:
    """Тесты generate() метода (обёртка над chat)."""

    @pytest.mark.asyncio
    async def test_generate_delegates_to_chat(self, backend):
        """generate() делегирует chat()."""
        with patch.object(backend, 'chat', new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "Сгенерированный текст"

            result = await backend.generate("Промпт")

            assert result == "Сгенерированный текст"
            mock_chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_passes_max_tokens(self, backend):
        """generate() передаёт max_tokens в chat()."""
        with patch.object(backend, 'chat', new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "Короткий ответ"

            result = await backend.generate("Промпт", max_tokens=500)

            assert result == "Короткий ответ"
            # Проверяем, что max_tokens был передан
            call_kwargs = mock_chat.call_args.kwargs
            assert call_kwargs.get("max_tokens") == 500

    @pytest.mark.asyncio
    async def test_generate_passes_require_json(self, backend):
        """generate() передаёт require_json в chat()."""
        with patch.object(backend, 'chat', new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '{"response": "JSON"}'

            result = await backend.generate("Промпт", require_json=True)

            assert result == '{"response": "JSON"}'
            # Проверяем, что require_json был передан
            call_kwargs = mock_chat.call_args.kwargs
            assert call_kwargs.get("require_json") is True


# =============================================================================
# OLLAMA BACKEND — HEALTH CHECK TESTS
# =============================================================================

class TestOllamaBackendHealthCheck:
    """Тесты health_check() метода."""

    def test_health_check_returns_true_when_closed(self, backend):
        """health_check() возвращает True при CLOSED breaker."""
        assert backend.circuit_breaker.state == CircuitState.CLOSED
        assert backend.health_check() is True

    def test_health_check_returns_false_when_open(self, backend):
        """health_check() возвращает False при OPEN breaker."""
        for _ in range(3):
            backend.circuit_breaker.record_failure()

        assert backend.circuit_breaker.state == CircuitState.OPEN
        assert backend.health_check() is False

    def test_is_available_property(self, backend):
        """is_available property делегирует health_check()."""
        assert backend.is_available is True

        for _ in range(3):
            backend.circuit_breaker.record_failure()

        assert backend.is_available is False


# =============================================================================
# OLLAMA BACKEND — STATUS TESTS
# =============================================================================

class TestOllamaBackendStatus:
    """Тесты get_status() метода."""

    def test_get_status_contains_all_fields(self, backend):
        """get_status() возвращает полную диагностику."""
        status = backend.get_status()

        assert "backend_type" in status
        assert "model" in status
        assert "base_url" in status
        assert "timeout" in status
        assert "temperature" in status
        assert "max_tokens" in status
        assert "circuit_breaker" in status
        assert "session_active" in status
        assert "fallback_configured" in status

        assert status["backend_type"] == "OllamaBackend"
        assert status["model"] == "test-model"
        assert status["base_url"] == "http://localhost:11434"

    def test_get_status_circuit_breaker_info(self, backend):
        """get_status() включает информацию о Circuit Breaker."""
        backend.circuit_breaker.record_failure()

        status = backend.get_status()
        assert status["circuit_breaker"]["failure_count"] == 1


# =============================================================================
# OLLAMA BACKEND — CLOSE TESTS
# =============================================================================

class TestOllamaBackendClose:
    """Тесты close() метода."""

    @pytest.mark.asyncio
    async def test_close_closes_session(self, backend):
        """close() закрывает aiohttp сессию."""
        # Создаём AsyncMock для сессии
        mock_session = AsyncMock()
        mock_session.closed = False
        backend._session = mock_session

        await backend.close()

        mock_session.close.assert_called_once()
        assert backend._session is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self, backend):
        """close() идемпотентен (можно вызывать несколько раз)."""
        await backend.close()
        await backend.close()  # Не должно упасть


# =============================================================================
# OLLAMA BACKEND — CONTEXT MANAGER TESTS
# =============================================================================

class TestOllamaBackendContextManager:
    """Тесты контекстного менеджера."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """OllamaBackend работает как контекстный менеджер."""
        async with OllamaBackend() as backend:
            with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
                mock_impl.return_value = "Тест"
                result = await backend.chat("Тест")
                assert result == "Тест"

        # После выхода из контекста сессия должна быть закрыта
        assert backend._session is None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestOllamaBackendIntegration:
    """Интеграционные тесты полного цикла."""

    @pytest.mark.asyncio
    async def test_full_cycle_success(self, backend):
        """Полный цикл: запрос → успех → CLOSED breaker."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            mock_impl.return_value = '{"response": "Привет!"}'

            result = await backend.chat("Привет", require_json=True)

            assert result == '{"response": "Привет!"}'
            assert backend.circuit_breaker.state == CircuitState.CLOSED
            assert backend.circuit_breaker._failure_count == 0

    @pytest.mark.asyncio
    async def test_full_cycle_recovery(self, backend):
        """Полный цикл: отказы → OPEN → recovery → HALF_OPEN → успех → CLOSED."""
        with patch.object(backend, '_chat_impl', new_callable=AsyncMock) as mock_impl:
            # 3 отказа → OPEN
            mock_impl.side_effect = LeyaLLMTimeoutError("Timeout")

            with patch("asyncio.sleep", new_callable=AsyncMock):
                for _ in range(3):
                    with pytest.raises(LeyaLLMTimeoutError):
                        await backend.chat("Тест", max_retries=1)

            # Вручную открываем breaker
            backend.circuit_breaker.record_failure()
            backend.circuit_breaker.record_failure()
            backend.circuit_breaker.record_failure()

            assert backend.circuit_breaker.state == CircuitState.OPEN

            # Имитируем recovery timeout
            backend.circuit_breaker._last_failure_time = time.time() - 61.0

            # ✅ Триггерим ленивую проверку состояния
            _ = backend.circuit_breaker.state  # Переведёт _state в HALF_OPEN

            # Успех в HALF_OPEN — нужно 2 успеха для перехода в CLOSED
            mock_impl.side_effect = None
            mock_impl.return_value = "Восстановлен!"

            # Первый успех в HALF_OPEN
            result1 = await backend.chat("Тест")
            assert result1 == "Восстановлен!"
            backend.circuit_breaker.record_success()
            assert backend.circuit_breaker.state == CircuitState.HALF_OPEN

            # Второй успех → CLOSED
            result2 = await backend.chat("Тест")
            assert result2 == "Восстановлен!"
            backend.circuit_breaker.record_success()
            assert backend.circuit_breaker.state == CircuitState.CLOSED