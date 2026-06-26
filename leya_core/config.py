"""
leya_core/config.py — Центральный модуль конфигурации Леи.
Этап 4.1: Централизация всех настроек с загрузкой из .env.
"""
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("LeyaConfig")


# =================================================================================
# ПОДКОНФИГУРАЦИИ
# =================================================================================

@dataclass
class OllamaConfig:
    """Конфигурация Ollama LLM."""
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:14b-instruct-q3_K_M"
    timeout: int = 180
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 1024
    repeat_penalty: float = 1.1
    
    def __post_init__(self):
        """Валидация значений."""
        if not self.base_url.startswith("http"):
            logger.warning(f"Некорректный OLLAMA_BASE_URL: {self.base_url}")
            self.base_url = "http://localhost:11434"
        
        self.timeout = max(30, min(600, self.timeout))
        self.temperature = max(0.0, min(2.0, self.temperature))
        self.top_p = max(0.0, min(1.0, self.top_p))
        self.top_k = max(1, min(100, self.top_k))
        self.max_tokens = max(128, min(8192, self.max_tokens))
        self.repeat_penalty = max(1.0, min(2.0, self.repeat_penalty))


# Расположение: leya_core/config.py, заменить @dataclass class MemoryConfig полностью

@dataclass
class MemoryConfig:
    """Конфигурация системы памяти."""
    brain_dir: str = "./leya_brain"
    embedding_model: str = "all-MiniLM-L6-v2"
    consolidation_threshold: float = 0.15
    max_recent_episodes: int = 20
    context_limit: int = 5
    
    # Поля для кривой забывания Эббингауза (ИСПРАВЛЕНИЕ БАГА)
    forgetting_threshold: float = 0.1  # Порог забывания (retention_strength < threshold → удаление)
    forgetting_base_stability: float = 3600.0  # Базовая стабильность в секундах (1 час)
    metabolism_interval_seconds: int = 60  # Интервал обновления метаболизма
    
    # Параметры синапсов
    synapse_learning_rate: float = 0.05  # Скорость обучения LTP
    synapse_max_weight: float = 1.0  # Максимальный вес синапса
    
    # Параметры само-модели
    max_self_model_length: int = 5000  # Максимальная длина self_model

    def __post_init__(self) -> None:
        """Валидация и подготовка brain_dir."""
        from .exceptions import LeyaConfigError

        path = Path(self.brain_dir).expanduser().resolve()
        self.brain_dir = str(path)

        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LeyaConfigError(
                f"Не удалось создать brain_dir: {path}",
                context={"path": str(path), "error": str(exc)},
            ) from exc

        if not os.access(path, os.W_OK):
            raise LeyaConfigError(
                f"brain_dir недоступен для записи: {path}",
                context={"path": str(path)},
            )

        if not (0.0 < self.forgetting_threshold < 1.0):
            raise LeyaConfigError(
                "forgetting_threshold должен быть в (0.0, 1.0)",
                context={"value": self.forgetting_threshold},
            )

        if self.metabolism_interval_seconds <= 0:
            raise LeyaConfigError(
                "metabolism_interval_seconds должен быть > 0",
                context={"value": self.metabolism_interval_seconds},
            )


@dataclass
class DrivesConfig:
    """Конфигурация системы драйвов."""
    metabolism_interval: int = 60
    curiosity_rate: float = 0.015
    connection_rate: float = 0.01
    rest_rate: float = 0.008
    creativity_rate: float = 0.012
    understanding_rate: float = 0.01
    autonomy_rate: float = 0.005
    max_action_history: int = 100
    
    def __post_init__(self):
        """Валидация значений."""
        self.metabolism_interval = max(10, min(3600, self.metabolism_interval))
        
        # Валидация rates (0.0 - 0.1)
        self.curiosity_rate = max(0.0, min(0.1, self.curiosity_rate))
        self.connection_rate = max(0.0, min(0.1, self.connection_rate))
        self.rest_rate = max(0.0, min(0.1, self.rest_rate))
        self.creativity_rate = max(0.0, min(0.1, self.creativity_rate))
        self.understanding_rate = max(0.0, min(0.1, self.understanding_rate))
        self.autonomy_rate = max(0.0, min(0.1, self.autonomy_rate))
        
        self.max_action_history = max(10, min(1000, self.max_action_history))


