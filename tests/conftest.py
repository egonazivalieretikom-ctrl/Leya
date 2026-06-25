"""
tests/conftest.py — Общие фикстуры для тестов Леи.
"""
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# Устанавливаем тестовое окружение ДО импорта модулей Леи
os.environ["LEYA_WEB"] = "0"  # CLI для тестов
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["LEYA_MODEL"] = "test-model"
os.environ["LOG_LEVEL"] = "WARNING"  # Минимум логов в тестах


@pytest.fixture
def temp_brain_dir():
    """Временная директория для памяти Леи (автоматически удаляется после теста)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_llm_client():
    """Мок LLM клиента для тестов."""
    async def mock_llm(prompt: str, require_json: bool = False) -> str:
        if require_json:
            # Возвращаем валидный JSON для cognitive_output
            return '{"response": "Тестовый ответ", "internal_monologue": "Тестовые мысли", "action_intent": "none", "self_reflection": ""}'
        else:
            return "Тестовый текстовый ответ"
    
    return mock_llm


@pytest.fixture
def mock_llm_with_facts():
    """Мок LLM клиента, возвращающий факты для консолидации."""
    async def mock_llm(prompt: str, require_json: bool = False) -> str:
        if "извлеки ключевые факты" in prompt.lower():
            return '{"facts": ["Факт 1 о тестировании", "Факт 2 о памяти"]}'
        elif "извлеки 3-5 новых" in prompt.lower():
            return '{"terms": ["термин1", "термин2"]}'
        elif require_json:
            return '{"response": "Ответ", "internal_monologue": "Мысли", "action_intent": "none", "self_reflection": ""}'
        else:
            return "Текстовый ответ"
    
    return mock_llm


@pytest.fixture
def mock_leya_os(temp_brain_dir, mock_llm_client):
    """Мок LeyaOS для тестов MetaCognition."""
    from leya_core.drives import DriveSystem
    from leya_core.memory import MemorySystem
    
    leya_os = MagicMock()
    leya_os.drives = DriveSystem()
    leya_os.memory = MemorySystem(persist_directory=temp_brain_dir)
    
    return leya_os