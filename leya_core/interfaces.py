"""
leya_core/interfaces.py
Protocol-интерфейсы для всех ключевых компонентов LeyaOS.

Обеспечивают слабую связанность между модулями, позволяют использовать
mock-объекты в тестах и гарантируют контракт между компонентами.

Шаг 3: Добавлены методы get_drives_state(), get_memory_graph_data(), get_workspace_status()
для устранения прямого доступа к internals из web_interface/server.py.
"""
from __future__ import annotations

from typing import (
    Any,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)


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

    def evaluate_stimulus(self, stimulus: Any) -> Dict[str, float]:
        """
        Оценивает стимул и возвращает влияние на драйвы.
        
        Args:
            stimulus: Входной стимул (сообщение, событие и т.д.)
            
        Returns:
            dict с изменениями драйвов: {"CURIOSITY": 0.5, "REST": -0.2, ...}
        """
        ...

    def apply_deltas(self, deltas: Dict[str, float]) -> None:
        """
        Применяет изменения к драйвам.
        
        Args:
            deltas: Изменения драйвов от evaluate_stimulus
        """
        ...

    def apply_satisfaction(self, drive_type: str, amount: float) -> None:
        """
        Удовлетворяет драйв (после успешного действия).
        
        Args:
            drive_type: Тип драйва (например, "CURIOSITY")
            amount: Количество удовлетворения
        """
        ...

    def calculate_rpe(self, drive_type: str, actual_reward: float) -> float:
        """
        Вычисляет Reward Prediction Error.
        
        Args:
            drive_type: Тип драйва
            actual_reward: Фактическое вознаграждение
            
        Returns:
            RPE (разница между предсказанным и фактическим)
        """
        ...

    def get_predicted_disbalance(self) -> Dict[str, float]:
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

    def update_from_system_metrics(self, metrics: Dict[str, float]) -> None:
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
        self,
        content: str,
        memory_type: str = "episodic",
        emotional_boost: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Сохраняет восприятие как энграмму.
        
        Args:
            content: Содержание восприятия
            memory_type: Тип памяти ("episodic" или "semantic")
            emotional_boost: Эмоциональное усиление (0.0-1.0)
            metadata: Дополнительные метаданные
            
        Returns:
            ID созданной энграммы
        """
        ...

    async def retrieve_context(
        self,
        query: str,
        max_results: int = 10,
        min_retention: float = 0.1,
    ) -> List[Dict[str, Any]]:
        """
        Извлекает контекст из памяти по запросу.
        
        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов
            min_retention: Минимальный retention_strength
            
        Returns:
            Список энграмм с метаданными
        """
        ...

    async def store_fact(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Сохраняет семантический факт.
        
        Args:
            content: Содержание факта
            metadata: Дополнительные метаданные
            
        Returns:
            ID созданной энграммы
        """
        ...

    async def consolidate_memories(self) -> Dict[str, Any]:
        """
        Консолидирует памяти (replay + извлечение семантических фактов).
        
        Returns:
            Статистика консолидации
        """
        ...

    async def update_self_model(self, reflection: str) -> None:
        """
        Обновляет само-модель на основе рефлексии.
        
        Args:
            reflection: Текст рефлексии
        """
        ...

    async def get_self_model_context(self) -> str:
        """
        Возвращает контекст само-модели для промпта.
        
        Returns:
            Строка с описанием само-модели
        """
        ...

    async def get_recent_spontaneous_thoughts(self, limit: int = 5) -> List[str]:
        """
        Возвращает недавние спонтанные мысли.
        
        Args:
            limit: Максимальное количество мыслей
            
        Returns:
            Список строк с мыслями
        """
        ...

    async def get_recent_episodes(self, limit: int = 20) -> List[Any]:
        """
        Возвращает недавние эпизоды памяти.
        Публичный API для UI и внешних потребителей.
        
        Args:
            limit: Максимальное количество эпизодов
            
        Returns:
            Список энграмм (Engram dataclass)
        """
        ...

    async def forget_weak_memories(self, threshold: float = 0.1) -> int:
        """
        Забывает слабые воспоминания.
        
        Args:
            threshold: Порог retention_strength
            
        Returns:
            Количество забытых воспоминаний
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
        Вся логика фильтрации, сортировки и построения nodes/edges
        инкапсулирована здесь.
        
        Args:
            min_retention: минимальный retention_strength для включения
            max_nodes: максимальное количество узлов
            include_synapses: включать ли рёбра (synapses)
            
        Returns:
            dict с ключами:
                "nodes": list[dict] — узлы графа
                "edges": list[dict] — рёбра графа
                "total_engrams": int
                "total_synapses": int
        """
        ...

    async def _save_state(self) -> None:
        """Сохраняет состояние памяти (pickle/JSON)."""
        ...

    async def _load_state(self) -> None:
        """Загружает состояние памяти."""
        ...


