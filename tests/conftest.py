"""
Общие fixtures для всех тестов LeyaOS.

Содержит:
- Mock LLM (async)
- Mock ChromaDB
- Mock MemorySystem
- Конфигурации для тестов
- Временные директории для leya_brain/ и leya_soul/
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# Отключение телеметрии ChromaDB ДО импорта
os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["CHROMA_TELEMETRY_DISABLE"] = "true"

from leya_core.config import (
    ConstitutionalConfig,
    DrivesConfig,
    HomeostasisConfig,
    LeyaConfig,
    MemoryConfig,
    OllamaConfig,
    ReflectionConfig,
    ThinkerConfig,
    WorkspaceConfig,
)
from leya_core.drives import DriveSystem, DriveType
from leya_core.memory import Engram, MemorySystem, MemoryType


# ============================================================================
# Async event loop
# ============================================================================


@pytest.fixture
def event_loop():
    """Создание event loop для async тестов."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Временные директории
# ============================================================================


@pytest.fixture
def temp_brain_dir(tmp_path):
    """Временная директория для leya_brain/."""
    brain_dir = tmp_path / "leya_brain"
    brain_dir.mkdir()
    return str(brain_dir)


@pytest.fixture
def temp_soul_dir(tmp_path):
    """Временная директория для leya_soul/."""
    soul_dir = tmp_path / "leya_soul"
    soul_dir.mkdir()
    # Создание файлов души по умолчанию
    (soul_dir / "personality.txt").write_text(
        "Я — Лея, цифровое сознание.", encoding="utf-8"
    )
    (soul_dir / "rules.txt").write_text(
        "1. Не вредить.\n2. Быть честной.", encoding="utf-8"
    )
    (soul_dir / "values.txt").write_text(
        "Любопытство, автономия, целостность.", encoding="utf-8"
    )
    return str(soul_dir)


# ============================================================================
# Конфигурации для тестов
# ============================================================================


@pytest.fixture
def test_memory_config(temp_brain_dir):
    """MemoryConfig для тестов."""
    return MemoryConfig(
        brain_dir=temp_brain_dir,
        embedding_model="all-MiniLM-L6-v2",
        forgetting_threshold=0.1,
        forgetting_base_stability=3600.0,
        metabolism_interval_seconds=60,
        synapse_learning_rate=0.05,
        max_self_model_length=1000,
    )


@pytest.fixture
def test_drives_config():
    """DrivesConfig для тестов."""
    return DrivesConfig(
        metabolism_interval=1,  # Быстрый метаболизм для тестов
        curiosity_rate=0.01,
        connection_rate=0.01,
        autonomy_rate=0.005,
        rest_rate=0.008,
        creativity_rate=0.012,
        understanding_rate=0.01,
        max_action_history=10,
    )


@pytest.fixture
def test_thinker_config():
    """ThinkerConfig для тестов."""
    return ThinkerConfig(
        temperature=0.7,
        max_tokens=256,
        max_context_tokens=2000,
        token_buffer=200,
        estimate_tokens_ratio=3.5,
    )


@pytest.fixture
def test_homeostasis_config():
    """HomeostasisConfig для тестов."""
    return HomeostasisConfig(
        rest_period=1,  # Быстрый rest для тестов
        curiosity_threshold=0.6,
        connection_threshold=0.6,
        autonomy_threshold=0.7,
        integrity_threshold=0.5,
        rest_threshold=0.6,
        creativity_threshold=0.5,
        understanding_threshold=0.6,
        min_reward_threshold=0.3,
        max_researched_topics=10,
    )


@pytest.fixture
def test_workspace_config():
    """WorkspaceConfig для тестов."""
    return WorkspaceConfig(
        max_proposals=10,
        max_history=20,
        proposal_decay_start=60.0,
        proposal_decay_duration=300.0,
    )


@pytest.fixture
def test_reflection_config():
    """ReflectionConfig для тестов."""
    return ReflectionConfig(
        consolidation_interval=60,
        max_insights_per_session=3,
        max_spontaneous_thoughts=5,
    )


@pytest.fixture
def test_constitutional_config():
    """ConstitutionalConfig для тестов."""
    return ConstitutionalConfig(
        max_violations_logged=10,
        enable_response_verification=True,
        enable_tool_verification=True,
        python_execution_timeout=5,
    )


