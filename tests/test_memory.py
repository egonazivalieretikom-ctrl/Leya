"""
Тесты для системы памяти LeyaOS.
Покрывает критические пути: store_perception, retrieve_context, synapses, consolidation.
"""
import math
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from leya_core.config import MemoryConfig
from leya_core.memory import Engram, MemorySystem, MemoryType, Synapse


# =============================================================================
# ФИКСТУРЫ
# =============================================================================

@pytest.fixture
def temp_brain_dir():
    """Временная директория для тестов памяти."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def memory_system(temp_brain_dir):
    """Инициализация MemorySystem для тестов с моком эмбеддингов."""
    config = MemoryConfig(
        brain_dir=str(temp_brain_dir),
        embedding_model="all-MiniLM-L6-v2",
        hmac_key="test_hmac_key_for_tests_" + "x" * 10,  # 33 символа
        unsafe_mode=True,
    )

    with (
        patch("leya_core.memory.chromadb.PersistentClient") as mock_client,
        patch("leya_core.memory.DefaultEmbeddingFunction") as mock_embed_fn,
    ):
        mock_collection = MagicMock()

        def mock_query(query_embeddings, n_results=10):
            return {"ids": [[]], "distances": [[]]}

        mock_collection.query = mock_query
        mock_collection.add = MagicMock()
        mock_collection.delete = MagicMock()
        mock_collection.get = MagicMock(return_value={"ids": []})
        mock_collection.upsert = MagicMock()

        mock_client.return_value.get_or_create_collection.return_value = mock_collection
        mock_embed_fn.return_value = MagicMock(return_value=[[0.1] * 384])

        mem = MemorySystem(config=config, disable_hmac_check=True)
        mem._generate_embedding = MagicMock(return_value=[0.1] * 384)

        yield mem

        if hasattr(mem, "chroma_client") and mem.chroma_client:
            try:
                mem.chroma_client = None
                mem.episodic_collection = None
                mem.semantic_collection = None
            except Exception:
                pass


# =============================================================================
# ENGRAM CREATION TESTS
# =============================================================================

class TestEngramCreation:
    """Тесты создания энграмм."""

    @pytest.mark.asyncio
    async def test_store_perception_creates_engram(self, memory_system):
        """store_perception создаёт энграмму с правильными полями."""
        engram = await memory_system.store_perception(
            content="Тестовое восприятие",
            emotional_boost=0.5,
            metadata={"source": "test"},
        )

        assert isinstance(engram, Engram)
        assert engram.content == "Тестовое восприятие"
        assert engram.memory_type == MemoryType.EPISODIC
        assert engram.emotional_boost == 0.5
        assert engram.metadata == {"source": "test"}
        assert engram.retention_strength == 1.0

    @pytest.mark.asyncio
    async def test_store_fact_creates_semantic_engram(self, memory_system):
        """store_fact создаёт семантическую энграмму."""
        engram = await memory_system.store_fact(
            content="Факт о мире",
            metadata={"category": "science"},
        )

        assert engram.memory_type == MemoryType.SEMANTIC
        assert engram.consolidation_level == 1
        assert engram.retention_strength == 1.0

    @pytest.mark.asyncio
    async def test_store_perception_clamps_emotional_boost(self, memory_system):
        """emotional_boost обрезается до [0.0, 1.0]."""
        engram_high = await memory_system.store_perception(
            content="Тест", emotional_boost=1.5
        )
        assert engram_high.emotional_boost == 1.0

        engram_low = await memory_system.store_perception(
            content="Тест", emotional_boost=-0.5
        )
        assert engram_low.emotional_boost == 0.0

    @pytest.mark.asyncio
    async def test_store_perception_adds_to_chromadb(self, memory_system):
        """store_perception добавляет энграмму в ChromaDB."""
        await memory_system.store_perception(content="Тест")
        memory_system.episodic_collection.add.assert_called()

    @pytest.mark.asyncio
    async def test_store_fact_adds_to_semantic_collection(self, memory_system):
        """store_fact добавляет в semantic_collection."""
        await memory_system.store_fact(content="Факт")
        memory_system.semantic_collection.add.assert_called()


# =============================================================================
# LTP / SYNAPTIC CONNECTIONS TESTS
# =============================================================================

class TestSynapticConnections:
    """Тесты формирования синаптических связей (LTP)."""

    @pytest.mark.asyncio
    async def test_form_synaptic_connections_high_similarity(self, memory_system):
        """При similarity >= 0.7 формируются синапсы в обе стороны."""
        existing_id = "existing-engram-id"

        def mock_query(query_embeddings, n_results=10):
            return {
                "ids": [[existing_id]],
                "distances": [[0.2]],  # similarity = 1 - 0.2 = 0.8 >= 0.7
            }

        memory_system.episodic_collection.query = mock_query

        # Добавляем существующую энграмму в in-memory dict
        existing_engram = Engram(
            id=existing_id,
            content="Существующая энграмма",
            memory_type=MemoryType.EPISODIC,
        )
        memory_system.engrams[existing_id] = existing_engram

        # Сохраняем новую энграмму
        new_engram = await memory_system.store_perception("Похожая энграмма")

        # Проверяем формирование синапсов в обе стороны
        key_forward = f"{new_engram.id}->{existing_id}"
        key_backward = f"{existing_id}->{new_engram.id}"

        assert key_forward in memory_system.synapses
        assert key_backward in memory_system.synapses

        # Проверяем вес синапса (similarity * 0.5 = 0.8 * 0.5 = 0.4)
        assert abs(memory_system.synapses[key_forward].weight - 0.4) < 0.01

    @pytest.mark.asyncio
    async def test_no_synapse_below_threshold(self, memory_system):
        """При similarity < 0.7 синапсы НЕ формируются."""
        existing_id = "existing-engram-id"

        def mock_query(query_embeddings, n_results=10):
            return {
                "ids": [[existing_id]],
                "distances": [[0.5]],  # similarity = 1 - 0.5 = 0.5 < 0.7
            }

        memory_system.episodic_collection.query = mock_query

        existing_engram = Engram(
            id=existing_id,
            content="Существующая энграмма",
            memory_type=MemoryType.EPISODIC,
        )
        memory_system.engrams[existing_id] = existing_engram

        await memory_system.store_perception("Похожая энграмма")

        # Синапсов быть не должно
        assert len(memory_system.synapses) == 0

    @pytest.mark.asyncio
    async def test_strengthen_synapses_on_retrieval(self, memory_system):
        """При совместной активации синапсы усиливаются."""
        # Создаём две энграммы и синапс между ними
        id1 = "engram-1"
        id2 = "engram-2"

        memory_system.engrams[id1] = Engram(
            id=id1, content="Энграмма 1", memory_type=MemoryType.EPISODIC
        )
        memory_system.engrams[id2] = Engram(
            id=id2, content="Энграмма 2", memory_type=MemoryType.EPISODIC
        )

        initial_weight = 0.3
        memory_system.synapses[f"{id1}->{id2}"] = Synapse(
            source_id=id1, target_id=id2, weight=initial_weight
        )

        # Активируем обе энграммы
        await memory_system._strengthen_synapses([id1, id2])

        # Проверяем усиление
        synapse = memory_system.synapses[f"{id1}->{id2}"]
        assert synapse.weight > initial_weight
        assert synapse.activation_count == 1

    @pytest.mark.asyncio
    async def test_synapse_weight_capped_at_1(self, memory_system):
        """Вес синапса не превышает 1.0."""
        id1 = "engram-1"
        id2 = "engram-2"

        memory_system.engrams[id1] = Engram(
            id=id1, content="Энграмма 1", memory_type=MemoryType.EPISODIC
        )
        memory_system.engrams[id2] = Engram(
            id=id2, content="Энграмма 2", memory_type=MemoryType.EPISODIC
        )

        memory_system.synapses[f"{id1}->{id2}"] = Synapse(
            source_id=id1, target_id=id2, weight=0.99
        )

        await memory_system._strengthen_synapses([id1, id2])

        synapse = memory_system.synapses[f"{id1}->{id2}"]
        assert synapse.weight <= 1.0


# =============================================================================
# FORGETTING TESTS (Ebbinghaus curve)
# =============================================================================

class TestForgetting:
    """Тесты забывания по кривой Эббингауза."""

    @pytest.mark.asyncio
    async def test_retention_decreases_over_time(self, memory_system):
        """Retention strength уменьшается со временем."""
        engram = await memory_system.store_perception("Временное восприятие")
        initial_retention = engram.retention_strength

        engram.last_retrieved -= 10000  # 10000 секунд назад
        await memory_system._apply_forgetting()

        assert engram.retention_strength < initial_retention

    @pytest.mark.asyncio
    async def test_emotional_boost_slows_forgetting(self, memory_system):
        """Эмоциональное усиление замедляет забывание."""
        engram_high = await memory_system.store_perception(
            "Важное событие", emotional_boost=0.9
        )
        engram_low = await memory_system.store_perception(
            "Обычное событие", emotional_boost=0.1
        )

        engram_high.last_retrieved -= 5000
        engram_low.last_retrieved -= 5000

        await memory_system._apply_forgetting()

        assert engram_high.retention_strength > engram_low.retention_strength

    @pytest.mark.asyncio
    async def test_forgetting_formula_ebbinghaus(self, memory_system):
        """Проверка формулы Эббингауза: retention = exp(-t / stability)."""
        engram = await memory_system.store_perception("Тест")

        # Устанавливаем параметры
        t = 3600  # 1 час
        engram.last_retrieved = time.time() - t
        engram.emotional_boost = 0.0
        engram.retrieval_count = 0

        base_stability = memory_system.memory_config.forgetting_base_stability

        # Ожидаемое значение по формуле
        expected = math.exp(-t / base_stability)

        await memory_system._apply_forgetting()

        # Проверяем с допуском (из-за float precision)
        assert abs(engram.retention_strength - expected) < 0.01

    @pytest.mark.asyncio
    async def test_retrieval_count_increases_stability(self, memory_system):
        """Частое извлечение увеличивает stability (замедляет забывание)."""
        engram_frequent = await memory_system.store_perception("Частое")
        engram_rare = await memory_system.store_perception("Редкое")

        engram_frequent.retrieval_count = 100
        engram_rare.retrieval_count = 0

        t = 3600
        engram_frequent.last_retrieved -= t
        engram_rare.last_retrieved -= t

        await memory_system._apply_forgetting()

        assert engram_frequent.retention_strength > engram_rare.retention_strength

    @pytest.mark.asyncio
    async def test_semantic_memory_decays_slower(self, memory_system):
        """Семантическая память деградирует медленнее эпизодической."""
        engram_episodic = await memory_system.store_perception("Эпизод")
        engram_semantic = await memory_system.store_fact("Факт")

        t = 3600
        engram_episodic.last_retrieved -= t
        engram_semantic.last_retrieved -= t

        await memory_system._apply_forgetting()

        # Семантическая память не должна падать ниже 99% от текущего значения
        assert engram_semantic.retention_strength >= engram_episodic.retention_strength

    @pytest.mark.asyncio
    async def test_forget_weak_memories(self, memory_system):
        """forget_weak_memories удаляет энграммы с низким retention."""
        # Создаём энграммы с разным retention
        engram_strong = await memory_system.store_perception("Сильная")
        engram_weak = await memory_system.store_perception("Слабая")

        # Имитируем забывание для слабой
        engram_weak.retention_strength = 0.05
        engram_strong.retention_strength = 0.9

        forgotten_count = await memory_system.forget_weak_memories(threshold=0.1)

        assert forgotten_count == 1
        assert engram_weak.id not in memory_system.engrams
        assert engram_strong.id in memory_system.engrams


# =============================================================================
# CONSOLIDATION TESTS
# =============================================================================

class TestConsolidation:
    """Тесты консолидации памяти."""

    @pytest.mark.asyncio
    async def test_consolidate_memories_returns_stats(self, memory_system):
        """consolidate_memories возвращает статистику."""
        await memory_system.store_perception("Эпизод 1")
        await memory_system.store_perception("Эпизод 2")

        stats = await memory_system.consolidate_memories()

        assert "episodes_processed" in stats
        assert "facts_extracted" in stats
        assert "episodes_forgotten" in stats
        assert stats["episodes_processed"] >= 2

    @pytest.mark.asyncio
    async def test_consolidation_without_llm(self, memory_system):
        """Консолидация без LLM не падает."""
        await memory_system.store_perception("Эпизод")

        # llm_client не установлен
        memory_system.llm_client = None

        stats = await memory_system.consolidate_memories()
        assert stats["facts_extracted"] == 0


# =============================================================================
# SELF-MODEL TESTS
# =============================================================================

class TestSelfModel:
    """Тесты само-модели."""

    @pytest.mark.asyncio
    async def test_update_self_model(self, memory_system):
        """update_self_model добавляет рефлексию в self_model."""
        await memory_system.update_self_model("Я учусь понимать мир")

        assert "Я учусь понимать мир" in memory_system.self_model

    @pytest.mark.asyncio
    async def test_self_model_length_limit(self, memory_system):
        """self_model не превышает максимальную длину."""
        long_reflection = "A" * 10000
        await memory_system.update_self_model(long_reflection)

        assert len(memory_system.self_model) <= memory_system.memory_config.max_self_model_length

    @pytest.mark.asyncio
    async def test_self_model_empty_input_ignored(self, memory_system):
        """Пустой ввод не добавляется в self_model."""
        initial_model = memory_system.self_model
        await memory_system.update_self_model("")
        await memory_system.update_self_model("   ")

        assert memory_system.self_model == initial_model


# =============================================================================
# RETRIEVE CONTEXT TESTS
# =============================================================================

class TestRetrieveContext:
    """Тесты retrieve_context."""

    @pytest.mark.asyncio
    async def test_retrieve_context_returns_engrams(self, memory_system):
        """retrieve_context возвращает список энграмм."""
        from unittest.mock import AsyncMock

        engram = await memory_system.store_perception("Тестовая энграмма")

        # Патчим asyncio.to_thread на AsyncMock с side_effect
        with patch("asyncio.to_thread", new=AsyncMock()) as mock_to_thread:
            mock_to_thread.side_effect = [
                [0.1] * 384,  # 1. query_embedding от _generate_embedding
                {"ids": [[engram.id]], "distances": [[0.1]]},  # 2. episodic_results
                {"ids": [[]], "distances": [[]]},  # 3. semantic_results
            ]

            results = await memory_system.retrieve_context("Тест")

        assert len(results) >= 1
        assert any(e.id == engram.id for e in results)

    @pytest.mark.asyncio
    async def test_retrieve_context_increments_retrieval_count(self, memory_system):
        """retrieve_context увеличивает retrieval_count."""
        from unittest.mock import AsyncMock

        engram = await memory_system.store_perception("Тест")
        initial_count = engram.retrieval_count

        with patch("asyncio.to_thread", new=AsyncMock()) as mock_to_thread:
            mock_to_thread.side_effect = [
                [0.1] * 384,  # 1. query_embedding
                {"ids": [[engram.id]], "distances": [[0.1]]},  # 2. episodic_results
                {"ids": [[]], "distances": [[]]},  # 3. semantic_results
            ]

            await memory_system.retrieve_context("Тест")

        assert engram.retrieval_count > initial_count

    @pytest.mark.asyncio
    async def test_retrieve_context_filters_by_min_retention(self, memory_system):
        """retrieve_context фильтрует по min_retention."""
        engram = await memory_system.store_perception("Тест")

        # Устанавливаем last_retrieved в далёкое прошлое,
        # чтобы _apply_forgetting снизил retention ниже 0.1
        # Формула: retention = exp(-t / stability), stability ≈ 3600
        # t = 10000 → retention ≈ exp(-10000/3600) ≈ 0.062 < 0.1
        engram.last_retrieved = time.time() - 10000

        def mock_query(query_embeddings, n_results=10):
            return {
                "ids": [[engram.id]],
                "distances": [[0.1]],
            }

        memory_system.episodic_collection.query = mock_query
        memory_system.semantic_collection.query = MagicMock(
            return_value={"ids": [[]], "distances": [[]]}
        )

        # Патчим asyncio.to_thread
        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch("leya_core.memory.asyncio.to_thread", side_effect=mock_to_thread):
            results = await memory_system.retrieve_context("Тест", min_retention=0.1)

        assert not any(e.id == engram.id for e in results)

# =============================================================================
# PERSISTENCE TESTS (базовые)
# =============================================================================

class TestPersistence:
    """Тесты персистентности (сохранение/загрузка)."""

    @pytest.mark.asyncio
    async def test_save_and_load_state(self, memory_system):
        """Состояние сохраняется и загружается корректно."""
        engram1 = await memory_system.store_perception("Тест 1")
        engram2 = await memory_system.store_fact("Факт 1")

        await memory_system._save_state()

        state_path = Path(memory_system.state_path)
        assert state_path.exists(), f"Файл состояния не создан: {state_path}"

        new_memory = MemorySystem(
            config=memory_system.memory_config,
            disable_hmac_check=True,
        )

        await new_memory._load_state()

        assert len(new_memory.engrams) == len(memory_system.engrams)
        assert engram1.id in new_memory.engrams
        assert engram2.id in new_memory.engrams