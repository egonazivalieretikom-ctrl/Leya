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
import json
from collections.abc import Callable
from enum import Enum
from typing import (
    Any,
    Callable,
    Protocol,
    runtime_checkable,
    Optional, 
)

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
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._transition_to(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            # Сбрасываем счётчик ошибок при успехе
            if self._failure_count > 0:
                self._failure_count = max(0, self._failure_count - 1)

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
        self.base_url = base_url.rstrip("/")  # ✅ Используем параметр напрямую
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

    async def _get_session(self):
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

        Обработка ошибок:
        - aiohttp.ClientError → LeyaLLMConnectionError
        - asyncio.TimeoutError → LeyaLLMTimeoutError
        - json.JSONDecodeError → LeyaJSONParseError
        - HTTP non-2xx → LeyaLLMError
        - Circuit Breaker OPEN → LeyaLLMUnavailableError
        - Пустой ответ → LeyaLLMError
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
        if not self.circuit_breaker.is_available:
            if self._fallback_fn:
                return await self._fallback_fn(prompt)
            raise LeyaLLMUnavailableError(
                "LLM недоступен: Circuit Breaker в состоянии OPEN",
                context={"breaker_status": self.circuit_breaker.get_status()}
            )

        # Инициализация сессии при первом вызове
        if self._session is None:
            self._session = aiohttp.ClientSession()

        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "num_predict": self.max_tokens,
                "repeat_penalty": self.repeat_penalty,
            },
            "messages": [],
        }
        if system:
            payload["messages"].append({"role": "system", "content": system})
        payload["messages"].append({"role": "user", "content": prompt})
        if require_json:
            payload["format"] = "json"

        req_timeout = aiohttp.ClientTimeout(total=timeout or self.timeout)

        try:
            async with self._session.post(url, json=payload, timeout=req_timeout) as resp:
                # HTTP-ошибки
                if resp.status >= 400:
                    body = await resp.text()
                    self.circuit_breaker.record_failure()
                    raise LeyaLLMError(
                        f"LLM вернул HTTP {resp.status}",
                        context={"status": resp.status, "body": body[:500]}
                    )

                # Парсинг JSON-ответа Ollama
                try:
                    data = await resp.json(content_type=None)
                except (json.JSONDecodeError, aiohttp.ContentTypeError) as e:
                    self.circuit_breaker.record_failure()
                    raise LeyaJSONParseError(
                        "Не удалось распарсить JSON-ответ от Ollama",
                        context={"detail": str(e)}
                    ) from e

                message = data.get("message", {})
                content = message.get("content", "")
                if not content:
                    self.circuit_breaker.record_failure()
                    raise LeyaLLMError(
                        "Пустой ответ от LLM",
                        context={"data_keys": list(data.keys())}
                    )

                # Дополнительная проверка JSON, если требуется
                if require_json:
                    try:
                        json.loads(content)
                    except json.JSONDecodeError as e:
                        self.circuit_breaker.record_failure()
                        raise LeyaJSONParseError(
                            "LLM вернул невалидный JSON в поле message.content",
                            context={"content_preview": content[:200], "detail": str(e)}
                        ) from e

                self.circuit_breaker.record_success()
                return content

        # --- Конкретные исключения ---
        except asyncio.TimeoutError as e:
            self.circuit_breaker.record_failure()
            raise LeyaLLMTimeoutError(
                "Таймаут запроса к LLM",
                context={"timeout": req_timeout.total, "url": url}
            ) from e

        except aiohttp.ClientError as e:
            self.circuit_breaker.record_failure()
            raise LeyaLLMConnectionError(
                "Ошибка соединения с LLM",
                context={"error_type": type(e).__name__, "detail": str(e), "url": url}
            ) from e

        # Наши обёрнутые исключения — пробрасываем как есть
        except (LeyaLLMError, LeyaJSONParseError):
            raise

        # Last-resort: неожиданная ошибка (НО НЕ ловим CancelledError, KeyboardInterrupt, SystemExit)
        except asyncio.CancelledError:
            raise  # Просто пробрасываем — это нормальное отключение
        except KeyboardInterrupt:
            raise  # Ctrl+C должен работать
        except SystemExit:
            raise  # Команда выхода
        except (RuntimeError, ValueError, TypeError) as e:
            # Конкретные типы ошибок, которые могут возникнуть
            logger.error(
                f"Ошибка в LLM client: {type(e).__name__}: {e}",
                exc_info=True,
                extra={"context": {"url": url, "model": self.model}}
            )
            self.circuit_breaker.record_failure()
            raise LeyaLLMError(
                f"Ошибка при обращении к LLM: {type(e).__name__}",
                context={"error_type": type(e).__name__, "detail": str(e)}
            ) from e
        except Exception as e:
            # Истинный last resort для непредвиденных ошибок
            logger.error(
                f"Неожиданная ошибка в LLM client: {type(e).__name__}: {e}",
                exc_info=True,
                extra={"context": {"url": url, "model": self.model}}
            )
            self.circuit_breaker.record_failure()
            raise LeyaLLMError(
                f"Неожиданная ошибка при обращении к LLM: {type(e).__name__}",
                context={"error_type": type(e).__name__, "detail": str(e)}
            ) from e

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        require_json: bool = False,
        timeout: float | None = None,
    ) -> str:
        """Обёртка для обратной совместимости с memory.py."""
        return await self.chat(
            prompt=prompt,
            system=system,
            require_json=require_json,
            timeout=timeout,
        )

    async def __aenter__(self) -> OllamaClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def _chat_impl(
        self,
        prompt: str,
        system: str | None = None,
        require_json: bool = False,
        timeout: float | None = None,
    ) -> str:
        """Внутренняя реализация chat без retry."""
        from .exceptions import (
            LeyaLLMConnectionError,
            LeyaLLMTimeoutError,
            LeyaLLMUnavailableError,
            LeyaLLMError,
            LeyaJSONParseError,
        )
        import aiohttp

        # Circuit Breaker check
        if not self.circuit_breaker.is_available:
            if self._fallback_fn:
                return await self._fallback_fn(prompt)
            raise LeyaLLMUnavailableError(
                "LLM недоступен: Circuit Breaker в состоянии OPEN",
                context={"breaker_status": self.circuit_breaker.get_status()}
            )

        # Инициализация сессии при первом вызове
        if self._session is None:
            self._session = aiohttp.ClientSession()

        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "num_predict": self.max_tokens,
                "repeat_penalty": self.repeat_penalty,
            },
            "messages": [],
        }
        if system:
            payload["messages"].append({"role": "system", "content": system})
        payload["messages"].append({"role": "user", "content": prompt})
        if require_json:
            payload["format"] = "json"

        req_timeout = aiohttp.ClientTimeout(total=timeout or self.timeout)

        try:
            async with self._session.post(url, json=payload, timeout=req_timeout) as resp:
                # HTTP-ошибки
                if resp.status >= 400:
                    body = await resp.text()
                    self.circuit_breaker.record_failure()
                    raise LeyaLLMError(
                        f"LLM вернул HTTP {resp.status}",
                        context={"status": resp.status, "body": body[:500]}
                    )

                # Парсинг JSON-ответа Ollama
                try:
                    data = await resp.json(content_type=None)
                except (json.JSONDecodeError, aiohttp.ContentTypeError) as e:
                    self.circuit_breaker.record_failure()
                    raise LeyaJSONParseError(
                        "Не удалось распарсить JSON-ответ от Ollama",
                        context={"detail": str(e)}
                    ) from e

                message = data.get("message", {})
                content = message.get("content", "")
                if not content:
                    self.circuit_breaker.record_failure()
                    raise LeyaLLMError(
                        "Пустой ответ от LLM",
                        context={"data_keys": list(data.keys())}
                    )

                # Дополнительная проверка JSON, если требуется
                if require_json:
                    try:
                        json.loads(content)
                    except json.JSONDecodeError as e:
                        self.circuit_breaker.record_failure()
                        raise LeyaJSONParseError(
                            "LLM вернул невалидный JSON в поле message.content",
                            context={"content_preview": content[:200], "detail": str(e)}
                        ) from e

                self.circuit_breaker.record_success()
                return content

        # --- Конкретные исключения ---
        except asyncio.TimeoutError as e:
            self.circuit_breaker.record_failure()
            raise LeyaLLMTimeoutError(
                "Таймаут запроса к LLM",
                context={"timeout": req_timeout.total, "url": url}
            ) from e

        except aiohttp.ClientError as e:
            self.circuit_breaker.record_failure()
            raise LeyaLLMConnectionError(
                "Ошибка соединения с LLM",
                context={"error_type": type(e).__name__, "detail": str(e), "url": url}
            ) from e

        # Наши обёрнутые исключения — пробрасываем как есть
        except (LeyaLLMError, LeyaJSONParseError):
            raise

        # Last-resort
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(
                f"Ошибка в LLM client: {type(e).__name__}: {e}",
                exc_info=True,
                extra={"context": {"url": url, "model": self.model}}
            )
            self.circuit_breaker.record_failure()
            raise LeyaLLMError(
                f"Ошибка при обращении к LLM: {type(e).__name__}",
                context={"error_type": type(e).__name__, "detail": str(e)}
            ) from e
        except Exception as e:
            logger.error(
                f"Неожиданная ошибка в LLM client: {type(e).__name__}: {e}",
                exc_info=True,
                extra={"context": {"url": url, "model": self.model}}
            )
            self.circuit_breaker.record_failure()
            raise LeyaLLMError(
                f"Неожиданная ошибка при обращении к LLM: {type(e).__name__}",
                context={"error_type": type(e).__name__, "detail": str(e)}
            ) from e


    async def chat(
        self,
        prompt: str,
        system: str | None = None,
        require_json: bool = False,
        timeout: float | None = None,
        max_retries: int = 3,
    ) -> str:
        """Отправка запроса к Ollama с retry и exponential backoff.

        Args:
            prompt: Промпт для LLM
            system: Системный промпт (опционально)
            require_json: Требовать JSON-формат
            timeout: Таймаут запроса
            max_retries: Максимальное количество попыток (по умолчанию 3)

        Returns:
            Ответ LLM или fallback
        """
        from .exceptions import LeyaLLMTimeoutError, LeyaLLMConnectionError, LeyaLLMError

        last_exception = None
    
        for attempt in range(max_retries):
            try:
                return await self._chat_impl(
                    prompt=prompt,
                    system=system,
                    require_json=require_json,
                    timeout=timeout,
                )
            except (LeyaLLMTimeoutError, LeyaLLMConnectionError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} после {wait_time}s "
                        f"(ошибка: {type(e).__name__})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Последняя попытка провалилась
                    logger.error(
                        f"Все {max_retries} попыток провалились: {type(e).__name__}: {e}"
                    )
                    raise
            except LeyaLLMError:
                # Другие LLM-ошибки не ретраим
                raise

        # Не должно достигнуть сюда, но на всякий случай
        if last_exception:
            raise last_exception
        raise LeyaLLMError("Неожиданная ошибка в retry-логике")