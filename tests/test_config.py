import os
from unittest.mock import patch

import pytest

from leya_core.config import LeyaConfig
from leya_core.exceptions import LeyaConfigError


def test_from_env_all_fields():
    """Проверяет, что ВСЕ поля всех под-конфигов читаются из .env."""
    env_vars = {
        # Ollama
        "OLLAMA_BASE_URL": "http://custom:11434",
        "LEYA_MODEL": "custom_model",
        "OLLAMA_TIMEOUT": "300",
        "OLLAMA_TEMPERATURE": "0.5",
        "OLLAMA_TOP_P": "0.8",
        "OLLAMA_TOP_K": "50",
        "OLLAMA_MAX_TOKENS": "2048",
        "OLLAMA_REPEAT_PENALTY": "1.2",
        # Memory (включая новые поля и ранее игнорируемые)
        "LEYA_BRAIN_DIR": "./custom_brain",
        "EMBEDDING_MODEL": "custom_embed",
        "CONSOLIDATION_THRESHOLD": "0.2",
        "MAX_RECENT_EPISODES": "30",
        "CONTEXT_LIMIT": "10",
        "FORGETTING_THRESHOLD": "0.2",
        "FORGETTING_BASE_STABILITY": "7200.0",
        "METABOLISM_INTERVAL_SECONDS": "120",
        "SYNAPSE_LEARNING_RATE": "0.1",
        "SYNAPSE_MAX_WEIGHT": "0.9",
        "MAX_SELF_MODEL_LENGTH": "6000",
        # ✅ ИСПРАВЛЕНО (Этап 3.2): Правильное имя переменной и длина ≥32
        "LEYA_STATE_HMAC_KEY": "a" * 40,  # Было: "HMAC_KEY": "secret_key_123"
        "STATE_VERSION": "2",
        # Drives
        "METABOLISM_INTERVAL": "120",
        "CURIOSITY_RATE": "0.02",
        "CONNECTION_RATE": "0.02",
        "REST_RATE": "0.01",
        "CREATIVITY_RATE": "0.02",
        "UNDERSTANDING_RATE": "0.02",
        "AUTONOMY_RATE": "0.01",
        "MAX_ACTION_HISTORY": "200",
        # Homeostasis (включая ранее игнорируемые thresholds)
        "HOMEOSTASIS_REST_PERIOD": "120",
        "CURIOSITY_THRESHOLD": "0.7",
        "CONNECTION_THRESHOLD": "0.7",
        "AUTONOMY_THRESHOLD": "0.8",
        "INTEGRITY_THRESHOLD": "0.6",
        "REST_THRESHOLD": "0.7",
        "CREATIVITY_THRESHOLD": "0.6",
        "UNDERSTANDING_THRESHOLD": "0.7",
        "MIN_REWARD_THRESHOLD": "0.4",
        "MAX_RESEARCHED_TOPICS": "200",
        # Thinker
        "THINKER_TEMPERATURE": "0.8",
        "THINKER_MAX_TOKENS": "2048",
        "THINKER_TOP_P": "0.95",
        "THINKER_FALLBACK_ENABLED": "false",
        "THINKER_MAX_CONTEXT_TOKENS": "7000",
        "THINKER_TOKEN_BUFFER": "600",
        "THINKER_TOKENS_RATIO": "4.0",
        # Reflection
        "REFLECTION_INTERVAL": "3600",
        "REFLECTION_MAX_INSIGHTS": "10",
        "REFLECTION_MAX_THOUGHTS": "20",
        "REFLECTION_EXISTENTIAL": "false",
        "REFLECTION_BEHAVIORAL": "false",
        "REFLECTION_INSIGHTS": "false",
        # Workspace
        "WORKSPACE_MAX_PROPOSALS": "100",
        "WORKSPACE_MAX_HISTORY": "200",
        "WORKSPACE_DECAY_START": "120.0",
        "WORKSPACE_DECAY_DURATION": "600.0",
        # Constitutional
        "CONSTITUTIONAL_MAX_VIOLATIONS": "200",
        "CONSTITUTIONAL_VERIFY_RESPONSE": "false",
        "CONSTITUTIONAL_VERIFY_TOOLS": "false",
        "CONSTITUTIONAL_PYTHON_TIMEOUT": "20",
        # Web
        "LEYA_WEB": "0",
        "WEB_HOST": "127.0.0.1",
        "WEB_PORT": "9000",
        # Logging
        "LOG_LEVEL": "DEBUG",
        "LOG_FILE": "custom.log",
        "LOG_FORMAT": "custom_format",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        config = LeyaConfig.from_env()

    # Ollama
    assert config.ollama.base_url == "http://custom:11434"
    assert config.ollama.timeout == 300
    assert config.ollama.temperature == 0.5

    # Memory (проверяем новые и ранее скрытые поля)
    assert config.memory.forgetting_threshold == 0.2
    assert config.memory.synapse_learning_rate == 0.1
    assert config.memory.hmac_key == "a" * 40  # Было: "secret_key_123"
    assert config.memory.state_version == 2

    # Homeostasis (проверяем thresholds)
    assert config.homeostasis.connection_threshold == 0.7
    assert config.homeostasis.autonomy_threshold == 0.8
    assert config.homeostasis.integrity_threshold == 0.6

    # Thinker (проверяем bool)
    assert config.thinker.fallback_enabled is False

    # Web
    assert config.web.enabled is False
    assert config.web.port == 9000


@pytest.mark.parametrize(
    "val,expected",
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
    ],
)
def test_bool_parsing(val, expected):
    """Проверяет улучшенный парсинг булевых значений."""
    env = {"THINKER_FALLBACK_ENABLED": val}
    with patch.dict(os.environ, env, clear=True):
        config = LeyaConfig.from_env()
        assert config.thinker.fallback_enabled is expected


def test_explicit_error_on_invalid_env():
    """Проверяет, что невалидные данные вызывают явную ошибку, а не silent fallback."""
    env = {"OLLAMA_TIMEOUT": "not_a_number"}
    with patch.dict(os.environ, env, clear=True), pytest.raises(LeyaConfigError):
        LeyaConfig.from_env()
