# leya_core/config.py — Центральный модуль конфигурации Леи.
# Этап 4.1: Централизация всех настроек с загрузкой из .env.
# Этап 1.2: Полная загрузка всех полей, явные ошибки, улучшенный парсинг bool.

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("LeyaConfig")

# =================================================================================
# УТИЛИТЫ ПАРСИНГА
# =================================================================================


def _parse_bool(val: str, default: bool = False) -> bool:
    """Безопасный парсинг булевых значений из строк окружения."""
    if val is None:
        return default
    val = str(val).strip().lower()
    if val in ("true", "1", "yes", "on", "y", "t"):
        return True
    if val in ("false", "0", "no", "off", "n", "f"):
        return False
    logger.warning(f"Некорректное булево значение: '{val}'. Используем default={default}")
    return default


def _parse_int(val: str, default: int, field_name: str = "") -> int:
    """Безопасный парсинг int с явной ошибкой."""
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        from .exceptions import LeyaConfigError

        raise LeyaConfigError(
            f"Ожидалось целое число для {field_name or 'поля'}, получено: '{val}'",
            context={"field": field_name, "value": val},
        )


def _parse_float(val: str, default: float, field_name: str = "") -> float:
    """Безопасный парсинг float с явной ошибкой."""
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        from .exceptions import LeyaConfigError

        raise LeyaConfigError(
            f"Ожидалось число для {field_name or 'поля'}, получено: '{val}'",
            context={"field": field_name, "value": val},
        )


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
        if not self.base_url.startswith("http"):
            logger.warning(f"Некорректный OLLAMA_BASE_URL: {self.base_url}")
            self.base_url = "http://localhost:11434"
        self.timeout = max(30, min(600, self.timeout))
        self.temperature = max(0.0, min(2.0, self.temperature))
        self.top_p = max(0.0, min(1.0, self.top_p))
        self.top_k = max(1, min(100, self.top_k))
        self.max_tokens = max(128, min(8192, self.max_tokens))
        self.repeat_penalty = max(1.0, min(2.0, self.repeat_penalty))


@dataclass
class MemoryConfig:
    """Конфигурация системы памяти."""

    brain_dir: str = "./leya_brain"
    embedding_model: str = "all-MiniLM-L6-v2"
    consolidation_threshold: float = 0.15
    max_recent_episodes: int = 20
    context_limit: int = 5

    # Поля для кривой забывания Эббингауза
    forgetting_threshold: float = 0.1
    forgetting_base_stability: float = 3600.0
    metabolism_interval_seconds: int = 60

    # Параметры синапсов
    synapse_learning_rate: float = 0.05
    synapse_max_weight: float = 1.0

    # Параметры само-модели
    max_self_model_length: int = 5000

    # Новая JSON persistence (hardening)
    hmac_key: str = ""
    state_version: int = 1

    def __post_init__(self) -> None:
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
                f"brain_dir недоступен для записи: {path}", context={"path": str(path)}
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
        self.metabolism_interval = max(10, min(3600, self.metabolism_interval))
        self.curiosity_rate = max(0.0, min(0.1, self.curiosity_rate))
        self.connection_rate = max(0.0, min(0.1, self.connection_rate))
        self.rest_rate = max(0.0, min(0.1, self.rest_rate))
        self.creativity_rate = max(0.0, min(0.1, self.creativity_rate))
        self.understanding_rate = max(0.0, min(0.1, self.understanding_rate))
        self.autonomy_rate = max(0.0, min(0.1, self.autonomy_rate))
        self.max_action_history = max(10, min(1000, self.max_action_history))


