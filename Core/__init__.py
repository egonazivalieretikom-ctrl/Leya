# Core/__init__.py
# Минимальный __init__ чтобы избежать circular imports

from .state import LeyaState
from .event_bus import EventBus, event_bus
from .logger import setup_logging

__all__ = ["LeyaState", "EventBus", "event_bus", "setup_logging"]