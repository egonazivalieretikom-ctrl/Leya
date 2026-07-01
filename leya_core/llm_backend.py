"""
leya_core/llm_backend.py
Абстрактный базовый класс для всех LLM-бэкендов.

Биологическая модель:
    LLMBackend — это "неокортекс" Леи, абстрагированный от конкретного провайдера.
    Конкретные реализации (OllamaClient, будущий OpenAIClient, AnthropicClient)
    наследуются от этого класса и обязаны реализовать все абстрактные методы.

Архитектурная роль:
    - LLMBackend (ABC) — базовый класс для наследования (номинальная типизация).
      Гарантирует наличие методов на уровне класса через @abstractmethod.
    - ILLMClient (Protocol) — интерфейс для структурной проверки (duck typing).
      Позволяет использовать mock-объекты в тестах без наследования.
    - OllamaClient наследуется от LLMBackend И автоматически соответствует
      ILLMClient Protocol (благодаря совпадению сигнатур методов).

Защита от ошибок:
    - Попытка инстанцировать LLMBackend() напрямую вызывает TypeError.
    - Наследник, не реализовавший все абстрактные методы, также не может
      быть инстанцирован (TypeError при попытке создания объекта).
    - Это предотвращает "частично реализованные" бэкенды, которые падают
      в runtime при вызове забытого метода.

Использование:
    class OllamaClient(LLMBackend):
        async def chat(self, prompt: str, require_json: bool = False) -> str:
            ...
        async def generate(self, prompt: str) -> str:
            ...
        def health_check(self) -> bool:
            ...
        @property
        def is_available(self) -> bool:
            ...

    client = OllamaClient(...)  # OK
    backend = LLMBackend()      # TypeError: Can't instantiate abstract class
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMBackend(ABC):
    """Абстрактный базовый класс для всех LLM-бэкендов Леи.

    Все конкретные реализации (Ollama, OpenAI, Anthropic и др.) должны
    наследоваться от этого класса и реализовать все абстрактные методы.

    Raises:
        TypeError: При попытке инстанцировать LLMBackend напрямую или
                   создать наследника, не реализовавшего все абстрактные методы.
    """

    # ===================================================================
    # Абстрактные методы — ОБЯЗАТЕЛЬНЫ для реализации в наследниках
    # ===================================================================

    @abstractmethod
    async def chat(
        self,
        prompt: str,
        require_json: bool = False,
    ) -> str:
        """Отправка запроса к LLM и получение текстового ответа.

        Это основной метод взаимодействия с LLM. Реализация должна:
        - Учитывать Circuit Breaker (если есть)
        - Обрабатывать таймауты и сетевые ошибки
        - Поддерживать require_json для структурированных ответов
        - Возвращать строку (сырой текст ответа LLM)

        Args:
            prompt: Промпт для LLM
            require_json: Если True, LLM должен вернуть валидный JSON.
                          Реализация может добавить "format": "json" в payload.

        Returns:
            Текстовый ответ LLM (сырая строка, без парсинга).

        Raises:
            LeyaLLMError: Базовое исключение для ошибок LLM.
            LeyaLLMTimeoutError: Таймаут запроса.
            LeyaLLMConnectionError: Ошибка соединения.
            LeyaLLMUnavailableError: LLM недоступен (Circuit Breaker open).
            LeyaJSONParseError: LLM вернул невалидный JSON при require_json=True.
        """
        ...

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        require_json: bool = False,
        timeout: float | None = None,
    ) -> str:
        """Упрощённая генерация текста (обёртка над chat).

        Используется там, где не требуется сложная логика chat
        (например, для извлечения семантических фактов из эпизодов
        в MemorySystem._extract_semantic_facts).

        Сигнатура расширена для совместимости с OllamaBackend.generate(),
        который поддерживает max_tokens, require_json и timeout.
        Наследники могут игнорировать необязательные параметры, но
        обязаны принять их для совместимости интерфейса.

        Реализация по умолчанию может делегировать chat():
            async def generate(self, prompt: str, **kwargs) -> str:
                return await self.chat(prompt, require_json=False)

        Args:
            prompt: Промпт для генерации.
            system: Системный промпт (опционально).
            max_tokens: Максимальное количество токенов в ответе.
            require_json: Требовать JSON-формат ответа.
            timeout: Таймаут запроса.

        Returns:
            Сгенерированный текст.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Быстрая проверка доступности LLM (синхронная).

        Используется для диагностики и мониторинга. Не должна делать
        реальный запрос к LLM (это дорого) — достаточно проверки
        состояния Circuit Breaker или последнего известного статуса.

        Returns:
            True если LLM доступен для запросов, False иначе.
        """
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Свойство: доступен ли LLM для запросов прямо сейчас.

        Алиас для health_check(), но как property для удобства:
            if client.is_available:
                response = await client.chat(prompt)

        Returns:
            True если Circuit Breaker в состоянии CLOSED или HALF_OPEN,
            False если OPEN.
        """
        ...

    # ===================================================================
    # Опциональные методы с реализацией по умолчанию
    # ===================================================================

    async def close(self) -> None:
        """Закрытие ресурсов (HTTP-сессии, соединения).

        Реализация по умолчанию — no-op. Наследники могут переопределить
        для корректного освобождения ресурсов (например, aiohttp.ClientSession).

        Вызывается из LeyaOS.shutdown() при graceful shutdown.
        """
        pass

    def get_status(self) -> dict:
        """Диагностическая информация о состоянии бэкенда.

        Реализация по умолчанию возвращает базовую информацию.
        Наследники могут переопределить для добавления специфичных данных
        (Circuit Breaker status, failure count, last failure time и т.д.).

        Returns:
            dict с диагностической информацией.
        """
        return {
            "backend_type": self.__class__.__name__,
            "is_available": self.is_available,
        }

    async def __aenter__(self) -> "LLMBackend":
        """Поддержка async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Закрытие ресурсов при выходе из context manager."""
        await self.close()