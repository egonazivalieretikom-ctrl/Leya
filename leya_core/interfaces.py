"""
leya_core/interfaces.py
Protocol-интерфейсы для всех ключевых компонентов LeyaOS.

Обеспечивают слабую связанность между модулями, позволяют использовать
mock-объекты в тестах и гарантируют контракт между компонентами.

Шаг 3: Добавлены методы get_drives_state(), get_memory_graph_data(), get_workspace_status()
для устранения прямого доступа к internals из web_interface/server.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from typing import Protocol, runtime_checkable, Any
from dataclasses import dataclass, field

if TYPE_CHECKING:
    # Импорт только для проверки типов, избегает циклического импорта в runtime
    from .memory import Engram, Synapse  # Адаптируйте импорт под ваш пакет


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
    """Протокол системы памяти Леи."""
    
    async def store_perception(
        self,
        content: str,
        emotional_boost: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> "Engram":  # ✅ ИСПРАВЛЕНО: было -> None
        """Сохранение восприятия в память."""
        ...
    
    async def store_fact(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> "Engram":  # ✅ ИСПРАВЛЕНО: было -> None
        """Сохранение факта в семантическую память."""
        ...
    
    async def retrieve_context(
        self,
        query: str,
        max_results: int = 5,
    ) -> list["Engram"]:  # ✅ ИСПРАВЛЕНО: было -> list[Any]
        """Получение релевантного контекста из памяти."""
        ...
    
    async def consolidate_memories(self) -> dict[str, Any]:
        """Консолидация памяти (фоновая задача)."""
        ...
    
    async def update_self_model(self, reflection: str) -> None:
        """Обновление модели себя на основе рефлексии."""
        ...
    
    async def get_self_model_context(self) -> str:
        """Получение контекста модели себя для промптов."""
        ...
    
    async def get_recent_episodes(self, limit: int = 10) -> list["Engram"]:  # ✅ ИСПРАВЛЕНО: было -> list[Any]
        """Получение недавних эпизодов."""
        ...
    
    async def forget_weak_memories(self) -> int:
        """Забывание слабых воспоминаний."""
        ...
    
    async def get_memory_graph_data(self) -> dict[str, Any]:  # ✅ КРИТИЧНО ИСПРАВЛЕНО: было def (синхронный), стало async def
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

    # Атрибуты состояния (как type annotations, БЕЗ присваивания)
    current_goal: Any  # WorkspaceProposal | None
    last_action_time: float
    rest_period: float

    # Методы (только сигнатуры с ... как телом)
    async def generate_goal(
        self,
        drive_state: dict[str, float],
        predicted_state: dict[str, float],
        recent_episodes: list[Any],  # list[Engram]
        action_values: dict[str, float],
    ) -> Any: ...

    def generate_goal_from_gap(self, gap: float, drive_type: str) -> Any: ...

    async def extract_key_facts(self, text: str) -> list[str]: ...

    async def extract_new_terms(self, text: str) -> list[str]: ...

    def mark_as_researched(self, topic: str) -> None: ...

    def add_dynamic_keywords(self, keywords: list[str]) -> None: ...

# =============================================================================
# Homeostasis Engine Interface
# =============================================================================

class HomeostasisEngine:
    """
    Реализация IHomeostasisEngine.
    Генерирует автономные цели на основе дисбаланса драйвов.
    """
    
    def __init__(self, config: HomeostasisConfig | None = None) -> None:
        self.config = config or HomeostasisConfig()
        
        # Реализация атрибутов Protocol
        self._current_goal: WorkspaceProposal | None = None
        self._last_action_time: float = 0.0
        self._rest_period: float = self.config.rest_period
        
        # Внутреннее состояние
        self._researched_topics: set[str] = set()
        self._dynamic_keywords: list[str] = []
    
    # Реализация атрибутов Protocol (обычные поля, НЕ @property)
    @property
    def current_goal(self) -> WorkspaceProposal | None:
        return self._current_goal
    
    @current_goal.setter
    def current_goal(self, value: WorkspaceProposal | None) -> None:
        self._current_goal = value
    
    @property
    def last_action_time(self) -> float:
        return self._last_action_time
    
    @last_action_time.setter
    def last_action_time(self, value: float) -> None:
        self._last_action_time = value
    
    @property
    def rest_period(self) -> float:
        return self._rest_period
    
    # Реализация методов Protocol
    async def generate_goal(
        self,
        drive_state: dict[str, float],
        predicted_state: dict[str, float],
        recent_episodes: list[Engram],
        action_values: dict[str, float],
    ) -> WorkspaceProposal | None:
        """Генерация цели на основе дисбаланса драйвов."""
        # ... существующая реализация ...
        pass
    
    def generate_goal_from_gap(self, gap: float, drive_type: str) -> WorkspaceProposal | None:
        """Генерация цели из разрыва (gap)."""
        # ... существующая реализация ...
        pass
    
    async def extract_key_facts(self, text: str) -> list[str]:
        """Извлечение ключевых фактов из текста."""
        # ... существующая реализация ...
        pass
    
    async def extract_new_terms(self, text: str) -> list[str]:
        """Извлечение новых терминов из текста."""
        # ... существующая реализация ...
        pass
    
    def mark_as_researched(self, topic: str) -> None:
        """Пометить тему как исследованную."""
        self._researched_topics.add(topic)
    
    def add_dynamic_keywords(self, keywords: list[str]) -> None:
        """Добавить динамические ключевые слова."""
        self._dynamic_keywords.extend(keywords)

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

# =================================================================================
# DECISION ENGINE & EMOTIONAL SUPPORT (Experimental, v3.1)
# =================================================================================

@runtime_checkable
class IDecisionEngine(Protocol):
    """Детерминированный движок быстрых решений (без LLM).
    
    Этап 2.2 (ADR-001): Префронтальная кора Леи. Принимает решения на основе
    состояния драйвов и типа стимула. Используется как уровень 0 в cognitive loop
    для мгновенных решений (разгрузка LLM).
    """
    
    async def make_decision(
        self,
        stimulus: str,
        drive_state: dict,
    ) -> Optional["Decision"]:
        """Принятие решения на основе стимула и состояния драйвов.
        
        Args:
            stimulus: Текст стимула от пользователя
            drive_state: Словарь {DriveType: tension_level}
            
        Returns:
            Decision с tool_name/parameters или None, если нужен LLM
        """
        ...
    
    def get_decision_confidence(self) -> float:
        """Возвращает confidence последнего решения (0.0-1.0)."""
        ...


@runtime_checkable
class IEmotionalSupport(Protocol):
    """Анализ эмоций пользователя и генерация эмпатических ответов.
    
    Этап 2.2 (ADR-001): Усиливает социальную составляющую Леи.
    Влияет на CONNECTION drive через RPE. Сохраняет эмоциональный контекст
    в Memory для долгосрочного анализа.
    """
    
    async def analyze_user_state(
        self,
        text: str,
        recent_messages: Optional[list[str]] = None,
    ) -> "EmotionState":
        """Анализ эмоционального состояния пользователя.
        
        Args:
            text: Текст сообщения пользователя
            recent_messages: Контекст последних сообщений (опционально)
            
        Returns:
            EmotionState с mood, intensity, needs_support
        """
        ...
    
    async def generate_support_response(
        self,
        emotion_state: "EmotionState",
        context: str = "",
    ) -> str:
        """Генерация эмпатического ответа.
        
        Args:
            emotion_state: Результат analyze_user_state
            context: Дополнительный контекст (опционально)
            
        Returns:
            Поддерживающий ответ на русском языке
        """
        ...
    
    async def update_drives_from_emotion(
        self,
        emotion_state: "EmotionState",
        drives: "IDriveSystem",
    ) -> None:
        """Влияние эмоции на CONNECTION drive через RPE.
        
        Позитивные эмоции → удовлетворение CONNECTION.
        Негативные эмоции → усиление CONNECTION (потребность в поддержке).
        
        Args:
            emotion_state: Результат analyze_user_state
            drives: Система драйвов для обновления
        """
        ...
    
    async def get_emotional_context_for_prompt(self) -> str:
        """Возвращает строку с эмоциональным контекстом для промпта LLM."""
        ...