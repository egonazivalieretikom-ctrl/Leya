# leya_core/soul_crypto_manager.py — Управление soul-файлами с HMAC-защитой.
# Этап 2.2 (ADR-004, Группа D): миграция из experimental/soul_crypto.py.
# HMAC-SHA256 защита, версионирование, история изменений, rollback.

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import SoulConfig
from .exceptions import LeyaError

logger = logging.getLogger("LeyaSoulCryptoManager")


# =================================================================================
# ИСКЛЮЧЕНИЯ
# =================================================================================


class SoulTamperError(LeyaError):
    """Обнаружена подмена soul-файла (HMAC не совпадает)."""


class SoulVersionError(LeyaError):
    """Ошибка работы с версиями soul."""


# =================================================================================
# DATA MODELS
# =================================================================================


@dataclass
class SoulVersion:
    """Снимок состояния soul на определённый момент времени.

    Используется для версионирования и отката.
    """

    timestamp: float
    personality: str
    rules: str
    values: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "personality": self.personality,
            "rules": self.rules,
            "values": self.values,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SoulVersion":
        return cls(
            timestamp=data["timestamp"],
            personality=data["personality"],
            rules=data["rules"],
            values=data["values"],
            metadata=data.get("metadata", {}),
        )


# =================================================================================
# SOUL CRYPTO MANAGER
# =================================================================================


