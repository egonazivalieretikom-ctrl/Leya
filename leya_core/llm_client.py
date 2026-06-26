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
from enum import Enum
from typing import Any, Callable, Optional

import aiohttp

from .exceptions import (
    LeyaLLMError,
    LeyaLLMTimeoutError,
    LeyaLLMUnavailableError,
)

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Состояние Circuit Breaker."""
    CLOSED = "closed"          # Нормальная работа
    OPEN = "open"              # LLM недоступна, fallback
    HALF_OPEN = "half_open"    # Проверка восстановления


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
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    @property
    def is_available(self) -> bool:
        """Можно ли делать запросы (CLOSED или HALF_OPEN)."""
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        """Записать успешный запрос."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._transition_to(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0  # Сброс счётчика отказов

    def record_failure(self) -> None:
        """Записать отказ."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
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
                time.time() - self._last_failure_time
                if self._last_failure_time > 0 else None
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

        self._session: Optional[aiohttp.ClientSession] = None
        self._fallback_fn: Optional[Callable] = None

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
        require_json: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Отправка запроса к Ollama с защитой Circuit Breaker.
        
        Бросает:
        - LeyaLLMUnavailableError: Circuit Breaker в состоянии OPEN
        - LeyaLLMTimeoutError: превышен таймаут
        - LeyaLLMError: другие ошибки
        """
        # Проверка Circuit Breaker
        if not self.circuit_breaker.is_available:
            logger.warning("OllamaClient: Circuit Breaker OPEN, используем fallback")
            if self._fallback_fn:
                return await self._fallback_fn(prompt)
            raise LeyaLLMUnavailableError(
                "Ollama недоступна (Circuit Breaker OPEN)",
                context=self.circuit_breaker.get_status(),
            )

        # Формирование payload
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "num_predict": max_tokens if max_tokens is not None else self.max_tokens,
                "repeat_penalty": self.repeat_penalty,
            },
        }
        if require_json:
            payload["format"] = "json"

        # HTTP-запрос
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    message = data.get("message", {})
                    content = message.get("content", "")
                    self.circuit_breaker.record_success()
                    return content
                else:
                    error_text = await response.text()
                    self.circuit_breaker.record_failure()
                    raise LeyaLLMError(
                        f"Ollama вернул статус {response.status}",
                        context={"status": response.status, "body": error_text[:500]},
                    )

        except asyncio.TimeoutError as exc:
            self.circuit_breaker.record_failure()
            raise LeyaLLMTimeoutError(
                f"Превышен таймаут {self.timeout}с",
                context={"timeout": self.timeout},
            ) from exc

        except aiohttp.ClientError as exc:
            self.circuit_breaker.record_failure()
            raise LeyaLLMUnavailableError(
                "Ошибка подключения к Ollama",
                context={"error": str(exc), "base_url": self.base_url},
            ) from exc

        except LeyaLLMError:
            # Пробрасываем наши исключения
            raise

        except Exception as exc:
            self.circuit_breaker.record_failure()
            raise LeyaLLMError(
                "Неожиданная ошибка вызова LLM",
                context={"error": str(exc)},
            ) from exc

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()