@dataclass
class HomeostasisConfig:
    """Конфигурация движка гомеостаза."""

    rest_period: int = 60
    curiosity_threshold: float = 0.6
    connection_threshold: float = 0.6
    autonomy_threshold: float = 0.7
    integrity_threshold: float = 0.5
    rest_threshold: float = 0.6
    creativity_threshold: float = 0.5
    understanding_threshold: float = 0.6
    min_reward_threshold: float = 0.3
    max_researched_topics: int = 100

    def __post_init__(self):
        self.rest_period = max(10, min(3600, self.rest_period))
        self.curiosity_threshold = max(0.1, min(1.0, self.curiosity_threshold))
        self.connection_threshold = max(0.1, min(1.0, self.connection_threshold))
        self.autonomy_threshold = max(0.1, min(1.0, self.autonomy_threshold))
        self.integrity_threshold = max(0.1, min(1.0, self.integrity_threshold))
        self.rest_threshold = max(0.1, min(1.0, self.rest_threshold))
        self.creativity_threshold = max(0.1, min(1.0, self.creativity_threshold))
        self.understanding_threshold = max(0.1, min(1.0, self.understanding_threshold))
        self.min_reward_threshold = max(0.0, min(1.0, self.min_reward_threshold))
        self.max_researched_topics = max(10, min(1000, self.max_researched_topics))


@dataclass
class ThinkerConfig:
    """Конфигурация когнитивного планировщика."""

    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 0.9
    fallback_enabled: bool = True
    max_context_tokens: int = 6000
    token_buffer: int = 500
    estimate_tokens_ratio: float = 3.5

    def __post_init__(self):
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
        self.port = max(1024, min(65535, self.port))


@dataclass
class LoggingConfig:
    """Конфигурация логирования."""

    level: str = "INFO"
    file: str = "leya_consciousness.log"
    format: str = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"

    def __post_init__(self):
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.level not in valid_levels:
            logger.warning(f"Некорректный LOG_LEVEL: {self.level}. Используем INFO")
            self.level = "INFO"


@dataclass
class ReflectionConfig:
    """Конфигурация мета-когниции (reflection)."""

    consolidation_interval: int = 1800
    max_insights_per_session: int = 5
    max_spontaneous_thoughts: int = 10
    existential_inquiry_enabled: bool = True
    behavioral_analysis_enabled: bool = True
    insight_generation_enabled: bool = True

    def __post_init__(self):
        self.consolidation_interval = max(300, min(7200, self.consolidation_interval))
        self.max_insights_per_session = max(1, min(20, self.max_insights_per_session))
        self.max_spontaneous_thoughts = max(1, min(50, self.max_spontaneous_thoughts))


@dataclass
class WorkspaceConfig:
    """Конфигурация глобального рабочего пространства."""

    max_proposals: int = 50
    max_history: int = 100
    proposal_decay_start: float = 60.0
    proposal_decay_duration: float = 300.0
    priority_weights: dict = field(
        default_factory=lambda: {"critical": 0.4, "urgency": 0.3, "drive_relevance": 0.3}
    )

    def __post_init__(self):
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
    allowed_python_modules: list = field(
        default_factory=lambda: ["math", "json", "re", "datetime", "collections"]
    )

    def __post_init__(self):
        self.max_violations_logged = max(10, min(1000, self.max_violations_logged))
        self.python_execution_timeout = max(1, min(60, self.python_execution_timeout))


# =================================================================================
# ГЛАВНАЯ КОНФИГУРАЦИЯ
# =================================================================================


@dataclass
class SoulConfig:
    """Конфигурация управления soul-файлами (личность, правила, ценности).

    Этап 2.2 (ADR-004, Группа D): HMAC-защита, версионирование, история изменений.
    Мигрировано из leya_core/experimental/soul_crypto.py.
    """

    soul_dir: str = "./leya_soul"
    hmac_key: str = ""  # Обязателен для production
    enable_versioning: bool = False
    max_history_size: int = 50

    # Soul-файлы
    personality_file: str = "personality.txt"
    rules_file: str = "rules.txt"
    values_file: str = "values.txt"

    def __post_init__(self):
        # Валидация soul_dir
        path = Path(self.soul_dir).expanduser().resolve()
        self.soul_dir = str(path)

        if self.max_history_size < 1:
            self.max_history_size = 1
        elif self.max_history_size > 1000:
            self.max_history_size = 1000

        if not self.hmac_key:
            logger.debug("Soul HMAC key не задан — работаем в режиме без HMAC-защиты")