class SoulCryptoManager:
    """Менеджер soul-файлов с HMAC-защитой и версионированием.

    Этап 2.2 (ADR-004): мигрировано из experimental/soul_crypto.py.

    Функции:
    - HMAC-SHA256 защита целостности soul-файлов
    - Версионирование изменений (история)
    - Откат к предыдущим версиям (rollback)
    - Graceful degradation: без HMAC ключа работает без защиты

    Soul-файлы:
    - personality.txt — личность Леи
    - rules.txt — правила поведения
    - values.txt — ценности
    """

    def __init__(self, config: SoulConfig):
        """Инициализация SoulCryptoManager.

        Args:
            config: Конфигурация soul (soul_dir, hmac_key, versioning)
        """
        self.config = config
        if hasattr(config, "soul_dir"):
            self.soul_dir = Path(config.soul_dir)
        elif hasattr(config, "soul") and hasattr(config.soul, "soul_dir"):
            self.soul_dir = Path(config.soul.soul_dir)
        else:
            raise ValueError("Конфигурация должна содержать soul_dir или soul.soul_dir")
        # 2. СНАЧАЛА инициализируем _hmac_key
        hmac_key_value = None
        if hasattr(config, "hmac_key"):
            hmac_key_value = config.hmac_key
        elif hasattr(config, "soul") and hasattr(config.soul, "hmac_key"):
            hmac_key_value = config.soul.hmac_key
        self._hmac_key = hmac_key_value.encode("utf-8") if hmac_key_value else b""

        # 3. СНАЧАЛА инициализируем enable_versioning
        self._enable_versioning = (
            getattr(config, "enable_versioning", False)
            or getattr(getattr(config, "soul", None), "enable_versioning", False)
            or getattr(getattr(config, "experimental", None), "enable_versioning", False)
        )
        # Создаём директорию, если её нет
        try:
            self.soul_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Не удалось создать soul_dir {self.soul_dir}: {e}")
            raise

        # История версий
        self._history: list[SoulVersion] = []
        self._history_file = self.soul_dir / ".soul_history.json"
        self._load_history()

        # Статистика
        self._stats = {
            "loads": 0,
            "updates": 0,
            "tamper_attempts": 0,
            "rollbacks": 0,
        }

        # Поддержка обоих вариантов: прямой enable_versioning и вложенный experimental.enable_versioning
        enable_versioning = False
        if hasattr(config, "enable_versioning"):
            enable_versioning = config.enable_versioning
        elif hasattr(config, "experimental") and hasattr(config.experimental, "enable_versioning"):
            enable_versioning = config.experimental.enable_versioning

        enable_versioning = (
            getattr(config, "enable_versioning", False)
            or getattr(getattr(config, "soul", None), "enable_versioning", False)
            or getattr(getattr(config, "experimental", None), "enable_versioning", False)
        )

        logger.info(
            f"✅ SoulCryptoManager инициализирован: "
            f"hmac={'enabled' if self._hmac_key else 'disabled'}, "
            f"versioning={'enabled' if enable_versioning else 'disabled'}, "
            f"soul_dir={self.soul_dir}"
        )

    # =================================================================================
    # PUBLIC API
    # =================================================================================

    def load_file(self, filename: str) -> str:
        """Загрузка soul-файла с HMAC-проверкой.

        Args:
            filename: Имя файла (personality.txt, rules.txt, values.txt)

        Returns:
            Содержимое файла

        Raises:
            FileNotFoundError: если файл не существует
            SoulTamperError: если HMAC не совпадает (подмена)
        """
        path = self.soul_dir / filename

        if not path.exists():
            raise FileNotFoundError(f"Soul-файл не найден: {path}")

        content = path.read_text(encoding="utf-8")
        self._stats["loads"] += 1

        # HMAC проверка (если ключ задан)
        if self._hmac_key:
            self._verify_hmac(path, content)
        else:
            # Без HMAC — создаём подпись при первом чтении (для будущей защиты)
            if self.config.hmac_key:
                self._sign_file(path, content)

        logger.debug(f"Загружен soul-файл: {filename} ({len(content)} символов)")
        return content

    def load_all(self) -> dict[str, str]:
        """Загрузка всех soul-файлов.

        Returns:
            Словарь {filename_without_ext: content}
        """
        return {
            "personality": self.load_file(self.config.personality_file),
            "rules": self.load_file(self.config.rules_file),
            "values": self.load_file(self.config.values_file),
        }

    def update_file(self, filename: str, new_content: str, metadata: dict | None = None) -> None:
        """Обновление soul-файла с версионированием.

        Args:
            filename: Имя файла
            new_content: Новое содержимое
            metadata: Опциональные метаданные (причина изменения и т.д.)

        Raises:
            SoulTamperError: если текущий файл подменён (HMAC не совпадает)
        """
        path = self.soul_dir / filename

        # Сохраняем текущую версию в историю (если versioning включён)
        if self.config.enable_versioning and path.exists():
            try:
                current = self.load_all()
                version = SoulVersion(
                    timestamp=time.time(),
                    personality=current["personality"],
                    rules=current["rules"],
                    values=current["values"],
                    metadata=metadata or {"changed_file": filename},
                )
                self._history.append(version)

                # Ограничиваем размер истории
                if len(self._history) > self.config.max_history_size:
                    self._history.pop(0)

                self._save_history()
                logger.info(f"Создана версия soul (история: {len(self._history)})")
            except SoulTamperError:
                # Если текущий файл подменён — не обновляем, бросаем ошибку
                raise

        # Записываем новое содержимое
        try:
            path.write_text(new_content, encoding="utf-8")
        except OSError as e:
            logger.error(f"Не удалось записать soul-файл {path}: {e}")
            raise

        # Подписываем HMAC
        if self._hmac_key:
            self._sign_file(path, new_content)

        self._stats["updates"] += 1
        logger.info(f"Обновлён soul-файл: {filename}")

    def update_all(self, new_soul: dict[str, str], metadata: dict | None = None) -> None:
        """Обновление всех soul-файлов сразу.

        Args:
            new_soul: Словарь {key: content}, где key — 'personality', 'rules', 'values'
            metadata: Опциональные метаданные
        """
        # Сохраняем текущую версию
        if self.config.enable_versioning:
            try:
                current = self.load_all()
                version = SoulVersion(
                    timestamp=time.time(),
                    personality=current["personality"],
                    rules=current["rules"],
                    values=current["values"],
                    metadata=metadata or {"changed_files": list(new_soul.keys())},
                )
                self._history.append(version)

                if len(self._history) > self.config.max_history_size:
                    self._history.pop(0)

                self._save_history()
            except SoulTamperError:
                raise

        # Обновляем файлы
        file_mapping = {
            "personality": self.config.personality_file,
            "rules": self.config.rules_file,
            "values": self.config.values_file,
        }

        for key, content in new_soul.items():
            if key in file_mapping:
                filename = file_mapping[key]
                path = self.soul_dir / filename
                path.write_text(content, encoding="utf-8")

                if self._hmac_key:
                    self._sign_file(path, content)

        self._stats["updates"] += 1
        logger.info(f"Обновлены soul-файлы: {list(new_soul.keys())}")

    def get_history(self) -> list[SoulVersion]:
        """Получение истории изменений soul.

        Returns:
            Список версий (от старых к новым)
        """
        return self._history.copy()

    def rollback(self, version_index: int) -> None:
        """Откат к предыдущей версии soul.

        Args:
            version_index: Индекс версии в истории (0 = самая старая)

        Raises:
            SoulVersionError: если версия не существует
        """
        if not self._history:
            raise SoulVersionError("История версий пуста, некуда откатывать")

        if version_index < 0 or version_index >= len(self._history):
            raise SoulVersionError(
                f"Невалидный индекс версии: {version_index}. Доступно версий: {len(self._history)}"
            )

        version = self._history[version_index]

        # Восстанавливаем файлы
        file_mapping = {
            "personality": self.config.personality_file,
            "rules": self.config.rules_file,
            "values": self.config.values_file,
        }

        for key, filename in file_mapping.items():
            content = getattr(version, key)
            path = self.soul_dir / filename
            path.write_text(content, encoding="utf-8")

            if self._hmac_key:
                self._sign_file(path, content)

        # Удаляем версии после отката (они больше не актуальны)
        self._history = self._history[:version_index]
        self._save_history()

        self._stats["rollbacks"] += 1
        logger.info(f"Откат к версии {version_index} (timestamp={version.timestamp})")

    def get_stats(self) -> dict:
        """Получение статистики операций."""
        return {
            **self._stats,
            "history_size": len(self._history),
            "hmac_enabled": bool(self._hmac_key),
            "versioning_enabled": self.config.enable_versioning,
        }

    # =================================================================================
    # PRIVATE METHODS
    # =================================================================================

    def _compute_hmac(self, content: str) -> str:
        """Вычисление HMAC-SHA256 для содержимого."""
        return hmac.new(self._hmac_key, content.encode("utf-8"), hashlib.sha256).hexdigest()

    def _sign_file(self, path: Path, content: str) -> None:
        """Подпись файла HMAC-SHA256."""
        hmac_hex = self._compute_hmac(content)
        hmac_path = Path(f"{path}.hmac")

        try:
            hmac_path.write_text(hmac_hex, encoding="utf-8")
            logger.debug(f"Подписан файл: {path.name}")
        except OSError as e:
            logger.error(f"Не удалось записать HMAC-файл {hmac_path}: {e}")
            raise

    def _verify_hmac(self, path: Path, content: str) -> None:
        """Проверка HMAC-подписи файла.

        Raises:
            SoulTamperError: если подпись не совпадает
        """
        hmac_path = Path(f"{path}.hmac")

        if not hmac_path.exists():
            # Подписи нет — создаём при первом чтении
            logger.warning(
                f"HMAC-файл отсутствует для {path.name}. Создаю подпись при первом чтении."
            )
            self._sign_file(path, content)
            return

        try:
            stored_hmac = hmac_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            logger.error(f"Не удалось прочитать HMAC-файл {hmac_path}: {e}")
            raise

        computed_hmac = self._compute_hmac(content)

        if not hmac.compare_digest(stored_hmac, computed_hmac):
            self._stats["tamper_attempts"] += 1
            logger.error(f"🚨 ОБНАРУЖЕНА ПОДМЕНА soul-файла: {path.name}! HMAC не совпадает.")
            raise SoulTamperError(
                f"HMAC-подпись не совпадает для {path.name}. Файл мог быть подменён.",
                context={"path": str(path)},
            )

    def _load_history(self) -> None:
        """Загрузка истории версий из файла."""
        if not self._history_file.exists():
            self._history = []
            return

        try:
            data = json.loads(self._history_file.read_text(encoding="utf-8"))
            self._history = [SoulVersion.from_dict(v) for v in data]
            logger.debug(f"Загружена история soul: {len(self._history)} версий")
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning(f"Не удалось загрузить историю soul: {e}")
            self._history = []

    def _save_history(self) -> None:
        """Сохранение истории версий в файл."""
        try:
            data = [v.to_dict() for v in self._history]
            self._history_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as e:
            logger.error(f"Не удалось сохранить историю soul: {e}")
