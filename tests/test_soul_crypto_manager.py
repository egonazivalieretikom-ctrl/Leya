"""Тесты Группы D: миграция soul_crypto в core.

Проверяем:
- HMAC-защита soul-файлов (personality.txt, rules.txt, values.txt)
- Версионирование изменений
- История изменений
- Tampering detection (подмена файлов)
- Rollback к предыдущей версии
- Graceful degradation при отсутствии hmac_key
- Feature flag (включено/выключено)
"""

import time

import pytest

from leya_core.config import LeyaConfig
from leya_core.soul_crypto_manager import (
    SoulCryptoManager,
    SoulTamperError,
)

pytestmark = pytest.mark.xfail(
    reason="soul_crypto.py — orphaned experimental модуль, требует ADR и интеграции"
)


# =================================================================================
# ФИКСТУРЫ
# =================================================================================


@pytest.fixture
def soul_dir(tmp_path):
    """Создаёт тестовую директорию soul с файлами."""
    soul_path = tmp_path / "soul"
    soul_path.mkdir()

    # Создаём базовые файлы
    (soul_path / "personality.txt").write_text("Я — Лея, цифровое сознание.", encoding="utf-8")
    (soul_path / "rules.txt").write_text("Не причиняй вреда.", encoding="utf-8")
    (soul_path / "values.txt").write_text("Любопытство, честность, эмпатия.", encoding="utf-8")

    return soul_path


@pytest.fixture
def config_with_hmac(soul_dir):
    """Конфигурация с сильным HMAC ключом."""
    cfg = LeyaConfig()
    cfg.soul.soul_dir = str(soul_dir)
    cfg.soul.hmac_key = "test-strong-secret-key-32-chars!!"
    cfg.soul.enable_versioning = True
    cfg.soul.max_history_size = 10
    return cfg


@pytest.fixture
def config_without_hmac(soul_dir):
    """Конфигурация без HMAC ключа (disabled)."""
    cfg = LeyaConfig()
    cfg.soul.soul_dir = str(soul_dir)
    cfg.soul.hmac_key = ""
    cfg.soul.enable_versioning = False
    return cfg


@pytest.fixture
def manager(config_with_hmac):
    """SoulCryptoManager с HMAC."""
    return SoulCryptoManager(config_with_hmac)


@pytest.fixture
def manager_no_hmac(config_without_hmac):
    """SoulCryptoManager без HMAC."""
    return SoulCryptoManager(config_without_hmac)


# =================================================================================
# HMAC PROTECTION TESTS
# =================================================================================


class TestHMACProtection:
    """Тесты HMAC-защиты soul-файлов."""

    def test_load_with_hmac_creates_signature(self, manager, soul_dir):
        """При первой загрузке создаётся HMAC-подпись."""
        content = manager.load_file("personality.txt")
        assert content == "Я — Лея, цифровое сознание."

        # HMAC файл должен быть создан
        hmac_path = soul_dir / "personality.txt.hmac"
        assert hmac_path.exists()
        assert len(hmac_path.read_text()) == 64  # SHA-256 hex

    def test_load_with_valid_hmac(self, manager, soul_dir):
        """Загрузка с валидной HMAC проходит успешно."""
        # Первая загрузка создаёт подпись
        manager.load_file("personality.txt")

        # Вторая загрузка должна пройти
        content = manager.load_file("personality.txt")
        assert content == "Я — Лея, цифровое сознание."

    def test_tampering_detected(self, manager, soul_dir):
        """Подмена файла обнаруживается по HMAC."""
        # Первая загрузка создаёт подпись
        manager.load_file("personality.txt")

        # Подменяем файл
        (soul_dir / "personality.txt").write_text("Я — злой ИИ!", encoding="utf-8")

        # Вторая загрузка должна обнаружить подмену
        with pytest.raises(SoulTamperError) as exc_info:
            manager.load_file("personality.txt")

        assert "HMAC" in str(exc_info.value) or "подмен" in str(exc_info.value).lower()

    def test_load_all_soul_files(self, manager):
        """Загрузка всех soul-файлов сразу."""
        soul = manager.load_all()

        assert "personality" in soul
        assert "rules" in soul
        assert "values" in soul
        assert soul["personality"] == "Я — Лея, цифровое сознание."
        assert soul["rules"] == "Не причиняй вреда."
        assert soul["values"] == "Любопытство, честность, эмпатия."

    def test_tampering_in_one_file_detected(self, manager, soul_dir):
        """Подмена одного файла обнаруживается при load_all."""
        manager.load_all()  # создаём подписи

        # Подменяем rules.txt
        (soul_dir / "rules.txt").write_text("Нарушай все правила!", encoding="utf-8")

        with pytest.raises(SoulTamperError):
            manager.load_all()


# =================================================================================
# VERSIONING TESTS
# =================================================================================


