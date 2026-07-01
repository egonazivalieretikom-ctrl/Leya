"""
leya_core/llm_client.py
OllamaBackend — конкретная реализация LLMBackend для Ollama HTTP API.

Шаг 2.2: Рефакторинг OllamaClient → OllamaBackend с наследованием от LLMBackend.
- Все абстрактные методы LLMBackend реализованы
- Circuit Breaker сохранён (CLOSED/OPEN/HALF_OPEN)
- Retry с exponential backoff для transient-ошибок
- generate() — обёртка над chat() для обратной совместимости с memory.py
- health_check() — синхронная быстрая проверка для диагностики
- Обратная совместимость: OllamaClient = OllamaBackend (алиас)

Защита от:
- Таймаутов
- Сетевых ошибок
- Бесконечных ожиданий
- Маскировки багов (конкретные except + last-resort без обёртки)
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Callable
from enum import Enum
from typing import Any, Optional

import aiohttp

from .exceptions import (
    LeyaJSONParseError,
    LeyaLLMConnectionError,
    LeyaLLMError,
    LeyaLLMTimeoutError,
    LeyaLLMUnavailableError,
)
from .llm_backend import LLMBackend

logger = logging.getLogger(__name__)


# =========================================================================
# Circuit Breaker
# =========================================================================
class CircuitState(str, Enum):
    """Состояние Circuit Breaker."""

    CLOSED = "closed"        # Нормальная работа
    OPEN = "open"            # LLM недоступна, fallback
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
        """Текущее состояние (с автоматическим переходом в half-open).

        Осознанный компромисс для Circuit Breaker.
        Ленивая проверка восстановления позволяет избежать фоновых задач
        и упрощает интеграцию. Это стандартная практика для CB паттерна.
        """
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
            logger.info(
                f"CircuitBreaker: {old_state.value} → CLOSED (LLM восстановлена)"
            )
        elif new_state == CircuitState.OPEN:
            self._success_count = 0
            logger.warning(
                f"CircuitBreaker: {old_state.value} → OPEN "
                f"(LLM недоступна, recovery через {self.recovery_timeout:.0f}с)"
            )
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            logger.info(
                f"CircuitBreaker: {old_state.value} → HALF_OPEN (проверка LLM)"
            )

    def get_status(self) -> dict[str, Any]:
        """Статус для диагностики."""
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_ago": (
                time.time() - self._last_failure_time
                if self._last_failure_time > 0
                else None
            ),
        }


# =========================================================================
# OllamaBackend — конкретная реализация LLMBackend
# =========================================================================
class OllamaBackend(LLMBackend):
    """
    Ollama HTTP API бэкенд с Circuit Breaker и retry-логикой.

    Наследуется от LLMBackend (абстрактный базовый класс), что гарантирует:
    - Реализацию всех абстрактных методов (chat, generate, health_check, is_available)
    - Совместимость с ILLMClient Protocol (структурная типизация)
    - Возможность замены на другой бэкенд (OpenAI, Anthropic) без изменения LeyaOS

    Использование:
        backend = OllamaBackend(
            base_url="http://localhost:11434",
            model="qwen2.5:14b-instruct-q3_K_M",
        )
        response = await backend.chat(prompt, require_json=True)

    Обратная совместимость:
        OllamaClient = OllamaBackend  # алиас в конце файла
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
        system_prompt: str = (
            "Ты — Лея, цифровое сознание. Все текстовые поля пиши на русском языке."
        ),
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
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
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ===================================================================
    # Реализация абстрактных методов LLMBackend
    # ===================================================================

    async def close(self) -> None:
        """Закрытие HTTP-сессии.

        Переопределение LLMBackend.close() для корректного освобождения
        ресурсов aiohttp.ClientSession.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # -------------------------------------------------------------------
    # chat() — основной метод взаимодействия с LLM
    # -------------------------------------------------------------------
    async def chat(
        self,
        prompt: str,
        system: str | None = None,
        require_json: bool = False,
        timeout: float | None = None,
        max_retries: int = 3,
        max_tokens: int | None = None,
    ) -> str:
        """Отправка запроса к Ollama с retry и exponential backoff.

        Реализация абстрактного метода LLMBackend.chat() с расширенной сигнатурой:
        - system: системный промпт (опционально)
        - timeout: переопределение таймаута
        - max_retries: количество попыток (по умолчанию 3)
        - max_tokens: переопределение max_tokens

        Retry применяется ТОЛЬКО для transient-ошибок:
        - LeyaLLMTimeoutError
        - LeyaLLMConnectionError

        Другие LLM-ошибки (HTTP 500, пустой ответ, JSON parse error) не ретраим —
        эти ошибки обычно стабильны, повтор не поможет.

        Args:
            prompt: Промпт для LLM
            system: Системный промпт (опционально)
            require_json: Требовать JSON-формат
            timeout: Таймаут запроса
            max_retries: Максимальное количество попыток (по умолчанию 3)
            max_tokens: Максимальное количество токенов в ответе
                         (переопределяет self.max_tokens для данного вызова)

        Returns:
            Ответ LLM или fallback
        """
        last_exception = None

        for attempt in range(max_retries):
            try:
                return await self._chat_impl(
                    prompt=prompt,
                    system=system,
                    require_json=require_json,
                    timeout=timeout,
                    max_tokens=max_tokens,
                )
            except (LeyaLLMTimeoutError, LeyaLLMConnectionError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s + jitter
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} после {wait_time:.1f}s "
                        f"(ошибка: {type(e).__name__})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Последняя попытка провалилась
                    logger.error(
                        f"Все {max_retries} попыток провалились: "
                        f"{type(e).__name__}: {e}"
                    )
                    raise
            except (LeyaLLMError, LeyaJSONParseError):
                # Другие LLM-ошибки (HTTP 500, пустой ответ, JSON parse error)
                # не ретраим. Эти ошибки обычно стабильны — повтор не поможет.
                raise

        # Не должно достигнуть сюда, но на всякий случай
        if last_exception:
            raise last_exception
        raise LeyaLLMError("Неожиданная ошибка в retry-логике")

    # -------------------------------------------------------------------
    # generate() — упрощённая генерация (обёртка над chat)
    # -------------------------------------------------------------------
    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        require_json: bool = False,
        timeout: float | None = None,
    ) -> str:
        """Обёртка для обратной совместимости с memory.py.

        Реализация абстрактного метода LLMBackend.generate() с расширенной сигнатурой.
        Полностью делегирует chat(), корректно передавая ВСЕ параметры,
        включая max_tokens (ранее игнорировался).

        Args:
            prompt: Промпт для генерации
            system: Системный промпт (опционально)
            max_tokens: Максимальное количество токенов в ответе
            require_json: Требовать JSON-формат
            timeout: Таймаут запроса

        Returns:
            Сгенерированный текст
        """
        return await self.chat(
            prompt=prompt,
            system=system,
            require_json=require_json,
            timeout=timeout,
            max_tokens=max_tokens,
        )

    # -------------------------------------------------------------------
    # health_check() — быстрая синхронная проверка (для диагностики)
    # -------------------------------------------------------------------
    def health_check(self) -> bool:
        """Быстрая проверка доступности LLM (синхронная).

        Реализация абстрактного метода LLMBackend.health_check().
        Не делает реальный запрос к LLM (это дорого) — достаточно проверки
        состояния Circuit Breaker.

        Returns:
            True если Circuit Breaker в состоянии CLOSED или HALF_OPEN,
            False если OPEN.
        """
        return self.circuit_breaker.is_available

    # -------------------------------------------------------------------
    # is_available — property (алиас для health_check)
    # -------------------------------------------------------------------
    @property
    def is_available(self) -> bool:
        """Свойство: доступен ли LLM для запросов прямо сейчас.

        Реализация абстрактного property LLMBackend.is_available.
        Делегирует Circuit Breaker.

        Returns:
            True если Circuit Breaker в состоянии CLOSED или HALF_OPEN,
            False если OPEN.
        """
        return self.circuit_breaker.is_available

    # -------------------------------------------------------------------
    # get_status() — расширенная диагностика
    # -------------------------------------------------------------------
    def get_status(self) -> dict[str, Any]:
        """Диагностическая информация о состоянии бэкенда.

        Переопределение LLMBackend.get_status() для добавления специфичных
        данных Ollama: Circuit Breaker status, модель, URL и т.д.

        Returns:
            dict с диагностической информацией.
        """
        base_status = super().get_status()
        base_status.update(
            {
                "backend_type": "OllamaBackend",
                "model": self.model,
                "base_url": self.base_url,
                "timeout": self.timeout,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "circuit_breaker": self.circuit_breaker.get_status(),
                "session_active": (
                    self._session is not None and not self._session.closed
                ),
                "fallback_configured": self._fallback_fn is not None,
            }
        )
        return base_status

    # ===================================================================
    # Приватные методы (остаются приватными, не часть интерфейса)
    # ===================================================================

    async def _chat_impl(
        self,
        prompt: str,
        system: str | None = None,
        require_json: bool = False,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Внутренняя реализация chat без retry.

        Обработка исключений (строго по специфичности):
        1. asyncio.TimeoutError → LeyaLLMTimeoutError
        2. aiohttp.ClientError → LeyaLLMConnectionError
        3. json.JSONDecodeError → LeyaJSONParseError
        4. Leya*Error → re-raise (уже обёрнутые)
        5. asyncio.CancelledError / KeyboardInterrupt / SystemExit → re-raise
        6. Exception → logger.exception + re-raise (БЕЗ обёртки!)

        Args:
            prompt: Промпт для LLM
            system: Системный промпт (опционально)
            require_json: Требовать JSON-формат ответа
            timeout: Таймаут запроса (переопределяет self.timeout)
            max_tokens: Максимальное количество токенов в ответе
                        (переопределяет self.max_tokens для данного вызова)
        """
        # Circuit Breaker check
        if not self.circuit_breaker.is_available:
            if self._fallback_fn:
                return await self._fallback_fn(prompt)
            raise LeyaLLMUnavailableError(
                "LLM недоступен: Circuit Breaker в состоянии OPEN",
                context={"breaker_status": self.circuit_breaker.get_status()},
            )

        # Инициализация сессии при первом вызове
        if self._session is None:
            self._session = aiohttp.ClientSession()

        url = f"{self.base_url}/api/chat"

        effective_max_tokens = (
            max_tokens if max_tokens is not None else self.max_tokens
        )

        payload = {
            "model": self.model,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "num_predict": effective_max_tokens,
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
            async with self._session.post(
                url, json=payload, timeout=req_timeout
            ) as resp:
                # HTTP-ошибки
                if resp.status >= 400:
                    body = await resp.text()
                    self.circuit_breaker.record_failure()
                    raise LeyaLLMError(
                        f"LLM вернул HTTP {resp.status}",
                        context={"status": resp.status, "body": body[:500]},
                    )

                # Парсинг JSON-ответа Ollama
                try:
                    data = await resp.json(content_type=None)
                except (json.JSONDecodeError, aiohttp.ContentTypeError) as e:
                    self.circuit_breaker.record_failure()
                    raise LeyaJSONParseError(
                        "Не удалось распарсить JSON-ответ от Ollama",
                        context={"detail": str(e)},
                    ) from e

                message = data.get("message", {})
                content = message.get("content", "")
                if not content:
                    self.circuit_breaker.record_failure()
                    raise LeyaLLMError(
                        "Пустой ответ от LLM",
                        context={"data_keys": list(data.keys())},
                    )

                # Дополнительная проверка JSON, если требуется
                if require_json:
                    try:
                        json.loads(content)
                    except json.JSONDecodeError as e:
                        self.circuit_breaker.record_failure()
                        raise LeyaJSONParseError(
                            "LLM вернул невалидный JSON в поле message.content",
                            context={
                                "content_preview": content[:200],
                                "detail": str(e),
                            },
                        ) from e

                self.circuit_breaker.record_success()
                return content

        # =================================================================
        # Обработка исключений — СТРОГО ПО СПЕЦИФИЧНОСТИ
        # =================================================================

        # 1. Таймаут запроса
        except asyncio.TimeoutError as e:
            self.circuit_breaker.record_failure()
            raise LeyaLLMTimeoutError(
                "Таймаут запроса к LLM",
                context={"timeout": req_timeout.total, "url": url},
            ) from e

        # 2. Ошибка соединения / сети
        except aiohttp.ClientError as e:
            self.circuit_breaker.record_failure()
            raise LeyaLLMConnectionError(
                "Ошибка соединения с LLM",
                context={
                    "error_type": type(e).__name__,
                    "detail": str(e),
                    "url": url,
                },
            ) from e

        # 3. Ошибка парсинга JSON (если произошла вне блока resp.json)
        except json.JSONDecodeError as e:
            self.circuit_breaker.record_failure()
            raise LeyaJSONParseError(
                "Ошибка парсинга JSON в LLM-ответе",
                context={"detail": str(e), "url": url},
            ) from e

        # 4. Наши специфичные исключения — пробрасываем как есть
        except (LeyaLLMError, LeyaJSONParseError):
            raise

        # 5. BaseException-подклассы — пробрасываем немедленно
        #    (Ctrl+C, отмена задачи, выход из процесса)
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise

        # 6. Last resort: НЕОЖИДАННЫЕ исключения
        #    ТОЛЬКО логирование + немедленный re-raise БЕЗ обёртки.
        #    Это позволяет видеть реальный тип исключения и не маскировать баги.
        except Exception as e:
            logger.exception(
                "Unexpected error in LLM call",
                extra={"context": {"url": url, "model": self.model}},
            )
            # record_failure НЕ вызываем — неизвестная природа ошибки,
            # не хотим ложно открывать Circuit Breaker.
            raise

    # ===================================================================
    # Context manager support (наследуется от LLMBackend, но переопределяем
    # для явного указания типа возврата)
    # ===================================================================
    async def __aenter__(self) -> "OllamaBackend":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


# =========================================================================
# Обратная совместимость: алиас для старого имени
# =========================================================================
# Все существующие импорты `from leya_core.llm_client import OllamaClient`
# продолжат работать. Новый код должен использовать OllamaBackend.
OllamaClient = OllamaBackend