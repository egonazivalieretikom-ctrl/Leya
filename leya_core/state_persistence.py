"""
leya_core/state_persistence.py
Сохранение и загрузка состояния Леи между сессиями.

Этап 1.2:
- Замена широких except на специфичные исключения
- Атомарная запись с резервной копией
"""

from __future__ import annotations

import contextlib 
import json
import logging
import hashlib
import hmac
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exceptions import ( 
    LeyaConfigError,
    LeyaPersistenceError,
    LeyaStateCorruptedError,
    LeyaStateVersionMismatchError,  
)

logger = logging.getLogger(__name__)



class StatePersistence:
    def __init__(self, state_file: str | None = None, brain_dir: str = "./leya_brain") -> None:
        if state_file is None:
            state_file = str(Path(brain_dir) / "leya_state.json")
        self.state_file = state_file
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Создание директории для файла состояния, если она не существует.
    
        Raises:
            LeyaPersistenceError: если не удалось создать директорию
        """
        directory = os.path.dirname(self.state_file)
        if directory:
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as exc:
                raise LeyaPersistenceError(
                    f"Не удалось создать директорию: {directory}",
                    context={"path": directory, "error": str(exc)},
                ) from exc

    def _get_hmac_key(self) -> bytes:
        key = os.environ.get("LEYA_STATE_HMAC_KEY")
        if not key or len(key.strip()) < 32:
            raise LeyaConfigError("LEYA_STATE_HMAC_KEY не установлен или слишком короткий")
        return key.encode("utf-8")
    
    def _compute_hmac(self, path: Path, key: bytes) -> str:
        h = hmac.new(key, digestmod=hashlib.sha256)
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    
    def save_state(self, state: dict[str, Any]) -> bool:
        try:
            state["_saved_at"] = datetime.now(timezone.utc).isoformat()
            state["__version__"] = 1  # ← Добавляем версию

            # Резервная копия
            if os.path.exists(self.state_file):
                backup_path = self.state_file + ".backup"
                try:
                    os.replace(self.state_file, backup_path)
                except OSError as exc:
                    logger.warning(f"Не удалось создать резервную копию: {exc}")

            # Запись во временный файл
            tmp_path = self.state_file + ".tmp"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)

                # HMAC подпись
                key = self._get_hmac_key()
                signature = self._compute_hmac(Path(tmp_path), key)
                (Path(self.state_file).with_suffix(".hmac")).write_text(signature, encoding="utf-8")

                os.replace(tmp_path, self.state_file)
            except OSError as exc:
                if os.path.exists(tmp_path):
                    with contextlib.suppress(OSError):
                        os.remove(tmp_path)
                raise LeyaPersistenceError(
                    f"Не удалось сохранить состояние: {exc}",
                    context={"path": self.state_file, "error": str(exc)},
                ) from exc

            return True

        except LeyaPersistenceError:
            raise
        except Exception as exc:
            raise LeyaPersistenceError(
                f"Неожиданная ошибка при сохранении состояния: {exc}",
                context={"path": self.state_file, "error": str(exc)},
            ) from exc
    
    def load_state(self) -> dict[str, Any]:
        if not os.path.exists(self.state_file):
            backup_path = self.state_file + ".backup"
            if os.path.exists(backup_path):
                logger.info("Основной файл не найден, загружаем из резервной копии")
                self.state_file = backup_path
            else:
                logger.info("Файл состояния не найден, начинаем с чистого листа")
                return {}

        try:
            # Проверка HMAC
            hmac_path = Path(self.state_file).with_suffix(".hmac")
            if hmac_path.exists():
                key = self._get_hmac_key()
                expected = hmac_path.read_text(encoding="utf-8").strip()
                actual = self._compute_hmac(Path(self.state_file), key)
                if not hmac.compare_digest(expected, actual):
                    raise LeyaStateCorruptedError("HMAC не совпадает")
            else:
                logger.warning("HMAC-файл отсутствует, пропускаем проверку")

            with open(self.state_file, encoding="utf-8") as f:
                state = json.load(f)

            # Проверка версии
            version = state.get("__version__", 0)
            if version != 1:
                raise LeyaStateVersionMismatchError(f"Несовместимая версия: {version}")

            return state

        except json.JSONDecodeError as exc:
            raise LeyaStateCorruptedError(
                f"Не удалось распарсить JSON состояния: {exc}",
                context={"path": self.state_file, "error": str(exc)},
            ) from exc
        except LeyaPersistenceError:
            raise
        except Exception as exc:
            raise LeyaPersistenceError(
                f"Неожиданная ошибка при загрузке состояния: {exc}",
                context={"path": self.state_file, "error": str(exc)},
            ) from exc