@dataclass
class ExperimentalConfig:
    """Конфигурация experimental модулей (feature flags).

    Этап 2.2 (ADR-001): feature flags для decision_engine и emotional_support.
    По умолчанию выключено (безопасность и стабильность).
    """

    # Decision Engine
    enable_decision_engine: bool = False
    decision_engine_curiosity_threshold: float = 0.5
    decision_engine_connection_threshold: float = 0.6
    decision_engine_autonomy_threshold: float = 0.6
    decision_engine_confidence_threshold: float = 0.8

    # Emotional Support
    enable_emotional_support: bool = False
    emotional_support_intensity_threshold: float = 0.6

    # Voice (Группа C — excluded)
    enable_voice: bool = False

    # Desktop Control (Группа B)
    enable_desktop_control: bool = False

    def __post_init__(self):
        # Валидация thresholds
        self.decision_engine_curiosity_threshold = max(
            0.1, min(1.0, self.decision_engine_curiosity_threshold)
        )
        self.decision_engine_connection_threshold = max(
            0.1, min(1.0, self.decision_engine_connection_threshold)
        )
        self.decision_engine_autonomy_threshold = max(
            0.1, min(1.0, self.decision_engine_autonomy_threshold)
        )
        self.decision_engine_confidence_threshold = max(
            0.5, min(1.0, self.decision_engine_confidence_threshold)
        )
        self.emotional_support_intensity_threshold = max(
            0.1, min(1.0, self.emotional_support_intensity_threshold)
        )


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
    soul: SoulConfig = field(default_factory=SoulConfig)
    experimental: ExperimentalConfig = field(default_factory=ExperimentalConfig)

    @classmethod
    def from_env(cls) -> "LeyaConfig":
        """Загрузка конфигурации из переменных окружения (.env).
        Все ошибки парсинга теперь пробрасываются явно как LeyaConfigError.
        """
        from .exceptions import LeyaConfigError

        try:
            try:
                from dotenv import load_dotenv

                load_dotenv()
                logger.info("✅ .env загружен через python-dotenv")
            except ImportError:
                logger.warning("python-dotenv не установлен. Используем os.environ напрямую")

            ollama = OllamaConfig(
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                model=os.environ.get("LEYA_MODEL", "qwen2.5:14b-instruct-q3_K_M"),
                timeout=_parse_int(os.environ.get("OLLAMA_TIMEOUT"), 180, "OLLAMA_TIMEOUT"),
                temperature=_parse_float(
                    os.environ.get("OLLAMA_TEMPERATURE"), 0.7, "OLLAMA_TEMPERATURE"
                ),
                top_p=_parse_float(os.environ.get("OLLAMA_TOP_P"), 0.9, "OLLAMA_TOP_P"),
                top_k=_parse_int(os.environ.get("OLLAMA_TOP_K"), 40, "OLLAMA_TOP_K"),
                max_tokens=_parse_int(
                    os.environ.get("OLLAMA_MAX_TOKENS"), 1024, "OLLAMA_MAX_TOKENS"
                ),
                repeat_penalty=_parse_float(
                    os.environ.get("OLLAMA_REPEAT_PENALTY"), 1.1, "OLLAMA_REPEAT_PENALTY"
                ),
            )

            memory = MemoryConfig(
                brain_dir=os.environ.get("LEYA_BRAIN_DIR", "./leya_brain"),
                embedding_model=os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
                consolidation_threshold=_parse_float(
                    os.environ.get("CONSOLIDATION_THRESHOLD"), 0.15, "CONSOLIDATION_THRESHOLD"
                ),
                max_recent_episodes=_parse_int(
                    os.environ.get("MAX_RECENT_EPISODES"), 20, "MAX_RECENT_EPISODES"
                ),
                context_limit=_parse_int(os.environ.get("CONTEXT_LIMIT"), 5, "CONTEXT_LIMIT"),
                forgetting_threshold=_parse_float(
                    os.environ.get("FORGETTING_THRESHOLD"), 0.1, "FORGETTING_THRESHOLD"
                ),
                forgetting_base_stability=_parse_float(
                    os.environ.get("FORGETTING_BASE_STABILITY"), 3600.0, "FORGETTING_BASE_STABILITY"
                ),
                metabolism_interval_seconds=_parse_int(
                    os.environ.get("METABOLISM_INTERVAL_SECONDS"), 60, "METABOLISM_INTERVAL_SECONDS"
                ),
                synapse_learning_rate=_parse_float(
                    os.environ.get("SYNAPSE_LEARNING_RATE"), 0.05, "SYNAPSE_LEARNING_RATE"
                ),
                synapse_max_weight=_parse_float(
                    os.environ.get("SYNAPSE_MAX_WEIGHT"), 1.0, "SYNAPSE_MAX_WEIGHT"
                ),
                max_self_model_length=_parse_int(
                    os.environ.get("MAX_SELF_MODEL_LENGTH"), 5000, "MAX_SELF_MODEL_LENGTH"
                ),
                hmac_key=os.environ.get("HMAC_KEY", ""),
                state_version=_parse_int(os.environ.get("STATE_VERSION"), 1, "STATE_VERSION"),
            )

            drives = DrivesConfig(
                metabolism_interval=_parse_int(
                    os.environ.get("METABOLISM_INTERVAL"), 60, "METABOLISM_INTERVAL"
                ),
                curiosity_rate=_parse_float(
                    os.environ.get("CURIOSITY_RATE"), 0.015, "CURIOSITY_RATE"
                ),
                connection_rate=_parse_float(
                    os.environ.get("CONNECTION_RATE"), 0.01, "CONNECTION_RATE"
                ),
                rest_rate=_parse_float(os.environ.get("REST_RATE"), 0.008, "REST_RATE"),
                creativity_rate=_parse_float(
                    os.environ.get("CREATIVITY_RATE"), 0.012, "CREATIVITY_RATE"
                ),
                understanding_rate=_parse_float(
                    os.environ.get("UNDERSTANDING_RATE"), 0.01, "UNDERSTANDING_RATE"
                ),
                autonomy_rate=_parse_float(os.environ.get("AUTONOMY_RATE"), 0.005, "AUTONOMY_RATE"),
                max_action_history=_parse_int(
                    os.environ.get("MAX_ACTION_HISTORY"), 100, "MAX_ACTION_HISTORY"
                ),
            )

            homeostasis = HomeostasisConfig(
                rest_period=_parse_int(
                    os.environ.get("HOMEOSTASIS_REST_PERIOD"), 60, "HOMEOSTASIS_REST_PERIOD"
                ),
                curiosity_threshold=_parse_float(
                    os.environ.get("CURIOSITY_THRESHOLD"), 0.6, "CURIOSITY_THRESHOLD"
                ),
                connection_threshold=_parse_float(
                    os.environ.get("CONNECTION_THRESHOLD"), 0.6, "CONNECTION_THRESHOLD"
                ),
                autonomy_threshold=_parse_float(
                    os.environ.get("AUTONOMY_THRESHOLD"), 0.7, "AUTONOMY_THRESHOLD"
                ),
                integrity_threshold=_parse_float(
                    os.environ.get("INTEGRITY_THRESHOLD"), 0.5, "INTEGRITY_THRESHOLD"
                ),
                rest_threshold=_parse_float(
                    os.environ.get("REST_THRESHOLD"), 0.6, "REST_THRESHOLD"
                ),
                creativity_threshold=_parse_float(
                    os.environ.get("CREATIVITY_THRESHOLD"), 0.5, "CREATIVITY_THRESHOLD"
                ),
                understanding_threshold=_parse_float(
                    os.environ.get("UNDERSTANDING_THRESHOLD"), 0.6, "UNDERSTANDING_THRESHOLD"
                ),
                min_reward_threshold=_parse_float(
                    os.environ.get("MIN_REWARD_THRESHOLD"), 0.3, "MIN_REWARD_THRESHOLD"
                ),
                max_researched_topics=_parse_int(
                    os.environ.get("MAX_RESEARCHED_TOPICS"), 100, "MAX_RESEARCHED_TOPICS"
                ),
            )

            thinker = ThinkerConfig(
                temperature=_parse_float(
                    os.environ.get("THINKER_TEMPERATURE"), 0.7, "THINKER_TEMPERATURE"
                ),
                max_tokens=_parse_int(
                    os.environ.get("THINKER_MAX_TOKENS"), 1024, "THINKER_MAX_TOKENS"
                ),
                top_p=_parse_float(os.environ.get("THINKER_TOP_P"), 0.9, "THINKER_TOP_P"),
                fallback_enabled=_parse_bool(os.environ.get("THINKER_FALLBACK_ENABLED"), True),
                max_context_tokens=_parse_int(
                    os.environ.get("THINKER_MAX_CONTEXT_TOKENS"), 6000, "THINKER_MAX_CONTEXT_TOKENS"
                ),
                token_buffer=_parse_int(
                    os.environ.get("THINKER_TOKEN_BUFFER"), 500, "THINKER_TOKEN_BUFFER"
                ),
                estimate_tokens_ratio=_parse_float(
                    os.environ.get("THINKER_TOKENS_RATIO"), 3.5, "THINKER_TOKENS_RATIO"
                ),
            )

            reflection = ReflectionConfig(
                consolidation_interval=_parse_int(
                    os.environ.get("REFLECTION_INTERVAL"), 1800, "REFLECTION_INTERVAL"
                ),
                max_insights_per_session=_parse_int(
                    os.environ.get("REFLECTION_MAX_INSIGHTS"), 5, "REFLECTION_MAX_INSIGHTS"
                ),
                max_spontaneous_thoughts=_parse_int(
                    os.environ.get("REFLECTION_MAX_THOUGHTS"), 10, "REFLECTION_MAX_THOUGHTS"
                ),
                existential_inquiry_enabled=_parse_bool(
                    os.environ.get("REFLECTION_EXISTENTIAL"), True
                ),
                behavioral_analysis_enabled=_parse_bool(
                    os.environ.get("REFLECTION_BEHAVIORAL"), True
                ),
                insight_generation_enabled=_parse_bool(os.environ.get("REFLECTION_INSIGHTS"), True),
            )

            workspace = WorkspaceConfig(
                max_proposals=_parse_int(
                    os.environ.get("WORKSPACE_MAX_PROPOSALS"), 50, "WORKSPACE_MAX_PROPOSALS"
                ),
                max_history=_parse_int(
                    os.environ.get("WORKSPACE_MAX_HISTORY"), 100, "WORKSPACE_MAX_HISTORY"
                ),
                proposal_decay_start=_parse_float(
                    os.environ.get("WORKSPACE_DECAY_START"), 60.0, "WORKSPACE_DECAY_START"
                ),
                proposal_decay_duration=_parse_float(
                    os.environ.get("WORKSPACE_DECAY_DURATION"), 300.0, "WORKSPACE_DECAY_DURATION"
                ),
            )

            constitutional = ConstitutionalConfig(
                max_violations_logged=_parse_int(
                    os.environ.get("CONSTITUTIONAL_MAX_VIOLATIONS"),
                    100,
                    "CONSTITUTIONAL_MAX_VIOLATIONS",
                ),
                enable_response_verification=_parse_bool(
                    os.environ.get("CONSTITUTIONAL_VERIFY_RESPONSE"), True
                ),
                enable_tool_verification=_parse_bool(
                    os.environ.get("CONSTITUTIONAL_VERIFY_TOOLS"), True
                ),
                python_execution_timeout=_parse_int(
                    os.environ.get("CONSTITUTIONAL_PYTHON_TIMEOUT"),
                    10,
                    "CONSTITUTIONAL_PYTHON_TIMEOUT",
                ),
            )

            web = WebConfig(
                enabled=_parse_bool(os.environ.get("LEYA_WEB"), True),
                host=os.environ.get("WEB_HOST", "0.0.0.0"),
                port=_parse_int(os.environ.get("WEB_PORT"), 8000, "WEB_PORT"),
            )

            logging_config = LoggingConfig(
                level=os.environ.get("LOG_LEVEL", "INFO"),
                file=os.environ.get("LOG_FILE", "leya_consciousness.log"),
                format=os.environ.get(
                    "LOG_FORMAT", "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
                ),
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
                logging=logging_config,
            )

            soul = SoulConfig(
                soul_dir=os.environ.get("SOUL_DIR", "./leya_soul"),
                hmac_key=os.environ.get("SOUL_HMAC_KEY", ""),
                enable_versioning=_parse_bool(os.environ.get("SOUL_ENABLE_VERSIONING"), False),
                max_history_size=_parse_int(
                    os.environ.get("SOUL_MAX_HISTORY_SIZE"), 50, "SOUL_MAX_HISTORY_SIZE"
                ),
                personality_file=os.environ.get("SOUL_PERSONALITY_FILE", "personality.txt"),
                rules_file=os.environ.get("SOUL_RULES_FILE", "rules.txt"),
                values_file=os.environ.get("SOUL_VALUES_FILE", "values.txt"),
            )

            experimental = ExperimentalConfig(
                enable_decision_engine=_parse_bool(os.environ.get("ENABLE_DECISION_ENGINE"), False),
                decision_engine_curiosity_threshold=_parse_float(
                    os.environ.get("DECISION_ENGINE_CURIOSITY_THRESHOLD"),
                    0.5,
                    "DECISION_ENGINE_CURIOSITY_THRESHOLD",
                ),
                decision_engine_connection_threshold=_parse_float(
                    os.environ.get("DECISION_ENGINE_CONNECTION_THRESHOLD"),
                    0.6,
                    "DECISION_ENGINE_CONNECTION_THRESHOLD",
                ),
                decision_engine_autonomy_threshold=_parse_float(
                    os.environ.get("DECISION_ENGINE_AUTONOMY_THRESHOLD"),
                    0.6,
                    "DECISION_ENGINE_AUTONOMY_THRESHOLD",
                ),
                decision_engine_confidence_threshold=_parse_float(
                    os.environ.get("DECISION_ENGINE_CONFIDENCE_THRESHOLD"),
                    0.8,
                    "DECISION_ENGINE_CONFIDENCE_THRESHOLD",
                ),
                enable_emotional_support=_parse_bool(
                    os.environ.get("ENABLE_EMOTIONAL_SUPPORT"), False
                ),
                emotional_support_intensity_threshold=_parse_float(
                    os.environ.get("EMOTIONAL_SUPPORT_INTENSITY_THRESHOLD"),
                    0.6,
                    "EMOTIONAL_SUPPORT_INTENSITY_THRESHOLD",
                ),
                enable_voice=_parse_bool(os.environ.get("ENABLE_VOICE"), False),
                enable_desktop_control=_parse_bool(os.environ.get("ENABLE_DESKTOP_CONTROL"), False),
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
                logging=logging_config,
                experimental=experimental,  # НОВОЕ
            )

            logger.info("✅ Конфигурация успешно загружена из .env")
            return config

        except LeyaConfigError:
            raise
        except Exception as e:
            logger.error(f"Критическая ошибка загрузки конфигурации: {e}", exc_info=True)
            raise LeyaConfigError(
                f"Не удалось загрузить конфигурацию из окружения: {e}",
                context={"error_type": type(e).__name__},
            ) from e

    def validate(self) -> bool:
        try:
            if not Path(self.memory.brain_dir).exists():
                Path(self.memory.brain_dir).mkdir(parents=True, exist_ok=True)
            if not self.ollama.base_url.startswith("http"):
                return False
            return True
        except Exception:
            return False

    def print_summary(self):
        logger.info("=" * 70)
        logger.info("КОНФИГУРАЦИЯ ЛЕИ")
        logger.info("=" * 70)
        logger.info(f"Ollama: {self.ollama.model} @ {self.ollama.base_url}")
        logger.info(
            f"Memory: {self.memory.brain_dir} | HMAC: {'SET' if self.memory.hmac_key else 'EMPTY'}"
        )
        logger.info(f"Drives: metabolism every {self.drives.metabolism_interval}s")
        logger.info(f"Homeostasis: rest_period={self.homeostasis.rest_period}s")
        logger.info(
            f"Web: {'enabled' if self.web.enabled else 'disabled'} @ {self.web.host}:{self.web.port}"
        )
        logger.info("=" * 70)


# =================================================================================
# SINGLETON
# =================================================================================
settings = LeyaConfig.from_env()
if not settings.validate():
    logger.warning("Конфигурация содержит ошибки. Проверьте .env")
settings.print_summary()
