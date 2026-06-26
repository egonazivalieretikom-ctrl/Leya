"""
Тесты для MemorySystem.

Проверяет:
- Кривую забывания Эббингауза
- LTP (усиление синапсов)
- Сохранение и загрузку состояния (с HMAC)
- get_recent_episodes
- forget_weak_memories
- update_self_model
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import pickle
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from leya_core.exceptions import (
    LeyaMemoryError,
    LeyaStateCorruptedError,
    LeyaStateVersionMismatchError,
)
from leya_core.memory import (
    Engram,
    MEMORY_STATE_VERSION,
    MemorySystem,
    MemoryType,
    Synapse,
)


class TestEngram:
    """Тесты модели Engram."""

    def test_engram_creation(self):
        """Engram корректно создаётся."""
        engram = Engram(
            id="test1",
            content="Тестовая энграмма",
            memory_type=MemoryType.EPISODIC,
        )

        assert engram.id == "test1"
        assert engram.content == "Тестовая энграмма"
        assert engram.memory_type == MemoryType.EPISODIC
        assert engram.retention_strength == 1.0
        assert engram.retrieval_count == 0

    def test_engram_to_dict(self):
        """Engram корректно сериализуется в dict."""
        engram = Engram(
            id="test1",
            content="Тест",
            memory_type=MemoryType.EPISODIC,
            emotional_boost=0.5,
        )

        data = engram.to_dict()

        assert data["id"] == "test1"
        assert data["content"] == "Тест"
        assert data["memory_type"] == "episodic"
        assert data["emotional_boost"] == 0.5

    def test_engram_from_dict(self):
        """Engram корректно десериализуется из dict."""
        data = {
            "id": "test1",
            "content": "Тест",
            "memory_type": "episodic",
            "retention_strength": 0.8,
            "emotional_boost": 0.3,
            "retrieval_count": 5,
        }

        engram = Engram.from_dict(data)

        assert engram.id == "test1"
        assert engram.retention_strength == 0.8
        assert engram.emotional_boost == 0.3
        assert engram.retrieval_count == 5


class TestSynapse:
    """Тесты модели Synapse."""

    def test_synapse_creation(self):
        """Synapse корректно создаётся."""
        synapse = Synapse(source_id="a", target_id="b", weight=0.5)

        assert synapse.source_id == "a"
        assert synapse.target_id == "b"
        assert synapse.weight == 0.5

    def test_synapse_to_dict(self):
        """Synapse корректно сериализуется."""
        synapse = Synapse(source_id="a", target_id="b", weight=0.7)
        data = synapse.to_dict()

        assert data["source_id"] == "a"
        assert data["weight"] == 0.7


class TestEbbinghausForgetting:
    """Тесты кривой забывания Эббингауза."""

    @pytest.mark.asyncio
    async def test_retention_decreases_over_time(self, test_memory_config):
        """Retention уменьшается со временем (без доступа)."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()
            memory = MemorySystem(config=test_memory_config)

            # Создаём энграмму с timestamp в прошлом
            engram = Engram(
                id="old_ep",
                content="Старый эпизод",
                memory_type=MemoryType.EPISODIC,
                timestamp=time.time() - 7200,  # 2 часа назад
                last_retrieved=time.time() - 7200,
                retention_strength=1.0,
            )
            memory.engrams["old_ep"] = engram

            # Применяем забывание
            await memory._apply_forgetting()

            # Retention должен уменьшиться
            assert memory.engrams["old_ep"].retention_strength < 1.0
            assert memory.engrams["old_ep"].retention_strength > 0.0

    @pytest.mark.asyncio
    async def test_emotional_boost_slows_forgetting(self, test_memory_config):
        """Эмоциональное усиление замедляет забывание."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()
            memory = MemorySystem(config=test_memory_config)

            # Две энграммы одинакового возраста
            now = time.time()
            engram_normal = Engram(
                id="normal",
                content="Обычный эпизод",
                memory_type=MemoryType.EPISODIC,
                timestamp=now - 3600,
                last_retrieved=now - 3600,
                emotional_boost=0.0,
            )
            engram_emotional = Engram(
                id="emotional",
                content="Эмоциональный эпизод",
                memory_type=MemoryType.EPISODIC,
                timestamp=now - 3600,
                last_retrieved=now - 3600,
                emotional_boost=0.8,
            )

            memory.engrams["normal"] = engram_normal
            memory.engrams["emotional"] = engram_emotional

            await memory._apply_forgetting()

            # Эмоциональная энграмма должна иметь больший retention
            assert (
                memory.engrams["emotional"].retention_strength
                > memory.engrams["normal"].retention_strength
            )

    @pytest.mark.asyncio
    async def test_retrieval_count_slows_forgetting(self, test_memory_config):
        """Частое извлечение замедляет забывание."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()
            memory = MemorySystem(config=test_memory_config)

            now = time.time()
            engram_frequent = Engram(
                id="frequent",
                content="Часто извлекаемый",
                memory_type=MemoryType.EPISODIC,
                timestamp=now - 3600,
                last_retrieved=now - 3600,
                retrieval_count=100,
            )
            engram_rare = Engram(
                id="rare",
                content="Редко извлекаемый",
                memory_type=MemoryType.EPISODIC,
                timestamp=now - 3600,
                last_retrieved=now - 3600,
                retrieval_count=0,
            )

            memory.engrams["frequent"] = engram_frequent
            memory.engrams["rare"] = engram_rare

            await memory._apply_forgetting()

            assert (
                memory.engrams["frequent"].retention_strength
                > memory.engrams["rare"].retention_strength
            )


