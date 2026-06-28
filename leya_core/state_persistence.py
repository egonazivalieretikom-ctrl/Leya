"""
leya_core/state_persistence.py
Сохранение и загрузка состояния Леи между сессиями.

Этап 1.2:
- Замена широких except на специфичные исключения
- Атомарная запись с резервной копией
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .exceptions import LeyaPersistenceError, LeyaStateCorruptedError

logger = logging.getLogger(__name__)


class StatePersistence:
    """Сохраняет и загружает состояние Леи из JSON файла."""

    def __init__(self, state_file: str | None = None, brain_dir: str = "./leya_brain") -> None:
        if state_file is None:
            state_file = str(Path(brain_dir) / "leya_state.json")
        self.state_file = state_file
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Создание директории для файла состояния."""
        directory = os.path.dirname(self.state_file)
        if directory:
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as exc:
                raise LeyaPersistenceError(
                    f"Не удалось создать директорию: {directory}",
                    context={"path": directory, "error": str(exc)},
                ) from exc

    def save_state(self, state: dict[str, Any]) -> bool:
        """Сохранение состояния в JSON файл с атомарной записью."""
        try:
            state["_saved_at"] = datetime.now().isoformat()

            # Резервная копия предыдущего состояния
            if os.path.exists(self.state_file):
                backup_path = self.state_file + ".backup"
                try:
                    os.replace(self.state_file, backup_path)
                except OSError as exc:
                    logger.warning(f"Не удалось создать резервную копию: {exc}")

            # Запись во временный файл + атомарная замена
            tmp_path = self.state_file + ".tmp"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)

                os.replace(tmp_path, self.state_file)
            except OSError as exc:
                # Очистка tmp на случай ошибки
                import contextlib

                if os.path.exists(tmp_path):
                    with contextlib.suppress(OSError):
                        os.remove(tmp_path)
                raise LeyaPersistenceError(
                    "Не удалось сохранить состояние",
                    context={"path": self.state_file, "error": str(exc)},
                ) from exc

            logger.info(
                f"StatePersistence: Состояние сохранено ({os.path.getsize(self.state_file)} байт)"
            )
            return True

        except LeyaPersistenceError:
            raise
        except Exception as exc:
            raise LeyaPersistenceError(
                "Неожиданная ошибка сохранения состояния",
                context={"path": self.state_file, "error": str(exc)},
            ) from exc

    def load_state(self) -> dict[str, Any]:
        """Загрузка состояния из JSON файла."""
        if not os.path.exists(self.state_file):
            # Попытка загрузить из резервной копии
            backup_path = self.state_file + ".backup"
            if os.path.exists(backup_path):
                logger.info(
                    "StatePersistence: Основной файл не найден, загружаем из резервной копии"
                )
                self.state_file = backup_path
            else:
                logger.info("StatePersistence: Файл состояния не найден, начинаем с чистого листа")
                return {}

        try:
            with open(self.state_file, encoding="utf-8") as f:
                state = json.load(f)

            saved_at = state.get("_saved_at", "неизвестно")
            logger.info(f"StatePersistence: Состояние загружено (сохранено: {saved_at})")
            return state

        except json.JSONDecodeError as exc:
            raise LeyaStateCorruptedError(
                "Файл состояния повреждён (невалидный JSON)",
                context={"path": self.state_file, "error": str(exc)},
            ) from exc
        except OSError as exc:
            raise LeyaPersistenceError(
                "Не удалось прочитать файл состояния",
                context={"path": self.state_file, "error": str(exc)},
            ) from exc
        except Exception as exc:
            raise LeyaPersistenceError(
                "Неожиданная ошибка загрузки состояния",
                context={"path": self.state_file, "error": str(exc)},
            ) from exc
