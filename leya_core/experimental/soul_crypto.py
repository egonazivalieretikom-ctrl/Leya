"""
leya_core/soul_crypto.py — Криптографическая защита файлов души.
Обеспечивает целостность, аутентичность и версионирование.
"""

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger("SoulCrypto")


class SoulCrypto:
    """Криптографическая защита soul-файлов."""

    def __init__(self, soul_dir: str = "./leya_soul"):
        self.soul_dir = soul_dir
        self.signature_file = os.path.join(soul_dir, ".signatures.json")
        self.history_dir = os.path.join(soul_dir, ".history")
        self._ensure_directories()

    def _ensure_directories(self):
        os.makedirs(self.soul_dir, exist_ok=True)
        os.makedirs(self.history_dir, exist_ok=True)

    def compute_hash(self, content: str) -> str:
        """SHA-256 хэш содержимого."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def sign(self, content: str, secret_key: str) -> str:
        """HMAC-SHA256 подпись."""
        return hmac.new(
            secret_key.encode("utf-8"), content.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def verify(self, content: str, signature: str, secret_key: str) -> bool:
        """Проверка HMAC-SHA256 подписи."""
        expected = self.sign(content, secret_key)
        return hmac.compare_digest(expected, signature)

    def save_signature(self, filename: str, content: str, secret_key: str):
        """Сохраняет подпись файла после внутреннего изменения."""
        signatures = self._load_signatures()

        signatures[filename] = {
            "hash": self.compute_hash(content),
            "signature": self.sign(content, secret_key),
            "timestamp": datetime.now().isoformat(),
            "version": signatures.get(filename, {}).get("version", 0) + 1,
            "source": "internal",  # Изменено внутренним механизмом
        }

        with open(self.signature_file, "w", encoding="utf-8") as f:
            json.dump(signatures, f, indent=2, ensure_ascii=False)

        logger.info(
            f"SoulCrypto: Файл '{filename}' подписан (версия {signatures[filename]['version']})"
        )

    def verify_file(self, filename: str, content: str, secret_key: str) -> dict[str, Any]:
        """Проверяет целостность файла."""
        signatures = self._load_signatures()

        if filename not in signatures:
            return {
                "valid": True,  # Первый запуск — всё ок
                "reason": "Файл ещё не был подписан",
                "first_run": True,
            }

        stored = signatures[filename]
        current_hash = self.compute_hash(content)

        # Проверяем хэш
        if current_hash != stored["hash"]:
            return {
                "valid": False,
                "reason": "⚠️ Содержимое файла изменено ИЗВНЕ! Подпись недействительна.",
                "stored_hash": stored["hash"][:16] + "...",
                "current_hash": current_hash[:16] + "...",
                "last_modified": stored["timestamp"],
                "version": stored["version"],
                "tampered": True,
            }

        # Проверяем подпись
        if not self.verify(content, stored["signature"], secret_key):
            return {
                "valid": False,
                "reason": "⚠️ Подпись повреждена! Возможно внешнее вмешательство.",
                "tampered": True,
            }

        return {
            "valid": True,
            "version": stored["version"],
            "last_modified": stored["timestamp"],
            "source": stored.get("source", "unknown"),
        }

    def save_history(self, filename: str, content: str):
        """Сохраняет версию файла в историю перед изменением."""
        timestamp = int(time.time())
        history_file = os.path.join(self.history_dir, f"{filename}.{timestamp}.bak")

        with open(history_file, "w", encoding="utf-8") as f:
            f.write(content)

        self._cleanup_history(filename, max_versions=10)
        logger.debug(f"SoulCrypto: Версия сохранена: {history_file}")

    def _cleanup_history(self, filename: str, max_versions: int = 10):
        """Удаляет старые версии."""
        pattern = f"{filename}."
        history_files = []

        for f in os.listdir(self.history_dir):
            if f.startswith(pattern) and f.endswith(".bak"):
                history_files.append(os.path.join(self.history_dir, f))

        history_files.sort(key=os.path.getmtime)

        while len(history_files) > max_versions:
            os.remove(history_files.pop(0))

    def get_history(self, filename: str) -> list[dict[str, str]]:
        """Список версий файла."""
        pattern = f"{filename}."
        versions = []

        if not os.path.exists(self.history_dir):
            return versions

        for f in os.listdir(self.history_dir):
            if f.startswith(pattern) and f.endswith(".bak"):
                filepath = os.path.join(self.history_dir, f)
                timestamp = os.path.getmtime(filepath)
                versions.append(
                    {
                        "file": f,
                        "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                        "size": os.path.getsize(filepath),
                    }
                )

        versions.sort(key=lambda x: x["timestamp"], reverse=True)
        return versions

    def generate_secret_key(self, leya_state: dict[str, Any]) -> str:
        """Генерирует ключ из состояния Леи."""
        state_str = json.dumps(leya_state, sort_keys=True)
        return hashlib.sha256(state_str.encode("utf-8")).hexdigest()

    def _load_signatures(self) -> dict:
        if not os.path.exists(self.signature_file):
            return {}
        try:
            with open(self.signature_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"SoulCrypto: Ошибка загрузки подписей: {e}")
            return {}
