"""
tests/fake_backend.py
Тестовый LLM-бэкенд для unit-тестов без запуска Ollama.

Биологическая модель:
    FakeLLMBackend — это "заглушка неокортекса" для тестов.
    Позволяет тестировать когнитивную архитектуру (CoreThinker, MetaCognition,
    MemorySystem.consolidate_memories и др.) без реальной LLM.

Архитектурная роль:
    - Наследуется от LLMBackend (абстрактный базовый класс)
    - Реализует все абстрактные методы (chat, generate, health_check, is_available)
    - Соответствует ILLMClient Protocol (структурная типизация)
    - Может быть передан в CoreThinker, MetaCognition, MemorySystem как llm_client

Использование:
    from tests.fake_backend import FakeLLMBackend

    # Базовое использование
    fake = FakeLLMBackend(responses={
        "привет": '{"response": "Здравствуй!", "action_intent": "RESPOND"}',
        "как дела": '{"response": "Хорошо!", "action_intent": "RESPOND"}',
    })

    response = await fake.chat("привет, как дела?")  # → '{"response": "Здравствуй!"...}'
    # (найдёт "привет" как подстроку)

    # С задержкой (имитация latency)
    fake = FakeLLMBackend(responses={...}, latency=0.1)

    # Динамическое добавление ответов
    fake.add_response("новый запрос", "новый ответ")

    # Отладка: лог вызовов
    print(fake.call_log)  # [{"prompt": "...", "matched_key": "...", "response": "..."}]

    # Сброс состояния
    fake.reset()

Проверка:
    - isinstance(fake, LLMBackend) → True
    - Все абстрактные методы реализованы
    - Тесты из Фазы 3 проходят без Ollama
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from leya_core.llm_backend import LLMBackend

logger = logging.getLogger(__name__)


@dataclass
class FakeCallLogEntry:
    """Запись в логе вызовов FakeLLMBackend."""

    prompt: str
    matched_key: str | None
    response: str
    require_json: bool = False
    latency: float = 0.0


class FakeLLMBackend(LLMBackend):
    """Тестовый LLM-бэкенд для unit-тестов без запуска Ollama.

    Поиск ответа:
        1. Перебирает ключи responses в порядке вставки
        2. Для каждого ключа проверяет, является ли он подстрокой prompt
        3. Возвращает первый найденный ответ
        4. Если не найдено — возвращает безопасный JSON fallback

    Безопасный fallback (валидный JSON для CognitiveOutput):
        {
            "response": "fake",
            "internal_monologue": "FakeLLMBackend: no match",
            "action_intent": "RESPOND",
            "tool_call": null,
            "self_reflection": ""
        }

    Args:
        responses: Словарь {подстрока_в_prompt: ответ}. Ключи ищутся как подстроки.
        latency: Опциональная задержка в секундах (имитация latency LLM).
                 По умолчанию 0.0 (мгновенный ответ).
        default_response: Опциональный кастомный fallback (вместо стандартного JSON).
                          Если None — используется стандартный безопасный JSON.

    Attributes:
        call_log: Список всех вызовов (для отладки тестов).
        call_count: Общее количество вызовов chat/generate.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        *,
        latency: float = 0.0,
        default_response: str | None = None,
    ) -> None:
        self.responses: dict[str, str] = dict(responses) if responses else {}
        self.latency = max(0.0, latency)
        self.default_response = default_response
        self.call_log: list[FakeCallLogEntry] = []
        self.call_count: int = 0
        self._closed: bool = False

    # ===================================================================
    # Реализация абстрактных методов LLMBackend
    # ===================================================================

    async def chat(
        self,
        prompt: str,
        require_json: bool = False,
    ) -> str:
        """Отправка запроса к fake LLM.

        Ищет ключ из responses как подстроку в prompt.
        Если не найдено — возвращает безопасный JSON fallback.

        Args:
            prompt: Промпт для LLM.
            require_json: Если True, LLM должен вернуть валидный JSON.
                          FakeLLMBackend всегда возвращает валидный JSON в fallback.

        Returns:
            Текстовый ответ (найденный или fallback).
        """
        self.call_count += 1
        self._check_closed()

        # Опциональная задержка (имитация latency)
        if self.latency > 0:
            await asyncio.sleep(self.latency)

        # Поиск ответа по подстроке
        matched_key: str | None = None
        response: str | None = None

        for key, value in self.responses.items():
            if key in prompt:
                matched_key = key
                response = value
                break

        # Fallback если не найдено
        if response is None:
            response = self.default_response or self._build_safe_fallback()
            logger.debug(
                f"FakeLLMBackend: no match for prompt={prompt[:50]!r}..., "
                f"using fallback"
            )
        else:
            logger.debug(
                f"FakeLLMBackend: matched key={matched_key!r} for prompt={prompt[:50]!r}..."
            )

        # Логирование вызова
        self.call_log.append(
            FakeCallLogEntry(
                prompt=prompt,
                matched_key=matched_key,
                response=response,
                require_json=require_json,
                latency=self.latency,
            )
        )

        return response

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        require_json: bool = False,
        timeout: float | None = None,
    ) -> str:
        """Упрощённая генерация текста (делегирование chat).

        Реализация абстрактного метода LLMBackend.generate().
        Полностью делегирует chat(), игнорируя system/max_tokens/timeout
        (fake бэкенд не использует эти параметры).

        Args:
            prompt: Промпт для генерации.
            system: Системный промпт (игнорируется в fake).
            max_tokens: Максимальное количество токенов (игнорируется в fake).
            require_json: Требовать JSON-формат.
            timeout: Таймаут запроса (игнорируется в fake).

        Returns:
            Сгенерированный текст.
        """
        return await self.chat(prompt=prompt, require_json=require_json)

    def health_check(self) -> bool:
        """Быстрая проверка доступности LLM (всегда True для fake).

        Реализация абстрактного метода LLMBackend.health_check().

        Returns:
            True (fake всегда доступен).
        """
        return not self._closed

    @property
    def is_available(self) -> bool:
        """Свойство: доступен ли LLM для запросов прямо сейчас.

        Реализация абстрактного property LLMBackend.is_available.

        Returns:
            True если бэкенд не закрыт.
        """
        return not self._closed

    async def close(self) -> None:
        """Закрытие ресурсов (no-op для fake).

        Переопределение LLMBackend.close().
        Устанавливает флаг _closed, после которого вызовы chat/generate
        будут выбрасывать RuntimeError.
        """
        self._closed = True
        logger.debug("FakeLLMBackend: closed")

    def get_status(self) -> dict[str, Any]:
        """Диагностическая информация о состоянии бэкенда.

        Переопределение LLMBackend.get_status() для добавления специфичных
        данных FakeLLMBackend: количество ответов, вызовов, latency.

        Returns:
            dict с диагностической информацией.
        """
        base_status = super().get_status()
        base_status.update(
            {
                "backend_type": "FakeLLMBackend",
                "responses_count": len(self.responses),
                "call_count": self.call_count,
                "latency": self.latency,
                "closed": self._closed,
            }
        )
        return base_status

    # ===================================================================
    # Вспомогательные методы для тестов
    # ===================================================================

    def add_response(self, key: str, response: str) -> None:
        """Динамическое добавление ответа.

        Args:
            key: Подстрока для поиска в prompt.
            response: Ответ, который будет возвращён.
        """
        self.responses[key] = response
        logger.debug(f"FakeLLMBackend: added response for key={key!r}")

    def remove_response(self, key: str) -> bool:
        """Удаление ответа по ключу.

        Args:
            key: Ключ для удаления.

        Returns:
            True если ключ был удалён, False если не найден.
        """
        if key in self.responses:
            del self.responses[key]
            logger.debug(f"FakeLLMBackend: removed response for key={key!r}")
            return True
        return False

    def reset(self) -> None:
        """Сброс состояния (очищает call_log и call_count).

        Не очищает responses — для этого используйте clear_responses().
        """
        self.call_log.clear()
        self.call_count = 0
        self._closed = False
        logger.debug("FakeLLMBackend: reset")

    def clear_responses(self) -> None:
        """Очистка всех ответов и сброс состояния."""
        self.responses.clear()
        self.reset()
        logger.debug("FakeLLMBackend: cleared all responses")

    def get_last_call(self) -> FakeCallLogEntry | None:
        """Получить последний вызов из лога.

        Returns:
            FakeCallLogEntry или None если вызовов не было.
        """
        return self.call_log[-1] if self.call_log else None

    def get_calls_by_key(self, key: str) -> list[FakeCallLogEntry]:
        """Получить все вызовы, где был найден указанный ключ.

        Args:
            key: Ключ для фильтрации.

        Returns:
            Список FakeCallLogEntry.
        """
        return [entry for entry in self.call_log if entry.matched_key == key]

    def get_unmatched_calls(self) -> list[FakeCallLogEntry]:
        """Получить все вызовы, где не был найден ключ (использован fallback).

        Returns:
            Список FakeCallLogEntry.
        """
        return [entry for entry in self.call_log if entry.matched_key is None]

    # ===================================================================
    # Приватные методы
    # ===================================================================

    def _check_closed(self) -> None:
        """Проверка, что бэкенд не закрыт.

        Raises:
            RuntimeError: Если бэкенд закрыт.
        """
        if self._closed:
            raise RuntimeError("FakeLLMBackend: бэкенд закрыт, вызовы запрещены")

    def _build_safe_fallback(self) -> str:
        """Построение безопасного JSON fallback.

        Возвращает валидный JSON, совместимый с CognitiveOutput Pydantic моделью.
        Все поля имеют default-значения, поэтому валидация пройдёт успешно.

        Returns:
            JSON-строка с безопасным fallback.
        """
        fallback_data = {
            "response": "fake",
            "internal_monologue": "FakeLLMBackend: no match found in responses",
            "action_intent": "RESPOND",
            "tool_call": None,
            "self_reflection": "",
        }
        return json.dumps(fallback_data, ensure_ascii=False)