class TestLTP:
    """Тесты Long-Term Potentiation (LTP)."""

    @pytest.mark.asyncio
    async def test_strengthen_synapses(self, test_memory_config):
        """Совместная активация усиливает синапсы."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()
            memory = MemorySystem(config=test_memory_config)

            # Создаём синапс
            memory.synapses["a->b"] = Synapse(
                source_id="a", target_id="b", weight=0.3
            )

            initial_weight = memory.synapses["a->b"].weight

            # Усиливаем
            await memory._strengthen_synapses(["a", "b"])

            assert memory.synapses["a->b"].weight > initial_weight


class TestMemoryPersistence:
    """Тесты персистентности с HMAC."""

    @pytest.mark.asyncio
    async def test_save_and_load_state(self, test_memory_config):
        """Сохранение и загрузка состояния работают корректно."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()
            memory = MemorySystem(config=test_memory_config)

            # Добавляем данные
            memory.engrams["test1"] = Engram(
                id="test1",
                content="Тест",
                memory_type=MemoryType.EPISODIC,
            )
            memory.self_model = "Я — Лея."

            # Сохраняем
            await memory._save_state()

            # Проверяем, что файлы созданы
            state_path = Path(memory.state_path)
            assert state_path.exists()
            assert state_path.with_suffix(state_path.suffix + ".hmac").exists()

            # Очищаем и загружаем
            memory.engrams = {}
            memory.self_model = ""

            await memory._load_state()

            assert "test1" in memory.engrams
            assert memory.self_model == "Я — Лея."

    @pytest.mark.asyncio
    async def test_load_corrupted_state(self, test_memory_config):
        """Загрузка повреждённого файла бросает исключение."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()
            memory = MemorySystem(config=test_memory_config)

            # Создаём повреждённый файл
            state_path = Path(memory.state_path)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_bytes(b"corrupted data")

            # Создаём HMAC файл с неправильной подписью
            hmac_path = state_path.with_suffix(state_path.suffix + ".hmac")
            hmac_path.write_text("invalid_signature")

            with pytest.raises(LeyaStateCorruptedError):
                await memory._load_state()

    @pytest.mark.asyncio
    async def test_load_version_mismatch(self, test_memory_config):
        """Загрузка файла с несовместимой версией бросает исключение."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()
            memory = MemorySystem(config=test_memory_config)

            # Создаём файл с неправильной версией
            state_path = Path(memory.state_path)
            state_path.parent.mkdir(parents=True, exist_ok=True)

            payload = {
                "__version__": 999,  # Несовместимая версия
                "data": {"engrams": {}, "synapses": {}, "self_model": ""},
            }
            with state_path.open("wb") as f:
                pickle.dump(payload, f)

            # Создаём правильный HMAC
            key = memory._get_hmac_key()
            signature = memory._compute_hmac(state_path, key)
            hmac_path = state_path.with_suffix(state_path.suffix + ".hmac")
            hmac_path.write_text(signature)

            with pytest.raises(LeyaStateVersionMismatchError):
                await memory._load_state()