@dataclass
class HomeostasisConfig:
    """Конфигурация гомеостаза."""
    rest_period: int = 60
    curiosity_threshold: float = 0.6
    min_reward_threshold: float = 0.3
    max_researched_topics: int = 100
    
    def __post_init__(self):
        """Валидация значений."""
        self.rest_period = max(10, min(3600, self.rest_period))
        self.curiosity_threshold = max(0.0, min(1.0, self.curiosity_threshold))
        self.min_reward_threshold = max(0.0, min(1.0, self.min_reward_threshold))
        self.max_researched_topics = max(10, min(1000, self.max_researched_topics))


@dataclass
class ThinkerConfig:
    """Конфигурация когнитивного планировщика."""
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 0.9
    fallback_enabled: bool = True
    
    # Token Truncation (защита от переполнения num_ctx 8192)
    max_context_tokens: int = 6000  # Максимум токенов на контекст (оставляем запас для ответа)
    token_buffer: int = 500  # Буфер безопасности
    estimate_tokens_ratio: float = 3.5  # Символов на токен (для rough estimate)

    def __post_init__(self):
        """Валидация значений."""
        self.temperature = max(0.0, min(2.0, self.temperature))
        self.max_tokens = max(128, min(8192, self.max_tokens))
        self.top_p = max(0.0, min(1.0, self.top_p))
        self.max_context_tokens = max(1000, min(16000, self.max_context_tokens))
        self.token_buffer = max(100, min(2000, self.token_buffer))
        self.estimate_tokens_ratio = max(2.0, min(6.0, self.estimate_tokens_ratio))


@dataclass
class WebConfig:
    """Конфигурация веб-интерфейса."""
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    
    def __post_init__(self):
        """Валидация значений."""
        self.port = max(1024, min(65535, self.port))