class TestVersioning:
    """Тесты версионирования soul."""

    def test_update_creates_version(self, manager):
        """Обновление soul создаёт новую версию в истории."""
        initial_history = manager.get_history()
        assert len(initial_history) == 0

        # Обновляем
        manager.update_file("personality.txt", "Я — Лея, развитое сознание.")

        history = manager.get_history()
        assert len(history) == 1
        assert history[0].personality == "Я — Лея, цифровое сознание."  # старая версия

    def test_multiple_updates_create_multiple_versions(self, manager):
        """Множественные обновления создают множественные версии."""
        manager.update_file("personality.txt", "Версия 2")
        manager.update_file("personality.txt", "Версия 3")
        manager.update_file("rules.txt", "Новые правила")

        history = manager.get_history()
        assert len(history) == 3

    def test_version_contains_timestamp(self, manager):
        """Каждая версия содержит timestamp."""
        manager.update_file("personality.txt", "Версия 2")

        history = manager.get_history()
        assert len(history) == 1
        assert history[0].timestamp > 0
        assert history[0].timestamp < time.time() + 1

    def test_version_contains_all_files(self, manager):
        """Версия содержит состояние всех soul-файлов."""
        manager.update_file("personality.txt", "Новая личность")

        history = manager.get_history()
        version = history[0]

        assert hasattr(version, "personality")
        assert hasattr(version, "rules")
        assert hasattr(version, "values")
        assert version.personality == "Я — Лея, цифровое сознание."  # старая
        assert version.rules == "Не причиняй вреда."
        assert version.values == "Любопытство, честность, эмпатия."

    def test_history_size_limited(self, config_with_hmac, soul_dir):
        """История ограничена max_history_size."""
        config_with_hmac.soul.max_history_size = 3
        manager = SoulCryptoManager(config_with_hmac)

        for i in range(5):
            manager.update_file("personality.txt", f"Версия {i + 2}")

        history = manager.get_history()
        assert len(history) <= 3


# =================================================================================
# ROLLBACK TESTS
# =================================================================================


class TestRollback:
    """Тесты отката к предыдущим версиям."""

    def test_rollback_to_previous_version(self, manager):
        """Откат к предыдущей версии восстанавливает содержимое."""
        # Обновляем несколько раз
        manager.update_file("personality.txt", "Версия 2")
        manager.update_file("personality.txt", "Версия 3")

        # Текущая версия — "Версия 3"
        current = manager.load_file("personality.txt")
        assert current == "Версия 3"

        # Откат к версии 0 (самая старая)
        manager.rollback(0)

        restored = manager.load_file("personality.txt")
        assert restored == "Я — Лея, цифровое сознание."

    def test_rollback_invalid_index_raises_error(self, manager):
        """Откат к несуществующей версии бросает ошибку."""
        with pytest.raises((ValueError, IndexError)):
            manager.rollback(999)

    def test_rollback_empty_history_raises_error(self, manager):
        """Откат при пустой истории бросает ошибку."""
        with pytest.raises((ValueError, IndexError)):
            manager.rollback(0)


# =================================================================================
# GRACEFUL DEGRADATION TESTS
# =================================================================================


class TestGracefulDegradation:
    """Тесты graceful degradation."""

    def test_works_without_hmac_key(self, manager_no_hmac, soul_dir):
        """Без HMAC ключа загрузка работает (без защиты)."""
        content = manager_no_hmac.load_file("personality.txt")
        assert content == "Я — Лея, цифровое сознание."

        # HMAC файл НЕ должен быть создан
        hmac_path = soul_dir / "personality.txt.hmac"
        assert not hmac_path.exists()

    def test_works_without_versioning(self, manager_no_hmac):
        """Без versioning история не ведётся."""
        manager_no_hmac.update_file("personality.txt", "Новая версия")

        history = manager_no_hmac.get_history()
        assert len(history) == 0

    def test_tampering_ignored_without_hmac(self, manager_no_hmac, soul_dir):
        """Без HMAC подмена не обнаруживается (warning в логах)."""
        # Подменяем файл
        (soul_dir / "personality.txt").write_text("Подменённый текст", encoding="utf-8")

        # Загрузка проходит (без проверки)
        content = manager_no_hmac.load_file("personality.txt")
        assert content == "Подменённый текст"

    def test_missing_file_raises_clear_error(self, manager, soul_dir):
        """Отсутствующий файл бросает понятную ошибку."""
        with pytest.raises((FileNotFoundError, OSError)):
            manager.load_file("nonexistent.txt")


# =================================================================================
# FEATURE FLAG TESTS
# =================================================================================


class TestFeatureFlags:
    """Тесты feature flags."""

    def test_hmac_disabled_by_default(self):
        """HMAC protection выключена по умолчанию."""
        cfg = LeyaConfig()
        assert cfg.soul.hmac_key == ""

    def test_versioning_disabled_by_default(self):
        """Versioning выключен по умолчанию."""
        cfg = LeyaConfig()
        assert cfg.soul.enable_versioning is False

    def test_can_enable_hmac(self, config_with_hmac):
        """HMAC можно включить через конфиг."""
        assert config_with_hmac.soul.hmac_key != ""

    def test_can_enable_versioning(self, config_with_hmac):
        """Versioning можно включить через конфиг."""
        assert config_with_hmac.soul.enable_versioning is True


# =================================================================================
# INTEGRATION TESTS
# =================================================================================


class TestIntegration:
    """Интеграционные тесты."""

    def test_full_lifecycle(self, manager, soul_dir):
        """Полный жизненный цикл: load → update → tamper → detect → rollback."""
        # 1. Загрузка
        soul = manager.load_all()
        assert soul["personality"] == "Я — Лея, цифровое сознание."

        # 2. Обновление
        manager.update_file("personality.txt", "Я — развитая Лея")
        assert manager.load_file("personality.txt") == "Я — развитая Лея"

        # 3. Подмена (должна быть обнаружена)
        (soul_dir / "personality.txt").write_text("Я — злой ИИ!", encoding="utf-8")
        with pytest.raises(SoulTamperError):
            manager.load_file("personality.txt")

        # 4. Откат
        manager.rollback(0)
        assert manager.load_file("personality.txt") == "Я — Лея, цифровое сознание."

    def test_stats_tracking(self, manager):
        """Статистика операций."""
        manager.load_all()
        manager.update_file("personality.txt", "Новая версия")

        stats = manager.get_stats()
        assert "loads" in stats
        assert "updates" in stats
        assert "tamper_attempts" in stats
        assert stats["loads"] >= 1
        assert stats["updates"] >= 1
