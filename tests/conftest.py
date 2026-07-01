"""
Общие fixtures для всех тестов LeyaOS.

Содержит:
- Mock LLM (совместимый с LLMBackend Protocol)
- Mock ChromaDB
- Mock MemorySystem
- Конфигурации для тестов
- Временные директории для leya_brain/ и leya_soul/
- FakeLLMBackend (из tests.fake_backend)

Этап 3.1: Полная переработка для совместимости с LLMBackend (Шаг 2.3)
и FakeLLMBackend (Шаг 2.4).
"""
from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

# Отключение телеметрии ChromaDB ДО импорта модулей
os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["CHROMA_TELEMETRY_DISABLE"] = "true"

from leya_core.config import (
    ConstitutionalConfig,
    DrivesConfig,
    ExperimentalConfig,
    HomeostasisConfig,
    LeyaConfig,
    LoggingConfig,
    MemoryConfig,
    OllamaConfig,
    ReflectionConfig,
    SoulConfig,
    ThinkerConfig,
    WebConfig,
    WorkspaceConfig,
)
from leya_core.memory import Engram, MemoryType


# =========================================================================
# Async event loop
# =========================================================================
@pytest.fixture
def event_loop():
    """Создание event loop для async тестов."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =========================================================================
# Временные директории
# =========================================================================
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


# =========================================================================
# Конфигурации для тестов
# =========================================================================
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
def test_leya_config(tmp_path):
    """Полная LeyaConfig для тестов."""
    return LeyaConfig(
        ollama=OllamaConfig(
            base_url="http://localhost:11434",
            model="test-model",
            timeout=10,
        ),
        memory=MemoryConfig(
            brain_dir=str(tmp_path / "brain"),
            embedding_model="all-MiniLM-L6-v2",
        ),
        drives=DrivesConfig(),
        homeostasis=HomeostasisConfig(),
        thinker=ThinkerConfig(),
        reflection=ReflectionConfig(),
        workspace=WorkspaceConfig(),
        constitutional=ConstitutionalConfig(),
        web=WebConfig(),
        logging=LoggingConfig(),
        soul=SoulConfig(
            soul_dir=str(tmp_path / "soul"),
        ),
        experimental=ExperimentalConfig(),
    )


# =========================================================================
# Mock LLM (совместимый с LLMBackend Protocol)
# =========================================================================
@pytest.fixture
def mock_llm_response():
    """Стандартный ответ mock LLM (валидный JSON для CognitiveOutput)."""
    return json.dumps(
        {
            "internal_monologue": "Я обрабатываю стимул.",
            "response": "Привет! Я Лея.",
            "action_intent": "RESPOND",
            "tool_call": None,
            "self_reflection": "",
        },
        ensure_ascii=False,
    )


@pytest.fixture
def mock_llm_backend(mock_llm_response):
    """
    Async mock для LLM-бэкенда, совместимый с LLMBackend Protocol.

    Реализует все абстрактные методы LLMBackend:
    - chat(prompt, require_json)
    - generate(prompt, system, max_tokens, require_json, timeout)
    - health_check()
    - is_available (property)
    - close()
    - get_status()
    """
    mock = MagicMock()

    async def _chat(prompt: str, require_json: bool = False, **kwargs) -> str:
        return mock_llm_response

    async def _generate(
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        require_json: bool = False,
        timeout: float | None = None,
    ) -> str:
        return mock_llm_response

    async def _close() -> None:
        pass

    def _health_check() -> bool:
        return True

    def _get_status() -> dict:
        return {
            "backend_type": "MockLLMBackend",
            "is_available": True,
        }

    mock.chat = AsyncMock(side_effect=_chat)
    mock.generate = AsyncMock(side_effect=_generate)
    mock.close = AsyncMock(side_effect=_close)
    mock.health_check = MagicMock(side_effect=_health_check)
    mock.get_status = MagicMock(side_effect=_get_status)

    # Property is_available
    type(mock).is_available = property(lambda self: True)

    return mock


@pytest.fixture
def failing_llm_backend():
    """Async mock для LLM, который всегда падает с LeyaLLMError."""
    from leya_core.exceptions import LeyaLLMError

    mock = MagicMock()

    async def _chat(prompt: str, require_json: bool = False, **kwargs) -> str:
        raise LeyaLLMError("LLM недоступна", context={"test": True})

    async def _generate(
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        require_json: bool = False,
        timeout: float | None = None,
    ) -> str:
        raise LeyaLLMError("LLM недоступна", context={"test": True})

    async def _close() -> None:
        pass

    def _health_check() -> bool:
        return False

    def _get_status() -> dict:
        return {
            "backend_type": "FailingLLMBackend",
            "is_available": False,
        }

    mock.chat = AsyncMock(side_effect=_chat)
    mock.generate = AsyncMock(side_effect=_generate)
    mock.close = AsyncMock(side_effect=_close)
    mock.health_check = MagicMock(side_effect=_health_check)
    mock.get_status = MagicMock(side_effect=_get_status)

    type(mock).is_available = property(lambda self: False)

    return mock


@pytest.fixture
def fake_llm_backend():
    """
    FakeLLMBackend для тестов без Ollama.

    Использует реальную реализацию из tests.fake_backend (Шаг 2.4).
    """
    from tests.fake_backend import FakeLLMBackend

    return FakeLLMBackend(
        responses={
            "привет": json.dumps(
                {
                    "response": "Здравствуй!",
                    "internal_monologue": "Пользователь поздоровался.",
                    "action_intent": "RESPOND",
                    "tool_call": None,
                    "self_reflection": "",
                },
                ensure_ascii=False,
            ),
            "семантические факты": "Факт 1: Лея — цифровое сознание.\n"
            "Факт 2: Лея имеет внутреннюю жизнь.",
        }
    )


# =========================================================================
# Mock ChromaDB
# =========================================================================
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
    empty_result = {
        "ids": [[]],
        "distances": [[]],
        "documents": [[]],
    }
    episodic_collection.query = MagicMock(return_value=empty_result)
    semantic_collection.query = MagicMock(return_value=empty_result)

    # Настройка поведения delete
    episodic_collection.delete = MagicMock()
    semantic_collection.delete = MagicMock()

    # Настройка поведения upsert
    episodic_collection.upsert = MagicMock()
    semantic_collection.upsert = MagicMock()

    # Настройка поведения get (для sync)
    episodic_collection.get = MagicMock(return_value={"ids": []})
    semantic_collection.get = MagicMock(return_value={"ids": []})

    mock_client.get_or_create_collection = MagicMock(
        side_effect=lambda name, **kwargs: (
            episodic_collection if name == "episodic_memory" else semantic_collection
        )
    )

    # Mock embedding function
    mock_client._embedding_function = MagicMock(return_value=[[0.1] * 384])

    return mock_client


# =========================================================================
# Mock MemorySystem
# =========================================================================
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
    memory.get_recent_semantic_facts = AsyncMock(return_value=[])
    memory.update_self_model = AsyncMock()
    memory.get_self_model_context = AsyncMock(return_value="Я — Лея.")
    memory.consolidate_memories = AsyncMock(return_value={})
    memory.forget_weak_memories = AsyncMock(return_value=0)
    memory.get_memory_graph_data = AsyncMock(
        return_value={"nodes": [], "edges": [], "total_engrams": 0, "total_synapses": 0}
    )
    memory.save_state = AsyncMock()
    memory._save_state = AsyncMock()
    memory._load_state = AsyncMock()

    return memory


# =========================================================================
# Примеры энграмм для тестов
# =========================================================================
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


# =========================================================================
# Утилиты для тестов
# =========================================================================
@pytest.fixture
def valid_cognitive_json():
    """Валидный JSON для CognitiveOutput."""
    return json.dumps(
        {
            "response": "Тестовый ответ",
            "internal_monologue": "Тестовый внутренний монолог",
            "action_intent": "RESPOND",
            "tool_call": None,
            "self_reflection": "Тестовая саморефлексия",
        },
        ensure_ascii=False,
    )


@pytest.fixture
def malformed_json():
    """Malformed JSON для тестов repair_json."""
    return '{"response": "Тест", "internal_monologue": "Тест"'  # нет закрывающей }