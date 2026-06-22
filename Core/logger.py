import logging
import structlog
from structlog import configure, processors, stdlib, get_logger

def setup_logging():
    configure(
        processors=[
            stdlib.filter_by_level,
            stdlib.add_logger_name,
            stdlib.add_log_level,
            stdlib.PositionalArgumentsFormatter(),
            processors.TimeStamper(fmt="iso"),
            processors.StackInfoRenderer(),
            processors.format_exc_info,
            processors.UnicodeDecoder(),
            processors.JSONRenderer() if False else processors.ConsoleRenderer(colors=True),
        ],
        context_class=dict,
        logger_factory=stdlib.LoggerFactory(),
        wrapper_class=stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logger = get_logger("leya")
    logger.info("📋 Structured logging initialized")
    return logger