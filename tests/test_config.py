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

# =================================================================================
# HMAC VALIDATION TESTS
# =================================================================================
class TestHMACValidation:
    """Тесты валидации HMAC-ключа в MemoryConfig."""

    def test_short_hmac_key_raises_error(self, tmp_path):
        """Короткий HMAC-ключ (< 32 символов) → LeyaConfigError."""
        from leya_core.config import MemoryConfig
        from leya_core.exceptions import LeyaConfigError

        with pytest.raises(LeyaConfigError) as exc_info:
            MemoryConfig(
                brain_dir=str(tmp_path),
                hmac_key="short_key",  # < 32 символов
                unsafe_mode=False,
            )
        assert "HMAC_KEY" in str(exc_info.value) or "короче 32" in str(exc_info.value)

    def test_empty_hmac_key_raises_error(self, tmp_path):
        """Пустой HMAC-ключ → LeyaConfigError (без unsafe_mode)."""
        from leya_core.config import MemoryConfig
        from leya_core.exceptions import LeyaConfigError

        with pytest.raises(LeyaConfigError):
            MemoryConfig(
                brain_dir=str(tmp_path),
                hmac_key="",
                unsafe_mode=False,
            )

    def test_strong_hmac_key_accepted(self, tmp_path):
        """Сильный HMAC-ключ (≥32 символов) → OK."""
        from leya_core.config import MemoryConfig

        config = MemoryConfig(
            brain_dir=str(tmp_path),
            hmac_key="a" * 32,  # Ровно 32 символа
            unsafe_mode=False,
        )
        assert config.hmac_key == "a" * 32

    def test_unsafe_mode_allows_empty_key(self, tmp_path):
        """unsafe_mode=True разрешает пустой ключ (warning, но не ошибка)."""
        from leya_core.config import MemoryConfig

        config = MemoryConfig(
            brain_dir=str(tmp_path),
            hmac_key="",
            unsafe_mode=True,
        )
        assert config.hmac_key == ""


# =================================================================================
# INT/FLOAT PARSING TESTS
# =================================================================================
class TestIntFloatParsing:
    """Тесты парсинга int и float в config.py."""

    def test_parse_int_valid(self):
        """Валидный int → корректное значение."""
        from leya_core.config import _parse_int

        assert _parse_int("42", 0, "test_field") == 42
        assert _parse_int("0", 10, "test_field") == 0
        assert _parse_int("-5", 0, "test_field") == -5

    def test_parse_int_none_returns_default(self):
        """None → default значение."""
        from leya_core.config import _parse_int

        assert _parse_int(None, 100, "test_field") == 100

    def test_parse_int_invalid_raises_error(self):
        """Невалидный int → LeyaConfigError."""
        from leya_core.config import _parse_int
        from leya_core.exceptions import LeyaConfigError

        with pytest.raises(LeyaConfigError) as exc_info:
            _parse_int("not_a_number", 0, "OLLAMA_TIMEOUT")
        assert "целое число" in str(exc_info.value)

    def test_parse_float_valid(self):
        """Валидный float → корректное значение."""
        from leya_core.config import _parse_float

        assert _parse_float("3.14", 0.0, "test_field") == 3.14
        assert _parse_float("0.5", 1.0, "test_field") == 0.5
        assert _parse_float("-2.7", 0.0, "test_field") == -2.7

    def test_parse_float_none_returns_default(self):
        """None → default значение."""
        from leya_core.config import _parse_float

        assert _parse_float(None, 2.5, "test_field") == 2.5

    def test_parse_float_invalid_raises_error(self):
        """Невалидный float → LeyaConfigError."""
        from leya_core.config import _parse_float
        from leya_core.exceptions import LeyaConfigError

        with pytest.raises(LeyaConfigError) as exc_info:
            _parse_float("not_a_number", 0.0, "OLLAMA_TEMPERATURE")
        assert "число" in str(exc_info.value)


# =================================================================================
# ENV LOADING EDGE CASES
# =================================================================================
class TestEnvLoadingEdgeCases:
    """Тесты загрузки конфигурации из .env с edge cases."""

    def test_missing_env_uses_defaults(self, monkeypatch):
        """Отсутствующие переменные окружения → default значения."""
        from leya_core.config import LeyaConfig

        # Очищаем все переменные окружения Leya
        for key in list(os.environ.keys()):
            if key.startswith("LEYA_") or key.startswith("OLLAMA_"):
                monkeypatch.delenv(key, raising=False)

        # Устанавливаем unsafe_mode, чтобы избежать ошибки HMAC
        monkeypatch.setenv("LEYA_UNSAFE_MODE", "1")

        config = LeyaConfig.from_env()
        assert config.ollama.model == "qwen2.5:14b-instruct-q3_K_M"
        assert config.memory.embedding_model == "all-MiniLM-L6-v2"

    def test_partial_env_loading(self, monkeypatch, tmp_path):
        """Частичная загрузка: некоторые переменные заданы, другие — default."""
        from leya_core.config import LeyaConfig

        monkeypatch.setenv("LEYA_UNSAFE_MODE", "1")
        monkeypatch.setenv("OLLAMA_TEMPERATURE", "0.9")
        monkeypatch.setenv("LEYA_BRAIN_DIR", str(tmp_path))

        config = LeyaConfig.from_env()
        assert config.ollama.temperature == 0.9
        assert config.memory.brain_dir == str(tmp_path)
        # Остальные поля — default
        assert config.ollama.timeout == 180