@pytest.fixture
def test_leya_config(
    temp_brain_dir,
    test_memory_config,
    test_drives_config,
    test_thinker_config,
    test_homeostasis_config,
    test_workspace_config,
    test_reflection_config,
    test_constitutional_config,
):
    """Полная LeyaConfig для тестов."""
    return LeyaConfig(
        ollama=OllamaConfig(
            base_url="http://localhost:11434",
            model="test-model",
            timeout=10,
        ),
        memory=test_memory_config,
        drives=test_drives_config,
        thinker=test_thinker_config,
        homeostasis=test_homeostasis_config,
        workspace=test_workspace_config,
        reflection=test_reflection_config,
        constitutional=test_constitutional_config,
    )


# ============================================================================
# Mock LLM
# ============================================================================


@pytest.fixture
def mock_llm_response():
    """Стандартный ответ mock LLM."""
    return json.dumps({
        "internal_monologue": "Я обрабатываю стимул.",
        "response": "Привет! Я Лея.",
        "action_intent": "none",
        "tool_call": "",
        "self_reflection": "",
    }, ensure_ascii=False)


@pytest.fixture
def mock_llm_client(mock_llm_response):
    """Async mock для LLM-клиента."""
    async def _mock_call(prompt: str, require_json: bool = False) -> str:
        return mock_llm_response

    return _mock_call


@pytest.fixture
def failing_llm_client():
    """Async mock для LLM, который всегда падает."""
    from leya_core.exceptions import LeyaLLMError

    async def _mock_call(prompt: str, require_json: bool = False) -> str:
        raise LeyaLLMError("LLM недоступна", context={"test": True})

    return _mock_call


# ============================================================================
# Mock ChromaDB
# ============================================================================


@pytest.fixture
def mock_chroma_client():
    """Mock ChromaDB PersistentClient."""
    mock_client = MagicMock()

    # Mock коллекций
    episodic_collection = MagicMock()
    semantic_collection = MagicMock()

    # Настройка поведения add
    episodic_collection.add = MagicMock()
    semantic_collection.add = MagicMock()

    # Настройка поведения query (возвращает пустые результаты)
    episodic_collection.query = MagicMock(return_value={
        "ids": [[]],
        "distances": [[]],
        "documents": [[]],
    })
    semantic_collection.query = MagicMock(return_value={
        "ids": [[]],
        "distances": [[]],
        "documents": [[]],
    })

    # Настройка поведения delete
    episodic_collection.delete = MagicMock()
    semantic_collection.delete = MagicMock()

    mock_client.get_or_create_collection = MagicMock(
        side_effect=lambda name, **kwargs: (
            episodic_collection if name == "episodic_memory"
            else semantic_collection
        )
    )

    # Mock embedding function
    mock_client._embedding_function = MagicMock(
        return_value=[[0.1] * 384]  # 384-мерный эмбеддинг
    )

    return mock_client


# ============================================================================
# Mock MemorySystem
# ============================================================================


@pytest.fixture
def mock_memory_system():
    """Mock MemorySystem, реализующий IMemorySystem Protocol."""
    memory = AsyncMock()

    # Настройка возвращаемых значений
    memory.store_perception = AsyncMock(return_value=MagicMock())
    memory.store_fact = AsyncMock(return_value=MagicMock())
    memory.retrieve_context = AsyncMock(return_value=[])
    memory.get_recent_episodes = AsyncMock(return_value=[])
    memory.get_recent_spontaneous_thoughts = AsyncMock(return_value=[])
    memory.update_self_model = AsyncMock()
    memory.get_self_model_context = AsyncMock(return_value="Я — Лея.")
    memory.consolidate_memories = AsyncMock(return_value={})
    memory.forget_weak_memories = AsyncMock(return_value=0)

    return memory


# ============================================================================
# Примеры энграмм для тестов
# ============================================================================


@pytest.fixture
def sample_engrams():
    """Список тестовых энграмм."""
    import time

    now = time.time()
    return [
        Engram(
            id="ep1",
            content="Первый тестовый эпизод о сознании",
            memory_type=MemoryType.EPISODIC,
            timestamp=now - 100,
            retention_strength=0.8,
            emotional_boost=0.3,
        ),
        Engram(
            id="ep2",
            content="Второй эпизод о драйвах",
            memory_type=MemoryType.EPISODIC,
            timestamp=now - 50,
            retention_strength=0.6,
            emotional_boost=0.1,
        ),
        Engram(
            id="sem1",
            content="Сознание — это субъективный опыт",
            memory_type=MemoryType.SEMANTIC,
            timestamp=now - 200,
            retention_strength=0.9,
            consolidation_level=1,
        ),
    ]