# =============================================================================
# Workspace Interface
# =============================================================================

@runtime_checkable
class IWorkspace(Protocol):
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
        metadata: Optional[Dict[str, Any]] = None,
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

    def select_winner(self) -> Optional[Any]:
        """
        Выбирает победителя (focus) из proposals.
        
        Returns:
            WorkspaceProposal-победитель или None
        """
        ...

    def get_focus(self) -> Optional[Any]:
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

    async def generate_goal(
        self,
        drive_state: Dict[str, float],
        predicted_state: Optional[Dict[str, float]] = None,
        recent_episodes: Optional[List[Dict[str, Any]]] = None,
        action_values: Optional[Dict[str, float]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Генерирует цель на основе дисбаланса драйвов.
        
        Args:
            drive_state: Текущее состояние драйвов
            predicted_state: Предсказанное состояние
            recent_episodes: Недавние эпизоды
            action_values: Ценности действий
            
        Returns:
            dict с информацией о цели или None
        """
        ...

    async def generate_goal_from_gap(
        self,
        gap: Dict[str, float],
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Генерирует цель на основе разрыва (gap) между текущим и желаемым состоянием.
        
        Args:
            gap: Разрыв между состояниями
            context: Дополнительный контекст
            
        Returns:
            dict с информацией о цели или None
        """
        ...

    def mark_as_researched(self, topic: str) -> None:
        """
        Отмечает тему как исследованную.
        
        Args:
            topic: Тема для отметки
        """
        ...

    def add_dynamic_keywords(self, keywords: List[str]) -> None:
        """
        Добавляет динамические ключевые слова для поиска.
        
        Args:
            keywords: Список ключевых слов
        """
        ...

    @property
    def current_goal(self) -> Optional[Dict[str, Any]]:
        """Текущая активная цель."""
        ...

    @property
    def last_action_time(self) -> float:
        """Время последнего действия."""
        ...

    @property
    def rest_period(self) -> float:
        """Период отдыха в секундах."""
        ...


# =============================================================================
# Thinker Interface
# =============================================================================

@runtime_checkable
class IThinker(Protocol):
    """
    Интерфейс когнитивного планировщика.
    
    Реализация: leya_core.thinker.CoreThinker
    
    Строит когнитивный промпт, вызывает LLM, парсит ответ в CognitiveOutput.
    """

    async def generate_plan(
        self,
        stimulus: Any,
        drive_state: str,
        memory_context: str,
        self_model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_context: Optional[str] = None,
    ) -> Any:
        """
        Генерирует когнитивный план (response + action_intent).
        
        Args:
            stimulus: Входной стимул
            drive_state: Состояние драйвов (строка для промпта)
            memory_context: Контекст из памяти
            self_model: Само-модель
            tools: Доступные инструменты
            tool_context: Контекст использования инструментов
            
        Returns:
            CognitiveOutput dataclass
        """
        ...

    def _build_cognitive_prompt(
        self,
        stimulus: Any,
        drive_state: str,
        memory_context: str,
        self_model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_context: Optional[str] = None,
    ) -> str:
        """
        Строит полный когнитивный промпт для LLM.
        
        Args:
            stimulus: Входной стимул
            drive_state: Состояние драйвов
            memory_context: Контекст из памяти
            self_model: Само-модель
            tools: Доступные инструменты
            tool_context: Контекст использования инструментов
            
        Returns:
            Полный промпт (строка)
        """
        ...


# =============================================================================
# Reflection Interface
# =============================================================================

@runtime_checkable
class IReflection(Protocol):
    """
    Интерфейс мета-когниции (рефлексии).
    
    Реализация: leya_core.reflection.MetaCognition
    
    Обрабатывает действия, генерирует спонтанные мысли, фоновая консолидация.
    """

    async def process_action(self, action: Dict[str, Any]) -> Optional[str]:
        """
        Обрабатывает выполненное действие и генерирует рефлексию.
        
        Args:
            action: Информация о действии
            
        Returns:
            Текст рефлексии или None
        """
        ...

    async def generate_spontaneous_thought(self) -> Optional[str]:
        """
        Генерирует спонтанную мысль.
        
        Returns:
            Текст спонтанной мысли или None
        """
        ...

    async def background_consolidation(self) -> None:
        """
        Фоновая консолидация (во время "сна").
        Запускается как asyncio задача.
        """
        ...

    @property
    def is_sleeping(self) -> bool:
        """Флаг: находится ли Лея в состоянии "сна"."""
        ...


# =============================================================================
# Environment Interface
# =============================================================================

@runtime_checkable
class IEnvironment(Protocol):
    """
    Интерфейс окружения (веб, CLI, голос и т.д.).
    
    Реализации: leya_core.environment.CLIEnvironment,
                 web_interface.web_environment.WebEnvironment
    """

    async def listen(self) -> Optional[Dict[str, Any]]:
        """
        Слушает входные сообщения/стимулы.
        
        Returns:
            Сообщение или None
        """
        ...

    async def send_message(self, message: str) -> None:
        """
        Отправляет сообщение пользователю/внешнему миру.
        
        Args:
            message: Текст сообщения
        """
        ...

    async def broadcast_thought(self, thought_type: str, content: str) -> None:
        """
        Транслирует мысль (для UI).
        
        Args:
            thought_type: Тип мысли (internal, spontaneous, reflection)
            content: Содержание мысли
        """
        ...

    async def update_drives(self, drive_state: Dict[str, float]) -> None:
        """
        Обновляет состояние драйвов (для UI).
        
        Args:
            drive_state: Состояние драйвов
        """
        ...

    async def update_self_model(self, self_model: str) -> None:
        """
        Обновляет само-модель (для UI).
        
        Args:
            self_model: Текст само-модели
        """
        ...

    async def update_memory(self, memory_info: Dict[str, Any]) -> None:
        """
        Обновляет информацию о памяти (для UI).
        
        Args:
            memory_info: Информация о памяти
        """
        ...

    async def broadcast_state(self, state: str) -> None:
        """
        Транслирует состояние Леи (для UI).
        
        Args:
            state: Состояние (awake, sleeping, reflecting и т.д.)
        """
        ...

    async def broadcast_soul_update(self, soul_files: Dict[str, str]) -> None:
        """
        Транслирует обновление файлов души (для UI).
        
        Args:
            soul_files: Содержимое файлов души
        """
        ...


# =============================================================================
# LLM Client Interface
# =============================================================================

@runtime_checkable
class ILLMClient(Protocol):
    """
    Интерфейс клиента LLM.
    
    Реализация: leya_core.llm_client.LLMClient
    
    Обёртка над Ollama API с circuit breaker и retry логикой.
    """

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        require_json: bool = False,
    ) -> str:
        """
        Отправляет запрос к LLM.
        
        Args:
            messages: Список сообщений (role, content)
            model: Модель (по умолчанию из config)
            temperature: Температура генерации
            require_json: Требовать JSON-ответ
            
        Returns:
            Ответ LLM (строка)
        """
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
    """
    Интерфейс менеджера души (личность, правила, ценности).
    
    Реализация: leya_core.soul_manager.SoulManager (если существует)
    """

    def get_personality(self) -> str:
        """Возвращает содержимое personality.txt."""
        ...

    def get_rules(self) -> str:
        """Возвращает содержимое rules.txt."""
        ...

    def get_values(self) -> str:
        """Возвращает содержимое values.txt."""
        ...

    def get_all_contents(self) -> Dict[str, str]:
        """Возвращает все файлы души."""
        ...

    def write_file(self, filename: str, content: str) -> bool:
        """
        Записывает файл души.
        
        Args:
            filename: Имя файла (personality.txt, rules.txt, values.txt)
            content: Содержимое
            
        Returns:
            True если успешно
        """
        ...


# =============================================================================
# Tool Registry Interface
# =============================================================================

@runtime_checkable
class IToolRegistry(Protocol):
    """
    Интерфейс реестра инструментов.
    
    Реализация: leya_core.tool_generator.ToolRegistry
    """

    def register_tool(self, tool: Dict[str, Any]) -> None:
        """
        Регистрирует инструмент.
        
        Args:
            tool: Описание инструмента (name, description, parameters, function)
        """
        ...

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает инструмент по имени.
        
        Args:
            name: Имя инструмента
            
        Returns:
            Описание инструмента или None
        """
        ...

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Возвращает все зарегистрированные инструменты."""
        ...

    async def execute_tool(self, name: str, **kwargs) -> Any:
        """
        Выполняет инструмент.
        
        Args:
            name: Имя инструмента
            **kwargs: Параметры инструмента
            
        Returns:
            Результат выполнения
        """
        ...