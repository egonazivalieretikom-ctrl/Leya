# Расположение: leya_core/state_persistence.py
# Заменить методы _save_state и _load_state полностью.

import hashlib
import hmac
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any

from .exceptions import (
    LeyaAtomicWriteError,
    LeyaPersistenceError,
    LeyaStateCorruptedError,
    LeyaStateVersionMismatchError,
)

# Текущая версия формата состояния.
# Инкрементировать при несовместимых изменениях структуры payload.
STATE_FORMAT_VERSION: int = 2

# Ключ HMAC. В production должен браться из .env (LEYA_STATE_HMAC_KEY).
# Здесь — fallback для разработки. НЕ ХРАНИТЬ В РЕПОЗИТОРИИ В ПРОДАКШЕНЕ.
_DEFAULT_HMAC_KEY_ENV: str = "LEYA_STATE_HMAC_KEY"
_FALLBACK_HMAC_KEY: bytes = b"leya-dev-key-change-me-in-production"


def _get_hmac_key() -> bytes:
    key = os.environ.get(_DEFAULT_HMAC_KEY_ENV)
    if key:
        return key.encode("utf-8")
    return _FALLBACK_HMAC_KEY


def _compute_hmac(path: Path, key: bytes) -> str:
    h = hmac.new(key, digestmod=hashlib.sha256)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _save_state(self, payload: dict[str, Any]) -> None:
    """
    Атомарная запись состояния с HMAC-подписью и версионированием.

    Алгоритм:
    1. Обернуть payload в {'__version__': N, 'data': payload}.
    2. Сериализовать pickle во временный файл в той же директории.
    3. Вычислить HMAC-SHA256 от tmp-файла, записать в <file>.hmac.
    4. os.replace(tmp → target) — атомарно на POSIX.
    """
    state_path = Path(self.state_path).expanduser().resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    versioned_payload = {
        "__version__": STATE_FORMAT_VERSION,
        "data": payload,
    }

    # Временный файл в той же ФС, чтобы os.replace был атомарным
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=state_path.name + ".",
        suffix=".tmp",
        dir=str(state_path.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(versioned_payload, f, protocol=pickle.HIGHEST_PROTOCOL)

        # Подпись
        key = _get_hmac_key()
        signature = _compute_hmac(tmp_path, key)
        hmac_path = state_path.with_suffix(state_path.suffix + ".hmac")
        hmac_path.write_text(signature, encoding="utf-8")

        # Атомарная замена
        try:
            os.replace(tmp_path, state_path)
        except OSError as exc:
            raise LeyaAtomicWriteError(
                "Не удалось атомарно заменить state-файл",
                context={"target": str(state_path), "error": str(exc)},
            ) from exc
    except LeyaPersistenceError:
        # Пробрасываем наши исключения
        raise
    except Exception as exc:
        raise LeyaPersistenceError(
            "Сбой при сохранении состояния",
            context={"path": str(state_path), "error": str(exc)},
        ) from exc
    finally:
        # Очистка tmp на случай ошибки до os.replace
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _load_state(self) -> dict[str, Any] | None:
    """
    Загрузка состояния с проверкой HMAC и версии.

    Возвращает:
    - dict с данными (ключ 'data' распакован) — при успехе.
    - None — если файл отсутствует.

    Бросает:
    - LeyaStateCorruptedError — не совпадает HMAC или повреждён pickle.
    - LeyaStateVersionMismatchError — несовместимая версия.
    """
    state_path = Path(self.state_path).expanduser().resolve()
    if not state_path.exists():
        return None

    hmac_path = state_path.with_suffix(state_path.suffix + ".hmac")
    key = _get_hmac_key()

    # Проверка HMAC
    if hmac_path.exists():
        expected = hmac_path.read_text(encoding="utf-8").strip()
        actual = _compute_hmac(state_path, key)
        if not hmac.compare_digest(expected, actual):
            raise LeyaStateCorruptedError(
                "HMAC-подпись state-файла не совпадает",
                context={"path": str(state_path)},
            )
    else:
        # Файл без подписи — считаем недоверенным (кроме первого запуска)
        raise LeyaStateCorruptedError(
            "Отсутствует HMAC-подпись для state-файла",
            context={"path": str(state_path)},
        )

    # Десериализация
    try:
        with state_path.open("rb") as f:
            raw = pickle.load(f)
    except (pickle.PickleError, EOFError, ValueError) as exc:
        raise LeyaStateCorruptedError(
            "Не удалось десериализовать state-файл",
            context={"path": str(state_path), "error": str(exc)},
        ) from exc

    # Проверка версии
    if not isinstance(raw, dict) or "__version__" not in raw:
        raise LeyaStateVersionMismatchError(
            "State-файл не содержит маркер версии (вероятно, старый формат)",
            context={"path": str(state_path)},
        )

    file_version = raw["__version__"]
    if file_version != STATE_FORMAT_VERSION:
        raise LeyaStateVersionMismatchError(
            "Несовместимая версия state-файла",
            context={
                "path": str(state_path),
                "file_version": file_version,
                "expected_version": STATE_FORMAT_VERSION,
            },
        )

    return raw.get("data")