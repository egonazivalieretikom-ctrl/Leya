"""
LeyaOS — Core package.

Bootstrap: установка переменных окружения ДО импорта chromadb и других модулей.
"""

import os

# Отключение телеметрии ChromaDB
os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["CHROMA_TELEMETRY_DISABLE"] = "true"

# Отключение телеметрии sentence-transformers/HuggingFace
os.environ["SENTENCE_TRANSFORMERS_HOME"] = os.environ.get(
    "SENTENCE_TRANSFORMERS_HOME", "./.cache/sentence_transformers"
)
