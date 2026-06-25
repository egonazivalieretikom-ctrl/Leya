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


@dataclass
class MemoryConfig:
    """Конфигурация системы памяти."""
    brain_dir: str = "./leya_brain"
    embedding_model: str = "all-MiniLM-L6-v2"
    consolidation_threshold: float = 0.15
    max_recent_episodes: int = 20
    context_limit: int = 5
    
    def __post_init__(self):
        """Валидация значений."""
        # Создание директории если не существует
        Path(self.brain_dir).mkdir(parents=True, exist_ok=True)
        
        self.consolidation_threshold = max(0.0, min(1.0, self.consolidation_threshold))
        self.max_recent_episodes = max(5, min(100, self.max_recent_episodes))
        self.context_limit = max(1, min(20, self.context_limit))


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
    
    def __post_init__(self):
        """Валидация значений."""
        self.temperature = max(0.0, min(2.0, self.temperature))
        self.max_tokens = max(128, min(8192, self.max_tokens))
        self.top_p = max(0.0, min(1.0, self.top_p))


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


# =================================================================================
# ГЛАВНАЯ КОНФИГУРАЦИЯ
# =================================================================================

@dataclass
class LeyaConfig:
    """Главная конфигурация системы Леи."""
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    drives: DrivesConfig = field(default_factory=DrivesConfig)
    homeostasis: HomeostasisConfig = field(default_factory=HomeostasisConfig)
    thinker: ThinkerConfig = field(default_factory=ThinkerConfig)
    web: WebConfig = field(default_factory=WebConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    @classmethod
    def from_env(cls) -> "LeyaConfig":
        """
        Загрузка конфигурации из переменных окружения (.env).
        
        Returns:
            LeyaConfig с загруженными значениями
        """
        try:
            # Попытка загрузить .env через python-dotenv
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
                fallback_enabled=os.environ.get("THINKER_FALLBACK_ENABLED", "true").lower() == "true"
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
        """
        Валидация всей конфигурации.
        
        Returns:
            True если конфигурация валидна
        """
        try:
            # Проверка критических путей
            if not Path(self.memory.brain_dir).exists():
                logger.warning(f"Директория памяти не существует: {self.memory.brain_dir}")
                Path(self.memory.brain_dir).mkdir(parents=True, exist_ok=True)
            
            # Проверка Ollama URL
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
        logger.info(f"Thinker: temp={self.thinker.temperature}, max_tokens={self.thinker.max_tokens}")
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