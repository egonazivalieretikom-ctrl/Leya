"""
leya_core/exceptions.py
Иерархия исключений LeyaOS.

Заменяет широкие `except Exception:` на специфичные классы.
Все исключения наследуются от LeyaError для возможности
глобального перехвата в фоновых задачах.
"""
from __future__ import annotations


class LeyaError(Exception):
    """Базовое исключение для всех ошибок LeyaOS."""

    def __init__(self, message: str, *, context: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        base = self.message
        if self.context:
            ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{base} [{ctx}]"
        return base


# --- Persistence ---
class LeyaPersistenceError(LeyaError):
    """Базовое исключение для ошибок персистентности."""


class LeyaStateCorruptedError(LeyaPersistenceError):
    """Файл состояния повреждён или не прошёл проверку HMAC."""


class LeyaStateVersionMismatchError(LeyaPersistenceError):
    """Версия формата состояния несовместима с текущей."""


class LeyaAtomicWriteError(LeyaPersistenceError):
    """Ошибка атомарной записи (не удалось заменить tmp-файл)."""


# --- Memory ---
class LeyaMemoryError(LeyaError):
    """Базовое исключение для ошибок памяти (ChromaDB, engrams, synapses)."""


class LeyaEmbeddingError(LeyaMemoryError):
    """Не удалось получить эмбеддинг (сбой sentence-transformers / to_thread)."""


class LeyaEngramNotFoundError(LeyaMemoryError):
    """Энграмма с указанным id отсутствует."""


# --- LLM / Thinker ---
class LeyaLLMError(LeyaError):
    """Базовое исключение для ошибок взаимодействия с LLM."""


class LeyaLLMTimeoutError(LeyaLLMError):
    """Таймаут при обращении к Ollama."""


class LeyaLLMUnavailableError(LeyaLLMError):
    """Ollama недоступна (circuit breaker open)."""


class LeyaJSONParseError(LeyaLLMError):
    """Ответ LLM не удалось распарсить в CognitiveOutput."""


# --- Drives / Homeostasis ---
class LeyaHomeostasisError(LeyaError):
    """Ошибка в гомеостазе или системе драйвов."""


class LeyaDriveNotFoundError(LeyaHomeostasisError):
    """Запрошен несуществующий драйв."""


# --- Environment / Web ---
class LeyaEnvironmentError(LeyaError):
    """Ошибка окружения (Web / CLI / Voice)."""


class LeyaBroadcastError(LeyaEnvironmentError):
    """Ошибка рассылки WebSocket-сообщения."""


# --- Config ---
class LeyaConfigError(LeyaError):
    """Ошибка конфигурации (невалидные значения .env)."""

# --- Circuit Breaker ---
class LeyaCircuitBreakerError(LeyaError):
    """Ошибка Circuit Breaker (не связано с LLM напрямую)."""


# --- Reflection / MetaCognition ---
class LeyaReflectionError(LeyaError):
    """Ошибка в мета-когниции (reflection, spontaneous thoughts)."""


class LeyaInsightError(LeyaReflectionError):
    """Ошибка генерации инсайта или экзистенциального вопроса."""


# --- Tools ---
class LeyaToolError(LeyaError):
    """Ошибка выполнения инструмента."""


class LeyaToolNotFoundError(LeyaToolError):
    """Инструмент не найден в реестре."""


class LeyaToolExecutionError(LeyaToolError):
    """Ошибка выполнения инструмента (runtime)."""


# --- Workspace ---
class LeyaWorkspaceError(LeyaError):
    """Ошибка в Global Workspace."""


# --- Soul / Personality ---
class LeyaSoulError(LeyaError):
    """Ошибка загрузки или обновления души (personality, rules, values)."""