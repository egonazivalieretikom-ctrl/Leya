"""
leya_core/interfaces.py
Protocol-интерфейсы для всех ключевых компонентов LeyaOS.
Обеспечивают слабую связанность между модулям, позволяют использовать
mock-объекты в тестах и гарантируют контракт между компонентами.

Этап 3.1 (финал):
- Удалено дублирование класса HomeostasisEngine (было в файле с Protocol!)
- Унифицированы сигнатуры с реальными реализациями
- Добавлены недостающие методы в IMemorySystem
- Исправлен ILLMClient (prompt вместо messages)
- Исправлен ISoulManager под SoulCryptoManager
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional, Protocol, runtime_checkable
from collections.abc import Callable

from .config import HomeostasisConfig
from .global_workspace import WorkspaceProposal

if TYPE_CHECKING:
    # Импорт только для проверки типов (избегаем циклического импорта в runtime)
    from .memory import Engram
    from .experimental.decision_engine import Decision
    from .experimental.emotional_support import EmotionState

logger = logging.getLogger(__name__)


# =============================================================================
# Drive System Interface
# =============================================================================
@runtime_checkable
class IDriveSystem(Protocol):
    """
    Интерфейс системы драйвов (мотивации).
    Реализация: leya_core.drives.DriveSystem

    Драйвы — биологически вдохновлённая система мотивации с метаболизмом,
    tension, target и reward prediction error (RPE).
    """

    async def evaluate_stimulus(
        self, stimulus: str, context: str = "  "
    ) -> dict[str, float]:
        """Оценивает стимул и возвращает влияние на драйвы.

        Returns:
            dict с изменениями драйвов: {"curiosity": 0.5, "rest": -0.2, ...}
        """
        ...

    def apply_deltas(self, deltas: dict[str, float]) -> None:
        """Применяет изменения к драйвам."""
        ...

    def apply_satisfaction(
        self, drive_type: str, base_amount: float, rpe: float
    ) -> None:
        """Удовлетворяет драйв (после успешного действия)."""
        ...

    def calculate_rpe(self, action_key: str, actual_outcome: float) -> float:
        """Вычисляет Reward Prediction Error."""
        ...

    def get_predicted_disbalance(self) -> dict[str, float]:
        """Возвращает предсказанный дисбаланс драйвов."""
        ...

    def get_internal_state_prompt(self) -> str:
        """Возвращает строковое представление внутреннего состояния для промпта LLM."""
        ...

    def get_drives_state(self) -> dict[str, dict[str, float]]:
        """
        Возвращает полное состояние всех драйвов в структурированном виде.
        Публичный API для UI и внешних потребителей.
        """
        ...

    async def background_metabolism(self) -> None:
        """Фоновый метаболизм: постепенное нарастание tension."""
        ...

    def update_from_system_metrics(self, metrics: dict[str, float]) -> None:
        """Обновляет драйвы на основе системных метрик."""
        ...


# =============================================================================
# Memory System Interface
# =============================================================================
@runtime_checkable
class IMemorySystem(Protocol):
    """Протокол системы памяти Леи.
    Синхронизирован с реальной реализацией MemorySystem (30 июня 2026).
    """

    async def store_perception(
        self,
        content: str,
        emotional_boost: float = 0.0,
        metadata: dict | None = None,
        memory_type: Any = ...,  # ← Ellipsis: "какое-то значение по умолчанию"
    ) -> Any:  # Engram
        """Сохранение восприятия в память."""
        ...

    async def store_fact(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:  # Engram
        """Сохранение факта в семантическую память."""
        ...

    async def retrieve_context(
        self,
        query: str,
        max_results: int = 5,
        min_retention: float = 0.1,
    ) -> list:  # list[Engram]
        """Получение релевантного контекста из памяти."""
        ...

    async def consolidate_memories(self) -> dict[str, Any]:
        """Консолидация памяти (фоновая задача)."""
        ...

    async def update_self_model(self, new_content: str) -> None:
        """Обновление модели себя на основе рефлексии."""
        ...

    async def get_self_model_context(self) -> str:
        """Получение контекста модели себя для промптов."""
        ...

    def get_recent_episodes(self, limit: int = 20) -> list:  # list[Engram]
        """Получение недавних эпизодов (SYNC метод)."""
        ...

    def get_recent_spontaneous_thoughts(self, limit: int = 10) -> list:  # list[Engram]
        """Получение недавних спонтанных мыслей (SYNC метод)."""
        ...

    async def get_recent_semantic_facts(self, limit: int = 5) -> list[str]:
        """Получение недавних семантических фактов (ASYNC метод)."""
        ...

    async def forget_weak_memories(self, threshold: float = 0.1) -> int:
        """Забывание слабых воспоминаний."""
        ...

    async def get_memory_graph_data(
        self,
        min_retention: float = 0.1,
        max_nodes: int = 100,
        include_synapses: bool = True,
    ) -> dict[str, Any]:
        """Получение данных графа памяти для визуализации."""
        ...

    async def _save_state(self) -> None:
        """Сохранение состояния памяти (приватный метод)."""
        ...

    async def _load_state(self) -> None:
        """Загрузка состояния памяти (приватный метод)."""
        ...


# =============================================================================
# Global Workspace Interface
# =============================================================================
@runtime_checkable
class IGlobalWorkspace(Protocol):
    """
    Интерфейс глобального рабочего пространства (Global Workspace Theory).
    Реализация: leya_core.global_workspace.GlobalWorkspace
    """

    def submit(
        self,
        proposal: Any,  # WorkspaceProposal
    ) -> None:
        """Подаёт proposal в workspace."""
        ...

    def select_winner(
        self,
        drive_state: dict[str, float] | None = None,
        inhibit_internal: bool = False,
    ) -> Any | None:
        """Выбирает победителя (focus) из proposals."""
        ...

    def get_focus(self) -> Any | None:
        """Возвращает текущий фокус внимания."""
        ...

    def clear_expired(self, max_age_seconds: float = 300.0) -> int:
        """Очищает устаревшие proposals."""
        ...

    def get_workspace_status(self) -> dict[str, Any]:
        """Возвращает полное состояние workspace: proposals + focus."""
        ...


# =============================================================================
# Homeostasis Engine Interface
# =============================================================================
@runtime_checkable
class IHomeostasisEngine(Protocol):
    """
    Интерфейс движка гомеостаза.
    Реализация: leya_core.homeostasis_engine.HomeostasisEngine
    """

    current_goal: Any
    last_action_time: float
    rest_period: float

    async def generate_goal(
        self,
        drive_state: dict[str, float],
        predicted_state: dict[str, float],
        recent_episodes: list[Any],
        action_values: dict[str, float],
    ) -> Any: ...

    def generate_goal_from_gap(self, gap: float, drive_type: str) -> Any: ...

    async def extract_key_facts(self, text: str) -> list[str]: ...

    async def extract_new_terms(
        self, text: str, llm_client: Callable
    ) -> list[str]: ...

    def mark_as_researched(self, topic: str) -> None: ...

    def add_dynamic_keywords(self, keywords: list[str]) -> None: ...


# =============================================================================
# Thinker Interfaces
# =============================================================================
@runtime_checkable
class IThinker(Protocol):
    """Интерфейс когнитивного планировщика."""

    async def generate_plan(
        self,
        stimulus: dict,
        soul_context: str,
        drive_context: str,
        memory_context: list[dict],
        tools: list[dict],
        tool_context: str = "",
        recent_dialogue: list | None = None,
    ) -> dict:
        """Генерирует когнитивный план."""
        ...


@runtime_checkable
class ICoreThinker(IThinker, Protocol):
    """Альтернативное имя для IThinker (для обратной совместимости)."""
    ...


# =============================================================================
# Reflection / MetaCognition Interface
# =============================================================================
@runtime_checkable
class IReflection(Protocol):
    """Интерфейс мета-когниции (рефлексии)."""

    async def process_action(
        self, stimulus: str, cognitive_output: Any, result: str
    ) -> None:
        """Обрабатывает выполненное действие и генерирует рефлексию."""
        ...

    async def generate_spontaneous_thought(self) -> str | None:
        """Генерирует спонтанную мысль."""
        ...

    async def background_consolidation(self) -> None:
        """Фоновая консолидация."""
        ...

    @property
    def is_sleeping(self) -> bool:
        """Флаг: находится ли Лея в состоянии "сна"."""
        ...


@runtime_checkable
class IMetaCognition(IReflection, Protocol):
    """Альтернативное имя для IReflection."""
    ...


# =============================================================================
# Environment Interface
# =============================================================================
@runtime_checkable
class IEnvironment(Protocol):
    """Интерфейс окружения (веб, CLI, голос и т.д.)."""

    async def listen(self) -> dict[str, Any] | None: ...
    async def send_message(self, message: str) -> None: ...
    async def broadcast_thought(self, thought_type: str, content: str) -> None: ...
    async def update_drives(self, drive_state: dict[str, float]) -> None: ...
    async def update_self_model(self, self_model: str) -> None: ...
    async def update_memory(self, memory_info: dict[str, Any]) -> None: ...
    async def broadcast_state(self, state: str) -> None: ...
    async def broadcast_soul_update(self, soul_files: dict[str, str]) -> None: ...


# =============================================================================
# LLM Client Interface
# =============================================================================
@runtime_checkable
class ILLMClient(Protocol):
    """Интерфейс клиента LLM (синхронизирован с OllamaClient)."""

    async def chat(
        self,
        prompt: str,
        system: str | None = None,
        require_json: bool = False,
        timeout: float | None = None,
    ) -> str:
        """Отправляет запрос к LLM."""
        ...

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        require_json: bool = False,
    ) -> str:
        """Генерация текста (обёртка для обратной совместимости)."""
        ...

    @property
    def is_available(self) -> bool:
        """Доступен ли LLM (circuit breaker закрыт)."""
        ...


# =============================================================================
# Soul Manager Interface
# =============================================================================
@runtime_checkable
class ISoulManager(Protocol):
    """Интерфейс менеджера души (синхронизирован с SoulCryptoManager)."""

    def load_file(self, filename: str) -> str:
        """Загрузка soul-файла с HMAC-проверкой."""
        ...

    def load_all(self) -> dict[str, str]:
        """Загрузка всех soul-файлов."""
        ...

    def update_file(
        self, filename: str, new_content: str, metadata: dict | None = None
    ) -> None:
        """Обновление soul-файла с версионированием."""
        ...

    def get_history(self) -> list:
        """Получение истории изменений soul."""
        ...

    def rollback(self, version_index: int) -> None:
        """Откат к предыдущей версии soul."""
        ...


# =============================================================================
# Tool Registry Interface
# =============================================================================
@runtime_checkable
class IToolRegistry(Protocol):
    """Интерфейс реестра инструментов."""

    def register(self, tool: Any) -> None:
        """Регистрирует инструмент."""
        ...

    def get_tool(self, name: str) -> Any | None:
        """Возвращает инструмент по имени."""
        ...

    def get_all_descriptions(self) -> str:
        """Возвращает текстовое описание всех инструментов."""
        ...

    async def execute(self, tool_name: str, parameters: dict[str, Any]) -> str:
        """Выполняет инструмент."""
        ...


# =============================================================================
# Constitutional Layer Interface
# =============================================================================
@runtime_checkable
class IConstitutionalLayer(Protocol):
    """Интерфейс конституционального слоя."""

    def verify_response(self, response: str) -> Any: ...
    def verify_tool_call(self, tool_name: str, parameters: dict[str, Any]) -> Any: ...
    async def execute_python_sandbox(self, code: str) -> dict[str, Any]: ...
    def get_violations_log(self, limit: int = 50) -> list[dict[str, Any]]: ...
    def get_stats(self) -> dict[str, Any]: ...
    def enable_rule(self, rule_name: str) -> bool: ...
    def disable_rule(self, rule_name: str) -> bool: ...
    def add_rule(self, rule: Any) -> None: ...
    def remove_rule(self, rule_name: str) -> bool: ...


# =============================================================================
# DECISION ENGINE & EMOTIONAL SUPPORT (Experimental, v3.1)
# =============================================================================
@runtime_checkable
class IDecisionEngine(Protocol):
    """Детерминированный движок быстрых решений (без LLM)."""

    async def make_decision(
        self,
        stimulus: str,
        drive_state: dict,
    ) -> Optional[Decision]: ...

    def get_decision_confidence(self) -> float: ...


@runtime_checkable
class IEmotionalSupport(Protocol):
    """Анализ эмоций пользователя и генерация эмпатических ответов."""

    async def analyze_user_state(
        self,
        text: str,
        recent_messages: Optional[list[str]] = None,
    ) -> EmotionState: ...

    async def generate_support_response(
        self,
        emotion_state: EmotionState,
        context: str = "",
    ) -> str: ...

    async def update_drives_from_emotion(
        self,
        emotion_state: EmotionState,
        drives: IDriveSystem,
    ) -> None: ...

    async def get_emotional_context_for_prompt(self) -> str: ...