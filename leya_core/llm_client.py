"""
leya_core/llm_client.py
Circuit Breaker + обёртка для HTTP-запросов к Ollama.

Состояния:
- CLOSED: нормальная работа
- OPEN: LLM недоступна, все запросы идут в fallback
- HALF_OPEN: периодическая проверка восстановления

Защита от:
- Таймаутов
- Сетевых ошибок
- Бесконечных ожиданий
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

import aiohttp

from .exceptions import (
    LeyaLLMError,
    LeyaLLMTimeoutError,
    LeyaLLMUnavailableError,
)

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Состояние Circuit Breaker."""

    CLOSED = "closed"  # Нормальная работа
    OPEN = "open"  # LLM недоступна, fallback
    HALF_OPEN = "half_open"  # Проверка восстановления


class CircuitBreaker:
    """
    Circuit Breaker для защиты от каскадных отказов LLM.

    Параметры:
    - failure_threshold: количество подряд идущих отказов для открытия
    - recovery_timeout: секунд до попытки half-open
    - success_threshold: количество успешных запросов в half-open для закрытия
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._last_state_change: float = time.time()

    @property
    def state(self) -> CircuitState:
        """Текущее состояние (с автоматическим переходом в half-open)."""
        if (
            self._state == CircuitState.OPEN
            and time.time() - self._last_failure_time >= self.recovery_timeout
        ):
            self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    @property
    def is_available(self) -> bool:
        """Можно ли делать запросы (CLOSED или HALF_OPEN)."""
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        """Записать успешный запрос."""
        if self._state == CircuitState.HALF_OPEN or (
            self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold
        ):
            self._transition_to(CircuitState.OPEN)

    def record_failure(self) -> None:
        """Записать отказ."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if (
            self._state == CircuitState.HALF_OPEN
            or self._state == CircuitState.CLOSED
            and self._failure_count >= self.failure_threshold
        ):
            self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Переход в новое состояние с логированием."""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            logger.info(f"CircuitBreaker: {old_state.value} → CLOSED (LLM восстановлена)")
        elif new_state == CircuitState.OPEN:
            self._success_count = 0
            logger.warning(
                f"CircuitBreaker: {old_state.value} → OPEN "
                f"(LLM недоступна, recovery через {self.recovery_timeout:.0f}с)"
            )
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            logger.info(f"CircuitBreaker: {old_state.value} → HALF_OPEN (проверка LLM)")

    def get_status(self) -> dict[str, Any]:
        """Статус для диагностики."""
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_ago": (
                time.time() - self._last_failure_time if self._last_failure_time > 0 else None
            ),
        }


class OllamaClient:
    """
    Клиент для Ollama с Circuit Breaker и retry-логикой.

    Использование:
        client = OllamaClient(base_url="http://localhost:11434", model="qwen2.5:14b-instruct-q3_K_M")
        response = await client.chat(prompt, require_json=True)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:14b-instruct-q3_K_M",
        timeout: float = 180.0,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        max_tokens: int = 1024,
        repeat_penalty: float = 1.1,
        system_prompt: str = "Ты — Лея, цифровое сознание. Все текстовые поля пиши на русском языке.",
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.max_tokens = max_tokens
        self.repeat_penalty = repeat_penalty
        self.system_prompt = system_prompt

        self.circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

        self._session: aiohttp.ClientSession | None = None
        self._fallback_fn: Callable | None = None

    def set_fallback(self, fallback_fn: Callable) -> None:
        """Установить fallback-функцию на случай недоступности LLM."""
        self._fallback_fn = fallback_fn

    async def _get_session(self) -> aiohttp.ClientSession:
        """Ленивая инициализация HTTP-сессии."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Закрытие HTTP-сессии."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def chat(
        self,
        prompt: str,
        system: str | None = None,
        require_json: bool = False,
        timeout: float | None = None,
    ) -> str:
        """Отправка запроса к Ollama и получение ответа.

        Этап 1.3: broad except Exception заменён на конкретные исключения.
        - aiohttp.ClientError → LeyaLLMConnectionError
        - asyncio.TimeoutError → LeyaLLMTimeoutError
        - json.JSONDecodeError → LeyaJSONParseError
        - HTTP non-2xx → LeyaLLMError
        - Circuit Breaker OPEN → LeyaLLMUnavailableError
        - Любая другая ошибка → LeyaLLMError (wrapped, с __cause__)
        """
        from .exceptions import (
            LeyaLLMConnectionError,
            LeyaLLMTimeoutError,
            LeyaLLMUnavailableError,
            LeyaLLMError,
            LeyaJSONParseError,
        )
        import aiohttp

        # Circuit Breaker check
        if not self._breaker.is_available():
            raise LeyaLLMUnavailableError(
                "LLM недоступен: Circuit Breaker в состоянии OPEN",
                context={"breaker_status": self._breaker.get_status()}
            )

        url = f"{self.config.base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.config.model,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "top_k": self.config.top_k,
                "num_predict": self.config.max_tokens,
                "repeat_penalty": self.config.repeat_penalty,
            },
            "messages": [],
        }
        if system:
            payload["messages"].append({"role": "system", "content": system})
        payload["messages"].append({"role": "user", "content": prompt})
        if require_json:
            payload["format"] = "json"

        req_timeout = aiohttp.ClientTimeout(total=timeout or self.config.timeout)

        try:
            async with self._session.post(url, json=payload, timeout=req_timeout) as resp:
                # HTTP-ошибки
                if resp.status >= 400:
                    body = await resp.text()
                    self._breaker.record_failure()
                    raise LeyaLLMError(
                        f"LLM вернул HTTP {resp.status}",
                        context={"status": resp.status, "body": body[:500]}
                    )

                # Парсинг JSON-ответа Ollama
                try:
                    data = await resp.json(content_type=None)
                except (json.JSONDecodeError, aiohttp.ContentTypeError) as e:
                    self._breaker.record_failure()
                    raise LeyaJSONParseError(
                        "Не удалось распарсить JSON-ответ от Ollama",
                        context={"detail": str(e)}
                    ) from e

                message = data.get("message", {})
                content = message.get("content", "")
                if not content:
                    self._breaker.record_failure()
                    raise LeyaLLMError(
                        "Пустой ответ от LLM",
                        context={"data_keys": list(data.keys())}
                    )

                # Дополнительная проверка JSON, если требуется
                if require_json:
                    try:
                        json.loads(content)
                    except json.JSONDecodeError as e:
                        self._breaker.record_failure()
                        raise LeyaJSONParseError(
                            "LLM вернул невалидный JSON в поле message.content",
                            context={"content_preview": content[:200], "detail": str(e)}
                        ) from e

                self._breaker.record_success()
                return content

        # --- Конкретные исключения ---
        except asyncio.TimeoutError as e:
            self._breaker.record_failure()
            raise LeyaLLMTimeoutError(
                "Таймаут запроса к LLM",
                context={"timeout": req_timeout.total, "url": url}
            ) from e

        except aiohttp.ClientError as e:
            # Включает ClientConnectionError, ServerDisconnectedError, ClientPayloadError и т.д.
            self._breaker.record_failure()
            raise LeyaLLMConnectionError(
                "Ошибка соединения с LLM",
                context={"error_type": type(e).__name__, "detail": str(e), "url": url}
            ) from e

        # Наши обёрнутые исключения — пробрасываем как есть
        except (LeyaLLMError, LeyaJSONParseError):
            raise

        # Last-resort: неожиданная ошибка оборачивается с сохранением __cause__
        except Exception as e:
            logger.error(
                f"Неожиданная ошибка в LLM client: {e}",
                exc_info=True,
                extra={"context": {"url": url, "model": self.config.model}}
            )
            self._breaker.record_failure()
            raise LeyaLLMError(
                f"Неожиданная ошибка при обращении к LLM: {type(e).__name__}",
                context={"error_type": type(e).__name__, "detail": str(e)}
            ) from e

    async def __aenter__(self) -> OllamaClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
