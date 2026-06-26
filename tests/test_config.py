"""
Тесты для конфигурации LeyaOS.

Проверяет:
- Валидацию MemoryConfig
- Валидацию DrivesConfig
- Валидацию ThinkerConfig
- LeyaConfig.from_env()
"""

from __future__ import annotations

from pathlib import Path

import pytest

from leya_core.config import (
    DrivesConfig,
    LeyaConfig,
    MemoryConfig,
    ThinkerConfig,
)
from leya_core.exceptions import LeyaConfigError


class TestMemoryConfig:
    """Тесты MemoryConfig."""

    def test_valid_config(self, tmp_path):
        """Валидная конфигурация создаётся без ошибок."""
        config = MemoryConfig(brain_dir=str(tmp_path / "brain"))
        assert Path(config.brain_dir).exists()

    def test_creates_brain_dir(self, tmp_path):
        brain_dir = tmp_path / "new_brain"
        MemoryConfig(brain_dir=str(brain_dir))  # Просто вызываем
        assert brain_dir.exists()

    def test_invalid_forgetting_threshold(self, tmp_path):
        """Невалидный forgetting_threshold бросает LeyaConfigError."""
        with pytest.raises(LeyaConfigError):
            MemoryConfig(
                brain_dir=str(tmp_path),
                forgetting_threshold=1.5,  # Должен быть в (0, 1)
            )

    def test_invalid_metabolism_interval(self, tmp_path):
        """Невалидный metabolism_interval бросает LeyaConfigError."""
        with pytest.raises(LeyaConfigError):
            MemoryConfig(
                brain_dir=str(tmp_path),
                metabolism_interval_seconds=0,  # Должен быть > 0
            )


class TestDrivesConfig:
    """Тесты DrivesConfig."""

    def test_valid_config(self):
        """Валидная конфигурация создаётся без ошибок."""
        config = DrivesConfig()
        assert config.metabolism_interval > 0
        assert config.curiosity_rate > 0

    def test_custom_rates(self):
        """Кастомные rates применяются."""
        config = DrivesConfig(
            curiosity_rate=0.05,
            connection_rate=0.03,
        )
        assert config.curiosity_rate == 0.05
        assert config.connection_rate == 0.03


class TestThinkerConfig:
    """Тесты ThinkerConfig."""

    def test_valid_config(self):
        """Валидная конфигурация создаётся без ошибок."""
        config = ThinkerConfig()
        assert 0.0 <= config.temperature <= 2.0
        assert config.max_tokens > 0

    def test_temperature_clamped(self):
        """Temperature ограничивается диапазоном [0, 2]."""
        config = ThinkerConfig(temperature=5.0)
        assert config.temperature == 2.0

    def test_max_tokens_clamped(self):
        """max_tokens ограничивается диапазоном [128, 8192]."""
        config = ThinkerConfig(max_tokens=100000)
        assert config.max_tokens == 8192


class TestLeyaConfig:
    """Тесты LeyaConfig."""

    def test_default_config(self):
        """Конфигурация по умолчанию создаётся без ошибок."""
        config = LeyaConfig()
        assert config.ollama is not None
        assert config.memory is not None
        assert config.drives is not None

    def test_from_env(self, tmp_path, monkeypatch):
        """from_env() загружает конфигурацию из окружения."""
        # Устанавливаем переменные окружения
        monkeypatch.setenv("LEYA_BRAIN_DIR", str(tmp_path / "brain"))
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://test:11434")
        monkeypatch.setenv("LEYA_MODEL", "test-model")

        config = LeyaConfig.from_env()

        assert config.ollama.base_url == "http://test:11434"
        assert config.ollama.model == "test-model"

    def test_validate(self, tmp_path):
        """validate() возвращает True для валидной конфигурации."""
        config = LeyaConfig()
        config.memory.brain_dir = str(tmp_path / "brain")

        assert config.validate() is True