class TestGetRecentEpisodes:
    """Тесты публичного API get_recent_episodes."""

    @pytest.mark.asyncio
    async def test_get_recent_episodes_sorted(self, test_memory_config):
        """Эпизоды отсортированы по timestamp (свежие первыми)."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()
            memory = MemorySystem(config=test_memory_config)

            now = time.time()
            memory.engrams = {
                "old": Engram(
                    id="old",
                    content="Старый",
                    memory_type=MemoryType.EPISODIC,
                    timestamp=now - 100,
                    retention_strength=0.5,
                ),
                "new": Engram(
                    id="new",
                    content="Новый",
                    memory_type=MemoryType.EPISODIC,
                    timestamp=now - 10,
                    retention_strength=0.5,
                ),
            }

            episodes = await memory.get_recent_episodes(limit=10)

            assert len(episodes) == 2
            assert episodes[0].id == "new"
            assert episodes[1].id == "old"

    @pytest.mark.asyncio
    async def test_get_recent_episodes_filters_by_retention(self, test_memory_config):
        """Эпизоды с низким retention отфильтровываются."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()
            memory = MemorySystem(config=test_memory_config)

            now = time.time()
            memory.engrams = {
                "strong": Engram(
                    id="strong",
                    content="Сильный",
                    memory_type=MemoryType.EPISODIC,
                    timestamp=now,
                    retention_strength=0.8,
                ),
                "weak": Engram(
                    id="weak",
                    content="Слабый",
                    memory_type=MemoryType.EPISODIC,
                    timestamp=now,
                    retention_strength=0.01,  # Ниже порога
                ),
            }

            episodes = await memory.get_recent_episodes(limit=10)

            assert len(episodes) == 1
            assert episodes[0].id == "strong"

    @pytest.mark.asyncio
    async def test_get_recent_episodes_limit(self, test_memory_config):
        """Лимит работает корректно."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()
            memory = MemorySystem(config=test_memory_config)

            now = time.time()
            for i in range(10):
                memory.engrams[f"ep{i}"] = Engram(
                    id=f"ep{i}",
                    content=f"Эпизод {i}",
                    memory_type=MemoryType.EPISODIC,
                    timestamp=now - i,
                    retention_strength=0.5,
                )

            episodes = await memory.get_recent_episodes(limit=3)

            assert len(episodes) == 3


class TestForgetWeakMemories:
    """Тесты забывания слабых воспоминаний."""

    @pytest.mark.asyncio
    async def test_forget_weak_memories(self, test_memory_config):
        """Слабые энграммы удаляются."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_client = MagicMock()
            mock_collection = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_chroma.return_value = mock_client

            memory = MemorySystem(config=test_memory_config)

            memory.engrams = {
                "strong": Engram(
                    id="strong",
                    content="Сильный",
                    memory_type=MemoryType.EPISODIC,
                    retention_strength=0.8,
                ),
                "weak": Engram(
                    id="weak",
                    content="Слабый",
                    memory_type=MemoryType.EPISODIC,
                    retention_strength=0.05,  # Ниже порога
                ),
            }

            forgotten = await memory.forget_weak_memories(threshold=0.1)

            assert forgotten == 1
            assert "strong" in memory.engrams
            assert "weak" not in memory.engrams