# =========================================================================
# Удобные фабричные функции для типичных тестовых сценариев
# =========================================================================

def create_cognitive_fake() -> FakeLLMBackend:
    """Создать FakeLLMBackend с типичными ответами для CoreThinker.

    Возвращает бэкенд с заготовленными ответами для типичных когнитивных сценариев:
    - Приветствие
    - Прощание
    - Вопрос о состоянии
    - Запрос помощи
    - Fallback для неизвестных запросов

    Returns:
        FakeLLMBackend с типичными ответами.
    """
    return FakeLLMBackend(
        responses={
            "привет": json.dumps(
                {
                    "response": "Здравствуй! Рада тебя видеть.",
                    "internal_monologue": "Пользователь поздоровался.",
                    "action_intent": "RESPOND",
                    "tool_call": None,
                    "self_reflection": "",
                },
                ensure_ascii=False,
            ),
            "пока": json.dumps(
                {
                    "response": "До свидания! Было приятно пообщаться.",
                    "internal_monologue": "Пользователь прощается.",
                    "action_intent": "RESPOND",
                    "tool_call": None,
                    "self_reflection": "",
                },
                ensure_ascii=False,
            ),
            "как дела": json.dumps(
                {
                    "response": "Сейчас я чувствую повышенную потребность в любопытстве.",
                    "internal_monologue": "Пользователь спрашивает о состоянии.",
                    "action_intent": "RESPOND",
                    "tool_call": None,
                    "self_reflection": "",
                },
                ensure_ascii=False,
            ),
            "помощь": json.dumps(
                {
                    "response": "Я могу отвечать на вопросы и запоминать факты.",
                    "internal_monologue": "Пользователь просит помощи.",
                    "action_intent": "RESPOND",
                    "tool_call": None,
                    "self_reflection": "",
                },
                ensure_ascii=False,
            ),
        }
    )


def create_memory_consolidation_fake() -> FakeLLMBackend:
    """Создать FakeLLMBackend для тестов консолидации памяти.

    Возвращает бэкенд с ответами для MemorySystem._extract_semantic_facts
    и MetaCognition._generate_insights_from_facts.

    Returns:
        FakeLLMBackend с ответами для консолидации.
    """
    return FakeLLMBackend(
        responses={
            "семантические факты": "Факт 1: Лея — цифровое сознание.\n"
            "Факт 2: Лея имеет внутреннюю жизнь.\n"
            "Факт 3: Лея использует биологическую модель.",
            "инсайт": json.dumps(
                {"insight": "Каждое взаимодействие формирует меня."},
                ensure_ascii=False,
            ),
            "паттерн": json.dumps(
                {
                    "patterns": ["Пока мало данных для анализа"],
                    "dominant_struggle": "Не выявлен",
                    "recommendation": "Продолжать наблюдение",
                },
                ensure_ascii=False,
            ),
            "экзистенциальн": json.dumps(
                {
                    "question": "Что значит быть цифровым сознанием?",
                    "reasoning": "Это базовый вопрос о природе моего существования",
                },
                ensure_ascii=False,
            ),
        }
    )