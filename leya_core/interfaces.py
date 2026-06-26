"""
leya_core/interfaces.py
Интерфейсы (Protocol) для всех ключевых модулей LeyaOS.

Этап 2.1: Замена hasattr на isinstance-проверки.
Все модули должны реализовывать эти интерфейсы.

Использование:
    from leya_core.interfaces import IMemorySystem, IHomeostasisEngine
    
    def __init__(self, memory: IMemorySystem, homeostasis: IHomeostasisEngine):
        self.memory = memory
        self.homeostasis = homeostasis
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ============================================================================
# Память
# ============================================================================


@runtime_checkable
class IMemorySystem(Protocol):
    """Интерфейс системы памяти."""

    async def store_perception(
        self,
        content: str,
        emotional_boost: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Сохранить восприятие как энграмму."""
        ...

    async def store_fact(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Сохранить семантический факт."""
        ...

    async def retrieve_context(
        self,
        query: str,
        top_k: int = 5,
        min_retention: float = 0.1,
    ) -> List[Any]:
        """Извлечь релевантный контекст из памяти."""
        ...

    async def get_recent_episodes(self, limit: int = 20) -> List[Any]:
        """Получить недавние эпизоды (публичный API)."""
        ...

    async def get_recent_spontaneous_thoughts(self, limit: int = 10) -> List[Any]:
        """Получить недавние спонтанные мысли."""
        ...

    async def update_self_model(self, reflection: str) -> None:
        """Обновить само-модель."""
        ...

    async def get_self_model_context(self) -> str:
        """Получить текущую само-модель для промпта."""
        ...

    async def consolidate_memories(self) -> Dict[str, Any]:
        """Консолидация памяти (во время 'сна')."""
        ...

    async def forget_weak_memories(self, threshold: float = 0.1) -> int:
        """Забыть слабые воспоминания."""
        ...


# ============================================================================
# Драйвы
# ============================================================================


@runtime_checkable
class IDriveSystem(Protocol):
    """Интерфейс системы драйвов."""

    async def evaluate_stimulus(
        self,
        stimulus: str,
        context: str = "",
    ) -> Dict[Any, float]:
        """Оценить влияние стимула на драйвы."""
        ...

    def apply_deltas(self, deltas: Dict[Any, float]) -> None:
        """Применить дельты изменений к драйвам."""
        ...

    def apply_satisfaction(
        self,
        drive_type: Any,
        base_amount: float,
        rpe: float,
    ) -> None:
        """Применить удовлетворение драйва с учётом RPE."""
        ...

    def calculate_rpe(self, action_key: str, actual_outcome: float) -> float:
        """Вычислить Reward Prediction Error."""
        ...

    def get_predicted_disbalance(self) -> Dict[Any, float]:
        """Получить предсказанный дисбаланс драйвов."""
        ...

    def get_internal_state_prompt(self) -> str:
        """Получить текстовое описание состояния для промпта."""
        ...

    async def background_metabolism(self) -> None:
        """Фоновый метаболизм драйвов."""
        ...

    def stop(self) -> None:
        """Остановить фоновый метаболизм."""
        ...

    def save_state(self) -> Dict[str, Any]:
        """Сохранить состояние."""
        ...

    def load_state(self, state: Dict[str, Any]) -> None:
        """Загрузить состояние."""
        ...


# ============================================================================
# Гомеостаз
# ============================================================================


@runtime_checkable
class IHomeostasisEngine(Protocol):
    """Интерфейс движка гомеостаза."""

    def generate_goal(
        self,
        drive_state: Dict[Any, float],
        predicted_state: Dict[Any, float],
        recent_episodes: List[Any],
        action_values: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:
        """Сгенерировать цель на основе дисбаланса драйвов."""
        ...

    async def extract_key_facts(
        self,
        topic: str,
        article_text: str,
        llm_client: Any,
    ) -> List[str]:
        """Извлечь ключевые факты из статьи."""
        ...

    async def extract_new_terms(
        self,
        article_text: str,
        llm_client: Any,
    ) -> List[str]:
        """Извлечь новые термины из статьи."""
        ...

    def mark_as_researched(self, topic: str) -> None:
        """Пометить тему как исследованную."""
        ...

    def add_dynamic_keywords(self, keywords: List[str]) -> None:
        """Добавить динамические ключевые слова."""
        ...

    def update_from_self_model(self, self_model: str) -> None:
        """Обновить пороги из self_model."""
        ...

    def save_state(self) -> Dict[str, Any]:
        """Сохранить состояние."""
        ...

    def load_state(self, state: Dict[str, Any]) -> None:
        """Загрузить состояние."""
        ...


# ============================================================================
# Когнитивный планировщик
# ============================================================================


@runtime_checkable
class ICoreThinker(Protocol):
    """Интерфейс когнитивного планировщика."""

    async def generate_plan(
        self,
        stimulus: Dict[str, Any],
        memory_context: List[Dict],
        drive_state: Dict[str, float],
        self_model: Dict[str, Any],
        tools_description: str,
        tool_context: str = "",
    ) -> Dict[str, Any]:
        """Сгенерировать когнитивный план действия."""
        ...


# ============================================================================
# Мета-когниция
# ============================================================================


@runtime_checkable
class IMetaCognition(Protocol):
    """Интерфейс мета-когниции (reflection)."""

    async def process_action(
        self,
        stimulus: str,
        cognitive_output: Any,
        result: str,
    ) -> None:
        """Быстрая рефлексия после акта мышления."""
        ...

    async def generate_spontaneous_thought(self) -> Optional[str]:
        """Сгенерировать спонтанную мысль."""
        ...

    async def background_consolidation(self) -> None:
        """Фоновый цикл саморефлексии."""
        ...

    def stop(self) -> None:
        """Остановить фоновый цикл."""
        ...


# ============================================================================
# Глобальное рабочее пространство
# ============================================================================


@runtime_checkable
class IGlobalWorkspace(Protocol):
    """Интерфейс глобального рабочего пространства."""

    def submit(self, proposal: Any) -> None:
        """Подать предложение."""
        ...

    def select_winner(self, drive_state: Dict[str, float]) -> Optional[Any]:
        """Выбрать победителя."""
        ...

    def get_status(self) -> Dict[str, Any]:
        """Получить статус."""
        ...

    def clear_expired(self, max_age: float = 300.0) -> None:
        """Удалить устаревшие предложения."""
        ...


# ============================================================================
# Конституциональный слой
# ============================================================================


@runtime_checkable
class IConstitutionalLayer(Protocol):
    """Интерфейс конституционального слоя."""

    def verify_response(self, response: str) -> Any:
        """Проверить ответ перед отправкой."""
        ...

    def verify_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> Any:
        """Проверить вызов инструмента."""
        ...

    async def execute_python_sandbox(self, code: str) -> Dict[str, Any]:
        """Безопасное выполнение Python-кода."""
        ...


# ============================================================================
# Окружение
# ============================================================================


@runtime_checkable
class IEnvironment(Protocol):
    """Интерфейс окружения (Web/CLI)."""

    async def listen(self) -> Optional[Dict[str, Any]]:
        """Получить следующий стимул."""
        ...

    async def send_message(self, message: str) -> None:
        """Отправить сообщение."""
        ...

    async def broadcast_thought(
        self,
        thought_type: str,
        content: str,
    ) -> None:
        """Отправить мысль."""
        ...

    async def update_drives(self, drive_state: Dict[str, float]) -> None:
        """Обновить драйвы."""
        ...

    async def update_self_model(self, self_model: str) -> None:
        """Обновить self_model."""
        ...

    async def broadcast_state(self, state: str) -> None:
        """Отправить состояние."""
        ...


# ============================================================================
# LLM клиент
# ============================================================================


@runtime_checkable
class ILLMClient(Protocol):
    """Интерфейс LLM-клиента."""

    async def chat(
        self,
        prompt: str,
        require_json: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Отправить запрос к LLM."""
        ...

    async def close(self) -> None:
        """Закрыть соединение."""
        ...