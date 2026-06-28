import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SoulManager:
    """
    Менеджер soul-файлов (personality, rules, values).
    Загружает текстовые файлы из leya_soul/ директории.
    """

    def __init__(self, soul_dir: str | Path, hmac_key: str | None = None):
        self.soul_dir = Path(soul_dir)
        self.hmac_key = hmac_key
        self._cache: dict[str, str] = {}

        if not self.soul_dir.exists():
            logger.warning(f"Soul directory не существует: {self.soul_dir}")
            self.soul_dir.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> str:
        """
        Загружает все soul-файлы и возвращает объединённый текст.

        Returns:
            Объединённый текст из personality.txt, rules.txt, values.txt
        """
        soul_files = ["personality.txt", "rules.txt", "values.txt"]
        combined = []

        for filename in soul_files:
            filepath = self.soul_dir / filename
            if filepath.exists():
                try:
                    content = filepath.read_text(encoding="utf-8")
                    combined.append(f"=== {filename.upper()} ===\n{content}\n")
                    self._cache[filename] = content
                    logger.debug(f"Soul file загружен: {filename} ({len(content)} символов)")
                except Exception as exc:
                    logger.error(f"Ошибка загрузки {filename}: {exc}")
            else:
                logger.debug(f"Soul file не найден: {filename}")

        if not combined:
            logger.warning("Soul files не найдены. Лея будет использовать только базовую личность.")
            return ""

        result = "\n".join(combined)
        logger.info(f"Soul загружен: {len(result)} символов из {len(combined)} файлов")
        return result

    def get_file(self, filename: str) -> str | None:
        """Получить содержимое конкретного soul-файла."""
        if filename in self._cache:
            return self._cache[filename]

        filepath = self.soul_dir / filename
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8")
                self._cache[filename] = content
                return content
            except Exception as exc:
                logger.error(f"Ошибка чтения {filename}: {exc}")

        return None

    def list_files(self) -> list[str]:
        """Список доступных soul-файлов."""
        if not self.soul_dir.exists():
            return []
        return [f.name for f in self.soul_dir.iterdir() if f.is_file()]
