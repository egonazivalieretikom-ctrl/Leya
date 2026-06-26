# leya_core/__init__.py
"""
LeyaOS — Core package.

Bootstrap: установка переменных окружения ДО импорта chromadb и других модулей.
Это гарантирует, что телеметрия отключена до загрузки любых зависимостей.
"""

import os

# Отключение телеметрии ChromaDB
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("CHROMA_TELEMETRY_DISABLE", "true")

# Отключение телеметрии sentence-transformers/HuggingFace
os.environ.setdefault(
    "SENTENCE_TRANSFORMERS_HOME",
    os.path.join(os.path.dirname(__file__), "..", ".cache", "sentence_transformers"),
)
