"""
leya_core/llm_client.py
HTTP-клиент для Ollama с Circuit Breaker и Retry.

Архитектура:
- Circuit Breaker (CLOSED → OPEN → HALF_OPEN)
- Retry с экспоненциальной задержкой
- Token estimation (эвристика для русского: ~4 символа = 1 токен)
- Специфичные исключения из leya_core/exceptions.py

Все методы — async.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import aiohttp

from .config import LeyaConfig
from .exceptions import (
    LeyaJSONParseError,
    LeyaLLMError,
    LeyaLLMTimeoutError,
    LeyaLLMUnavailableError,
)

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Состояние Circuit Breaker."""
    CLOSED = "closed"        # Нормальная работа
    OPEN = "open"            # Сбой, запросы блокируются
    HALF_OPEN = "half_open"  # Тестовый запрос


@dataclass
class CircuitBreakerConfig:
    """Конфигурация Circuit Breaker."""
    failure_threshold: int = 5          # Количество неудач до открытия
    recovery_timeout: float = 60.0      # Секунд до попытки HALF_OPEN
    success_threshold: int = 2          # Успехов в HALF_OPEN для закрытия


class OllamaClient:
    """
    HTTP-клиент для Ollama с Circuit Breaker.
    
    Использование:
        client = OllamaClient(config)
        response = await client.generate("Привет", require_json=True)
    """

    def __init__(self, config: LeyaConfig) -> None:
        self.config = config
        self.base_url = config.ollama.base_url.rstrip("/")
        self.model = config.ollama.model
        self.timeout = config.ollama.timeout
        self.temperature = config.ollama.temperature
        self.num_ctx = config.ollama.num_ctx
        
        # Circuit Breaker state
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._breaker_config = CircuitBreakerConfig()
        
        # HTTP session (создаётся лениво)
        self._session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"OllamaClient инициализирован: {self.base_url}, model={self.model}")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Ленивая инициализация HTTP-сессии."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Закрытие HTTP-сессии."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _check_circuit(self) -> None:
        """Проверка состояния Circuit Breaker."""
        if self._circuit_state == CircuitState.OPEN:
            # Проверяем, прошло ли время восстановления
            if time.time() - self._last_failure_time >= self._breaker_config.recovery_timeout:
                self._circuit_state = CircuitState.HALF_OPEN
                logger.info("Circuit Breaker: OPEN → HALF_OPEN (тестовый запрос)")
            else:
                raise LeyaLLMUnavailableError(
                    "Ollama недоступна (Circuit Breaker OPEN)",
                    context={
                        "state": self._circuit_state.value,
                        "failure_count": self._failure_count,
                        "recovery_timeout": self._breaker_config.recovery_timeout,
                    },
                )

    def _record_success(self) -> None:
        """Запись успешного запроса."""
        if self._circuit_state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._breaker_config.success_threshold:
                self._circuit_state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                logger.info("Circuit Breaker: HALF_OPEN → CLOSED (восстановление)")
        else:
            self._failure_count = 0

    def _record_failure(self, error: Exception) -> None:
        """Запись неудачного запроса."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._failure_count >= self._breaker_config.failure_threshold:
            self._circuit_state = CircuitState.OPEN
            logger.error(
                f"Circuit Breaker: → OPEN (неудач: {self._failure_count})",
                exc_info=False,
            )
        
        if self._circuit_state == CircuitState.HALF_OPEN:
            # Тестовый запрос не удался — возвращаемся в OPEN
            self._circuit_state = CircuitState.OPEN
            logger.error("Circuit Breaker: HALF_OPEN → OPEN (тест провален)")

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        require_json: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """