import logging
import sys
import platform
from pathlib import Path

import structlog
from rich.console import Console
from rich.logging import RichHandler

# 🎨 ИНИЦИАЛИЗАЦИЯ ЦВЕТОВ ДЛЯ WINDOWS
# Colorama "переводит" ANSI цвета в Win32 API, чтобы они работали в cmd/PowerShell
if platform.system() == "Windows":
    try:
        import colorama
        colorama.init()
    except ImportError:
        print("⚠️ Warning: colorama not found. Colors might not work correctly on Windows.")

# Создаем консоль для красивого вывода
console = Console()

def setup_logger(log_level: str = "INFO") -> structlog.BoundLogger:
    """
    Настраивает структурированное логирование с использованием Rich.
    """
    # Настраиваем стандартный logging для библиотек
    logging.basicConfig(
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, tracebacks_show_locals=True)],
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    # Настраиваем structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(colors=True, sort_keys=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()

# Глобальный логгер, который можно импортировать в любой файл
log = setup_logger()

# Пример использования (можно удалить после теста):
if __name__ == "__main__":
    log.info("🟢 Leya OS Logger initialized")
    log.warning("⚠️ Calibration required", module="Vision")
    log.error("❌ Connection lost", target="Memory_DB")