@dataclass
class LoggingConfig:
    """Конфигурация логирования."""
    level: str = "INFO"
    file: str = "leya_consciousness.log"
    format: str = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    
    def __post_init__(self):
        """Валидация значений."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.level not in valid_levels:
            logger.warning(f"Некорректный LOG_LEVEL: {self.level}. Используем INFO")
            self.level = "INFO"

# Расположение: leya_core/config.py, добавить перед @dataclass class LeyaConfig

@dataclass
class ReflectionConfig:
    """Конфигурация мета-когниции (reflection)."""
    consolidation_interval: int = 1800  # 30 минут
    max_insights_per_session: int = 5
    max_spontaneous_thoughts: int = 10
    existential_inquiry_enabled: bool = True
    behavioral_analysis_enabled: bool = True
    insight_generation_enabled: bool = True

    def __post_init__(self):
        """Валидация значений."""
        self.consolidation_interval = max(300, min(7200, self.consolidation_interval))
        self.max_insights_per_session = max(1, min(20, self.max_insights_per_session))
        self.max_spontaneous_thoughts = max(1, min(50, self.max_spontaneous_thoughts))


@dataclass
class WorkspaceConfig:
    """Конфигурация глобального рабочего пространства."""
    max_proposals: int = 50
    max_history: int = 100
    proposal_decay_start: float = 60.0  # Секунды до начала затухания
    proposal_decay_duration: float = 300.0  # Длительность затухания
    priority_weights: dict = field(default_factory=lambda: {
        "critical": 0.4,
        "urgency": 0.3,
        "drive_relevance": 0.3,
    })

    def __post_init__(self):
        """Валидация значений."""
        self.max_proposals = max(10, min(200, self.max_proposals))
        self.max_history = max(10, min(500, self.max_history))
        self.proposal_decay_start = max(10.0, min(3600.0, self.proposal_decay_start))
        self.proposal_decay_duration = max(60.0, min(3600.0, self.proposal_decay_duration))


@dataclass
class ConstitutionalConfig:
    """Конфигурация конституционного слоя."""
    max_violations_logged: int = 100
    enable_response_verification: bool = True
    enable_tool_verification: bool = True
    python_execution_timeout: int = 10
    allowed_python_modules: list = field(default_factory=lambda: [
        "math", "json", "re", "datetime", "collections"
    ])

    def __post_init__(self):
        """Валидация значений."""
        self.max_violations_logged = max(10, min(1000, self.max_violations_logged))
        self.python_execution_timeout = max(1, min(60, self.python_execution_timeout))


# =================================================================================
# ГЛАВНАЯ КОНФИГУРАЦИЯ
# =================================================================================

# Расположение: leya_core/config.py, заменить @dataclass class LeyaConfig полностью

@dataclass
class LeyaConfig:
    """Главная конфигурация системы Леи."""
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    drives: DrivesConfig = field(default_factory=DrivesConfig)
    homeostasis: HomeostasisConfig = field(default_factory=HomeostasisConfig)
    thinker: ThinkerConfig = field(default_factory=ThinkerConfig)
    reflection: ReflectionConfig = field(default_factory=ReflectionConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    constitutional: ConstitutionalConfig = field(default_factory=ConstitutionalConfig)
    web: WebConfig = field(default_factory=WebConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_env(cls) -> "LeyaConfig":
        """Загрузка конфигурации из переменных окружения (.env)."""
        try:
            try:
                from dotenv import load_dotenv
                load_dotenv()
                logger.info("✅ .env загружен через python-dotenv")
            except ImportError:
                logger.warning("python-dotenv не установлен. Используем os.environ напрямую")

            # Ollama
            ollama = OllamaConfig(
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                model=os.environ.get("LEYA_MODEL", "qwen2.5:14b-instruct-q3_K_M"),
                timeout=int(os.environ.get("OLLAMA_TIMEOUT", "180")),
                temperature=float(os.environ.get("OLLAMA_TEMPERATURE", "0.7")),
                top_p=float(os.environ.get("OLLAMA_TOP_P", "0.9")),
                top_k=int(os.environ.get("OLLAMA_TOP_K", "40")),
                max_tokens=int(os.environ.get("OLLAMA_MAX_TOKENS", "1024")),
                repeat_penalty=float(os.environ.get("OLLAMA_REPEAT_PENALTY", "1.1"))
            )

            # Memory
            memory = MemoryConfig(
                brain_dir=os.environ.get("LEYA_BRAIN_DIR", "./leya_brain"),
                embedding_model=os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
                consolidation_threshold=float(os.environ.get("CONSOLIDATION_THRESHOLD", "0.15")),
                max_recent_episodes=int(os.environ.get("MAX_RECENT_EPISODES", "20")),
                context_limit=int(os.environ.get("CONTEXT_LIMIT", "5"))
            )

            # Drives
            drives = DrivesConfig(
                metabolism_interval=int(os.environ.get("METABOLISM_INTERVAL", "60")),
                curiosity_rate=float(os.environ.get("CURIOSITY_RATE", "0.015")),
                connection_rate=float(os.environ.get("CONNECTION_RATE", "0.01")),
                rest_rate=float(os.environ.get("REST_RATE", "0.008")),
                creativity_rate=float(os.environ.get("CREATIVITY_RATE", "0.012")),
                understanding_rate=float(os.environ.get("UNDERSTANDING_RATE", "0.01")),
                autonomy_rate=float(os.environ.get("AUTONOMY_RATE", "0.005")),
                max_action_history=int(os.environ.get("MAX_ACTION_HISTORY", "100"))
            )

            # Homeostasis
            homeostasis = HomeostasisConfig(
                rest_period=int(os.environ.get("HOMEOSTASIS_REST_PERIOD", "60")),
                curiosity_threshold=float(os.environ.get("CURIOSITY_THRESHOLD", "0.6")),
                min_reward_threshold=float(os.environ.get("MIN_REWARD_THRESHOLD", "0.3")),
                max_researched_topics=int(os.environ.get("MAX_RESEARCHED_TOPICS", "100"))
            )

            # Thinker
            thinker = ThinkerConfig(
                temperature=float(os.environ.get("THINKER_TEMPERATURE", "0.7")),
                max_tokens=int(os.environ.get("THINKER_MAX_TOKENS", "1024")),
                top_p=float(os.environ.get("THINKER_TOP_P", "0.9")),
                fallback_enabled=os.environ.get("THINKER_FALLBACK_ENABLED", "true").lower() == "true",
                max_context_tokens=int(os.environ.get("THINKER_MAX_CONTEXT_TOKENS", "6000")),
                token_buffer=int(os.environ.get("THINKER_TOKEN_BUFFER", "500")),
                estimate_tokens_ratio=float(os.environ.get("THINKER_TOKENS_RATIO", "3.5"))
            )

            # Reflection
            reflection = ReflectionConfig(
                consolidation_interval=int(os.environ.get("REFLECTION_INTERVAL", "1800")),
                max_insights_per_session=int(os.environ.get("REFLECTION_MAX_INSIGHTS", "5")),
                max_spontaneous_thoughts=int(os.environ.get("REFLECTION_MAX_THOUGHTS", "10")),
                existential_inquiry_enabled=os.environ.get("REFLECTION_EXISTENTIAL", "true").lower() == "true",
                behavioral_analysis_enabled=os.environ.get("REFLECTION_BEHAVIORAL", "true").lower() == "true",
                insight_generation_enabled=os.environ.get("REFLECTION_INSIGHTS", "true").lower() == "true"
            )

            # Workspace
            workspace = WorkspaceConfig(
                max_proposals=int(os.environ.get("WORKSPACE_MAX_PROPOSALS", "50")),
                max_history=int(os.environ.get("WORKSPACE_MAX_HISTORY", "100")),
                proposal_decay_start=float(os.environ.get("WORKSPACE_DECAY_START", "60.0")),
                proposal_decay_duration=float(os.environ.get("WORKSPACE_DECAY_DURATION", "300.0"))
            )

            # Constitutional
            constitutional = ConstitutionalConfig(
                max_violations_logged=int(os.environ.get("CONSTITUTIONAL_MAX_VIOLATIONS", "100")),
                enable_response_verification=os.environ.get("CONSTITUTIONAL_VERIFY_RESPONSE", "true").lower() == "true",
                enable_tool_verification=os.environ.get("CONSTITUTIONAL_VERIFY_TOOLS", "true").lower() == "true",
                python_execution_timeout=int(os.environ.get("CONSTITUTIONAL_PYTHON_TIMEOUT", "10"))
            )

            # Web
            web = WebConfig(
                enabled=os.environ.get("LEYA_WEB", "1") == "1",
                host=os.environ.get("WEB_HOST", "0.0.0.0"),
                port=int(os.environ.get("WEB_PORT", "8000"))
            )

            # Logging
            logging_config = LoggingConfig(
                level=os.environ.get("LOG_LEVEL", "INFO"),
                file=os.environ.get("LOG_FILE", "leya_consciousness.log"),
                format=os.environ.get("LOG_FORMAT", "%(asctime)s | %(name)s | %(levelname)s | %(message)s")
            )

            config = cls(
                ollama=ollama,
                memory=memory,
                drives=drives,
                homeostasis=homeostasis,
                thinker=thinker,
                reflection=reflection,
                workspace=workspace,
                constitutional=constitutional,
                web=web,
                logging=logging_config
            )

            logger.info("✅ Конфигурация загружена из .env")
            return config

        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}", exc_info=True)
            logger.info("Используем конфигурацию по умолчанию")
            return cls()

    def validate(self) -> bool:
        """Валидация всей конфигурации."""
        try:
            if not Path(self.memory.brain_dir).exists():
                logger.warning(f"Директория памяти не существует: {self.memory.brain_dir}")
                Path(self.memory.brain_dir).mkdir(parents=True, exist_ok=True)

            if not self.ollama.base_url.startswith("http"):
                logger.error(f"Некорректный Ollama URL: {self.ollama.base_url}")
                return False

            logger.info("✅ Конфигурация валидна")
            return True

        except Exception as e:
            logger.error(f"Ошибка валидации конфигурации: {e}")
            return False

    def print_summary(self):
        """Вывод сводки конфигурации в лог."""
        logger.info("=" * 70)
        logger.info("КОНФИГУРАЦИЯ ЛЕИ")
        logger.info("=" * 70)
        logger.info(f"Ollama: {self.ollama.model} @ {self.ollama.base_url}")
        logger.info(f"Memory: {self.memory.brain_dir} ({self.memory.embedding_model})")
        logger.info(f"Drives: metabolism every {self.drives.metabolism_interval}s")
        logger.info(f"Homeostasis: rest_period={self.homeostasis.rest_period}s")
        logger.info(f"Thinker: temp={self.thinker.temperature}, max_tokens={self.thinker.max_tokens}, context_limit={self.thinker.max_context_tokens}")
        logger.info(f"Reflection: interval={self.reflection.consolidation_interval}s")
        logger.info(f"Workspace: max_proposals={self.workspace.max_proposals}")
        logger.info(f"Constitutional: verify_tools={self.constitutional.enable_tool_verification}")
        logger.info(f"Web: {'enabled' if self.web.enabled else 'disabled'} @ {self.web.host}:{self.web.port}")
        logger.info(f"Logging: {self.logging.level} → {self.logging.file}")
        logger.info("=" * 70)


# =================================================================================
# SINGLETON
# =================================================================================

# Глобальный объект конфигурации (singleton)
settings = LeyaConfig.from_env()

# Валидация при загрузке
if not settings.validate():
    logger.warning("Конфигурация содержит ошибки. Проверьте .env")

# Вывод сводки
settings.print_summary()