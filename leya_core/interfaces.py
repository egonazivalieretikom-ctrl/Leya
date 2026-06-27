"""
leya_core/interfaces.py
Protocol-интерфейсы для всех ключевых компонентов LeyaOS.

Обеспечивают слабую связанность между модулями, позволяют использовать
mock-объекты в тестах и гарантируют контракт между компонентами.

Шаг 3: Добавлены методы get_drives_state(), get_memory_graph_data(), get_workspace_status()
для устранения прямого доступа к internals из web_interface/server.py.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from .models import Engram, Synapse  # Адаптируйте импорт под ваш пакет

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

    async def evaluate_stimulus(self, stimulus: str, context: str = " ") -> dict[str, float]:
        """
        Оценивает стимул и возвращает влияние на драйвы.

        Args:
            stimulus: Входной стимул (сообщение, событие и т.д.)

        Returns:
            dict с изменениями драйвов: {"CURIOSITY": 0.5, "REST": -0.2, ...}
        """
        ...

    def apply_deltas(self, deltas: dict[str, float]) -> None:
        """
        Применяет изменения к драйвам.

        Args:
            deltas: Изменения драйвов от evaluate_stimulus
        """
        ...

    def apply_satisfaction(self, drive_type: str, base_amount: float, rpe: float) -> None:
        """
        Удовлетворяет драйв (после успешного действия).

        Args:
            drive_type: Тип драйва (например, "CURIOSITY")
            amount: Количество удовлетворения
        """
        ...

    def calculate_rpe(self, action_key: str, actual_outcome: float) -> float:
        """
        Вычисляет Reward Prediction Error.

        Args:
            drive_type: Тип драйва
            actual_reward: Фактическое вознаграждение

        Returns:
            RPE (разница между предсказанным и фактическим)
        """
        ...

    def get_predicted_disbalance(self) -> dict[str, float]:
        """
        Возвращает предсказанный дисбаланс драйвов.

        Returns:
            dict с предсказанными значениями дисбаланса
        """
        ...

    def get_internal_state_prompt(self) -> str:
        """
        Возвращает строковое представление внутреннего состояния для промпта LLM.

        Returns:
            Строка с описанием текущего состояния драйвов
        """
        ...

    def get_drives_state(self) -> dict[str, dict[str, float]]:
        """
        Возвращает полное состояние всех драйвов в структурированном виде.
        Публичный API для UI и внешних потребителей.

        Returns:
            dict вида:
            {
                "CURIOSITY": {
                    "current": 0.5,
                    "tension": 0.3,
                    "target": 0.8,
                    "satisfaction": 0.0
                },
                ...
            }
        """
        ...

    async def background_metabolism(self) -> None:
        """
        Фоновый метаболизм: постепенное нарастание tension.
        Запускается как asyncio задача.
        """
        ...

    def update_from_system_metrics(self, metrics: dict[str, float]) -> None:
        """
        Обновляет драйвы на основе системных метрик (CPU, memory и т.д.).

        Args:
            metrics: Системные метрики
        """
        ...


# =============================================================================
# Memory System Interface
# =============================================================================


@runtime_checkable
class IMemorySystem(Protocol):
    """
    Интерфейс системы памяти.
    Реализация: leya_core.memory.MemorySystem

    Биологически вдохновлённая память с энграммами, синапсами,
    забыванием по Эббингаузу, консолидацией и LTP/LTD-подобными механизмами.
    """

    async def store_perception(
        self, content: str, emotional_boost: float=0.0, metadata: dict[str, Any] | None=None
    ) -> Engram: ...

    async def retrieve_context(
    self, query: str, max_results: int = 5, min_retention: float = 0.1
    ) -> list[Engram]: ...

    async def store_fact(self, content: str, metadata: dict[str, Any] | None=None) -> Engram: ...

    async def consolidate_memories(self) -> dict[str, Any]: ...

    async def get_self_model_context(self) -> str: ...

    async def get_self_model_context(self) -> str: ...

    async def get_recent_spontaneous_thoughts(self, limit: int = 10) -> list[Engram]: ...

    async def get_recent_episodes(self, limit: int=10) -> list[Engram]: ...

    async def forget_weak_memories(self, threshold: float = 0.1) -> int:
        """
        Удаляет энграммы с retention_strength ниже порога.

        Args:
            threshold: Порог retention_strength

        Returns:
            Количество удалённых энграмм
        """
        ...

    async def get_memory_graph_data(
        self,
        min_retention: float = 0.1,
        max_nodes: int = 100,
        include_synapses: bool = True,
    ) -> dict[str, Any]:
        """
        Возвращает данные для визуализации графа памяти.

        Args:
            min_retention: Минимальный retention_strength для включения узла
            max_nodes: Максимальное количество узлов в графе
            include_synapses: Включать ли рёбра (synapses)

        Returns:
            {
                "nodes": list[dict],
                "edges": list[dict],
                "total_engrams": int,
                "total_synapses": int,
            }
        """
        ...

    async def _save_state(self) -> None:
        """
        Атомарное сохранение состояния памяти (engrams, synapses, self_model)
        в JSON с HMAC-подписью.
        """
        ...

    async def _load_state(self) -> None:
        """
        Загрузка состояния памяти из JSON с проверкой HMAC и версии.
        При отсутствии файла — инициализация пустого состояния.
        """
        ...


# =============================================================================
# Global Workspace Interface
# =============================================================================


@runtime_checkable
class IGlobalWorkspace(Protocol):
    """
    Интерфейс глобального рабочего пространства (Global Workspace Theory).

    Реализация: leya_core.global_workspace.GlobalWorkspace

    Управляет конкуренцией proposals (от homeostasis, spontaneous thoughts, user)
    и выбором фокуса внимания.
    """

    def submit(
        self,
        source: str,
        content: str,
        action_type: str = "none",
        priority: str = "MEDIUM",
        urgency: float = 0.5,
        drive_relevance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """
        Подаёт proposal в workspace.

        Args:
            source: Источник proposal (homeostasis, spontaneous, user и т.д.)
            content: Содержание proposal
            action_type: Тип действия
            priority: Приоритет (LOW, MEDIUM, HIGH, CRITICAL)
            urgency: Срочность (0.0-1.0)
            drive_relevance: Релевантность драйвам (0.0-1.0)
            metadata: Дополнительные метаданные

        Returns:
            Созданный WorkspaceProposal
        """
        ...

    def select_winner(self) -> Any | None:
        """
        Выбирает победителя (focus) из proposals.

        Returns:
            WorkspaceProposal-победитель или None
        """
        ...

    def get_focus(self) -> Any | None:
        """
        Возвращает текущий фокус внимания.

        Returns:
            Текущий WorkspaceProposal или None
        """
        ...

    def clear_expired(self, max_age_seconds: float = 300.0) -> int:
        """
        Очищает устаревшие proposals.

        Args:
            max_age_seconds: Максимальный возраст proposal в секундах

        Returns:
            Количество удалённых proposals
        """
        ...

    def get_workspace_status(self) -> dict[str, Any]:
        """
        Возвращает полное состояние workspace: proposals + focus.
        Публичный API для UI.

        Returns:
            dict с ключами:
                "proposals": list[dict]
                "focus": dict | None
                "total": int
        """
        ...


# =============================================================================
# Homeostasis Engine Interface
# =============================================================================


@runtime_checkable
class IHomeostasisEngine(Protocol):
    """
    Интерфейс движка гомеостаза.
    Реализация: leya_core.homeostasis_engine.HomeostasisEngine

    Автономная генерация целей на основе дисбаланса драйвов,
    предсказанного состояния и недавних эпизодов.
    """

    # Атрибуты состояния (в реализации это обычные поля экземпляра, а не @property)
    current_goal: dict[str, Any] | None
    last_action_time: float

    async def generate_goal(
        self,
        drive_state: dict[str, float],
        predicted_state: dict[str, float],
        recent_episodes: list[Engram],
        action_values: dict[str, float],
    ) -> dict[str, Any]: ...

    def generate_goal_from_gap(self, gap: float, drive_type: str) -> dict[str, Any]: ...
    async def extract_key_facts(self, text: str) -> list[str]: ...
    async def extract_new_terms(self, text: str) -> list[str]: ...

    def mark_as_researched(self, topic: str) -> None: ...

    def add_dynamic_keywords(self, keywords: list[str]) -> None: ...

    @property
    def current_goal(self) -> dict[str, Any] | None: ...
    @property
    def last_action_time(self) -> float: ...
    @property
    def rest_period(self) -> float: ...

# =============================================================================
# Thinker Interfaces
# =============================================================================


@runtime_checkable
class IThinker(Protocol):
    """
    Интерфейс когнитивного планировщика.

    Реализация: leya_core.thinker.CoreThinker
    """

    async def generate_plan(
        self,
        stimulus: Any,
        drive_state: str,
        memory_context: str,
        self_model: str,
        tools: list[dict[str, Any]] | None = None,
        tool_context: str | None = None,
    ) -> Any:
        """Генерирует когнитивный план."""
        ...


@runtime_checkable
class ICoreThinker(IThinker, Protocol):
    """
    Альтернативное имя для IThinker (для обратной совместимости с тестами и LeyaOS).
    """

    ...


# =============================================================================
# Reflection / MetaCognition Interface
# =============================================================================


@runtime_checkable
class IReflection(Protocol):
    """
    Интерфейс мета-когниции (рефлексии).

    Реализация: leya_core.reflection.MetaCognition
    """

    async def process_action(self, action: dict[str, Any]) -> str | None:
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
    """
    Альтернативное имя для IReflection (для обратной совместимости с тестами и LeyaOS).
    """

    ...


# =============================================================================
# Environment Interface
# =============================================================================


@runtime_checkable
class IEnvironment(Protocol):
    """Интерфейс окружения (веб, CLI, голос и т.д.)."""

    async def listen(self) -> dict[str, Any] | None:
        """Слушает входные сообщения/стимулы."""
        ...

    async def send_message(self, message: str) -> None:
        """Отправляет сообщение пользователю/внешнему миру."""
        ...

    async def broadcast_thought(self, thought_type: str, content: str) -> None:
        """Транслирует мысль (для UI)."""
        ...

    async def update_drives(self, drive_state: dict[str, float]) -> None:
        """Обновляет состояние драйвов (для UI)."""
        ...

    async def update_self_model(self, self_model: str) -> None:
        """Обновляет само-модель (для UI)."""
        ...

    async def update_memory(self, memory_info: dict[str, Any]) -> None:
        """Обновляет информацию о памяти (для UI)."""
        ...

    async def broadcast_state(self, state: str) -> None:
        """Транслирует состояние Леи (для UI)."""
        ...

    async def broadcast_soul_update(self, soul_files: dict[str, str]) -> None:
        """Транслирует обновление файлов души (для UI)."""
        ...


# =============================================================================
# LLM Client Interface
# =============================================================================


@runtime_checkable
class ILLMClient(Protocol):
    """Интерфейс клиента LLM."""

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        require_json: bool = False,
    ) -> str:
        """Отправляет запрос к LLM."""
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
    """Интерфейс менеджера души (личность, правила, ценности)."""

    def get_personality(self) -> str:
        """Возвращает содержимое personality.txt."""
        ...

    def get_rules(self) -> str:
        """Возвращает содержимое rules.txt."""
        ...

    def get_values(self) -> str:
        """Возвращает содержимое values.txt."""
        ...

    def get_all_contents(self) -> dict[str, str]:
        """Возвращает все файлы души."""
        ...

    def write_file(self, filename: str, content: str) -> bool:
        """Записывает файл души."""
        ...


# =============================================================================
# Tool Registry Interface
# =============================================================================


@runtime_checkable
class IToolRegistry(Protocol):
    """Интерфейс реестра инструментов."""

    def register_tool(self, tool: dict[str, Any]) -> None:
        """Регистрирует инструмент."""
        ...

    def get_tool(self, name: str) -> dict[str, Any] | None:
        """Возвращает инструмент по имени."""
        ...

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Возвращает все зарегистрированные инструменты."""
        ...

    async def execute_tool(self, name: str, **kwargs) -> Any:
        """Выполняет инструмент."""
        ...


# =============================================================================
# Constitutional Layer Interface
# =============================================================================


@runtime_checkable
class IConstitutionalLayer(Protocol):
    """
    Интерфейс конституционального слоя (этические ограничения).

    Реализация: leya_core.constitutional.ConstitutionalLayer
    """

    def verify_response(self, response: str) -> Any:
        """Проверка ответа Леи перед отправкой пользователю."""
        ...

    def verify_tool_call(self, tool_name: str, parameters: dict[str, Any]) -> Any:
        """Проверка вызова инструмента перед выполнением."""
        ...

    async def execute_python_sandbox(self, code: str) -> dict[str, Any]:
        """Безопасное выполнение Python-кода в sandbox."""
        ...

    def get_violations_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Получение лога нарушений."""
        ...

    def get_stats(self) -> dict[str, Any]:
        """Получение статистики конституционального слоя."""
        ...

    def enable_rule(self, rule_name: str) -> bool:
        """Включение правила по названию."""
        ...

    def disable_rule(self, rule_name: str) -> bool:
        """Отключение правила по названию."""
        ...

    def add_rule(self, rule: Any) -> None:
        """Добавление нового правила."""
        ...

    def remove_rule(self, rule_name: str) -> bool:
        """Удаление правила по названию."""
        ...
