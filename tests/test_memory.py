"""
tests/test_memory.py — Тесты для системы памяти Леи.
Проверяет: забывание по Эббингаузу, LTP, консолидацию, синапсы.
"""
import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from leya_core.memory import MemorySystem, Engram, Synapse, MemoryType


class TestEngram:
    """Тесты для модели Engram."""
    
    def test_engram_initialization(self):
        """Проверка инициализации энграммы."""
        engram = Engram(
            id="test_id",
            content="Тестовое воспоминание",
            memory_type=MemoryType.EPISODIC,
            emotional_boost=0.5
        )
        
        assert engram.id == "test_id"
        assert engram.content == "Тестовое воспоминание"
        assert engram.memory_type == MemoryType.EPISODIC
        assert engram.emotional_boost == 0.5
        assert engram.retention_strength == 1.0
        assert engram.retrieval_count == 0
    
    def test_engram_forgetting_basic(self):
        """Проверка базового забывания по Эббингаузу."""
        engram = Engram(
            id="test_id",
            content="Тест",
            memory_type=MemoryType.EPISODIC,
            timestamp=time.time() - 3600  # 1 час назад
        )
        
        current_time = time.time()
        retention = engram.calculate_forgetting(current_time)
        
        #Retention должно уменьшиться со временем
        assert retention < 1.0
        assert retention > 0.0
    
    def test_engram_forgetting_with_emotional_boost(self):
        """Проверка влияния эмоционального усиления на забывание."""
        engram1 = Engram(
            id="test1",
            content="Обычное воспоминание",
            memory_type=MemoryType.EPISODIC,
            timestamp=time.time() - 3600,
            emotional_boost=0.0
        )
        
        engram2 = Engram(
            id="test2",
            content="Эмоциональное воспоминание",
            memory_type=MemoryType.EPISODIC,
            timestamp=time.time() - 3600,
            emotional_boost=0.8
        )
        
        current_time = time.time()
        retention1 = engram1.calculate_forgetting(current_time)
        retention2 = engram2.calculate_forgetting(current_time)
        
        # Эмоциональное воспоминание должно забываться медленнее
        assert retention2 > retention1
    
    def test_engram_forgetting_with_retrieval(self):
        """Проверка влияния извлечения на забывание (LTP-подобный эффект)."""
        engram = Engram(
            id="test_id",
            content="Тест",
            memory_type=MemoryType.EPISODIC,
            timestamp=time.time() - 3600,
            retrieval_count=0
        )
        
        current_time = time.time()
        retention_before = engram.calculate_forgetting(current_time)
        
        # Увеличиваем количество извлечений
        engram.retrieval_count = 5
        retention_after = engram.calculate_forgetting(current_time)
        
        # После извлечения retention должно быть выше
        assert retention_after > retention_before


class TestSynapse:
    """Тесты для модели Synapse."""
    
    def test_synapse_initialization(self):
        """Проверка инициализации синапса."""
        synapse = Synapse(source_id="id1", target_id="id2", weight=0.5)
        
        assert synapse.source_id == "id1"
        assert synapse.target_id == "id2"
        assert synapse.weight == 0.5
        assert synapse.activation_count == 0
    
    def test_synapse_strengthen(self):
        """Проверка усиления синапса (LTP)."""
        synapse = Synapse(source_id="id1", target_id="id2", weight=0.5)
        
        synapse.strengthen(delta=0.1)
        
        assert synapse.weight == 0.6
        assert synapse.activation_count == 1
    
    def test_synapse_strengthen_limit(self):
        """Проверка ограничения веса синапса (максимум 1.0)."""
        synapse = Synapse(source_id="id1", target_id="id2", weight=0.95)
        
        synapse.strengthen(delta=0.1)
        
        assert synapse.weight == 1.0  # Ограничено максимумом
    
    def test_synapse_weaken(self):
        """Проверка ослабления синапса (LTD)."""
        synapse = Synapse(source_id="id1", target_id="id2", weight=0.5)
        
        synapse.weaken(delta=0.1)
        
        assert synapse.weight == 0.4
    
    def test_synapse_weaken_limit(self):
        """Проверка ограничения веса синапса (минимум 0.0)."""
        synapse = Synapse(source_id="id1", target_id="id2", weight=0.05)
        
        synapse.weaken(delta=0.1)
        
        assert synapse.weight == 0.0  # Ограничено минимумом


class TestMemorySystem:
    """Тесты для MemorySystem."""
    
    @pytest.mark.asyncio
    async def test_memory_initialization(self, temp_brain_dir):
        """Проверка инициализации MemorySystem."""
        memory = MemorySystem(persist_directory=temp_brain_dir)
        
        assert memory.persist_directory == temp_brain_dir
        assert memory.episodic_collection is not None
        assert memory.semantic_collection is not None
        assert len(memory.engrams) == 0
        assert len(memory.synapses) == 0
    
    @pytest.mark.asyncio
    async def test_store_perception(self, temp_brain_dir):
        """Проверка сохранения восприятия."""
        memory = MemorySystem(persist_directory=temp_brain_dir)
        
        engram_id = await memory.store_perception(
            content="Тестовое воспоминание для проверки сохранения",
            drive_state={"CURIOSITY": 0.5},
            importance=0.7
        )
        
        assert engram_id is not None
        assert engram_id in memory.engrams
        assert memory.engrams[engram_id].content == "Тестовое воспоминание для проверки сохранения"
        assert memory.engrams[engram_id].emotional_boost == 0.7
    
    @pytest.mark.asyncio
    async def test_store_perception_too_short(self, temp_brain_dir):
        """Проверка пропуска слишком короткого восприятия."""
        memory = MemorySystem(persist_directory=temp_brain_dir)
        
        engram_id = await memory.store_perception(
            content="Коротко",
            drive_state={},
            importance=0.5
        )
        
        assert engram_id is None
        assert len(memory.engrams) == 0
    
    @pytest.mark.asyncio
    async def test_store_fact(self, temp_brain_dir):
        """Проверка сохранения семантического факта."""
        memory = MemorySystem(persist_directory=temp_brain_dir)
        
        engram_id = await memory.store_fact(
            fact="Тестовый факт для проверки семантической памяти",
            category="test"
        )
        
        assert engram_id is not None
        assert engram_id in memory.engrams
        assert memory.engrams[engram_id].memory_type == MemoryType.SEMANTIC
        assert memory.engrams[engram_id].consolidation_level == 0.5
    
    @pytest.mark.asyncio
    async def test_retrieve_context(self, temp_brain_dir):
        """Проверка извлечения контекста."""
        memory = MemorySystem(persist_directory=temp_brain_dir)
        
        # Сохраняем несколько восприятий
        await memory.store_perception(
            content="Первое воспоминание о квантовой физике",
            drive_state={},
            importance=0.5
        )
        await memory.store_perception(
            content="Второе воспоминание о квантовой механике",
            drive_state={},
            importance=0.6
        )
        
        # Извлекаем контекст
        context = await memory.retrieve_context(
            current_stimulus="квантовая физика",
            current_drive_state={},
            limit=5
        )
        
        assert "квантовой" in context.lower()
        assert len(context) > 0
    
    @pytest.mark.asyncio
    async def test_update_self_model(self, temp_brain_dir):
        """Проверка обновления модели себя."""
        memory = MemorySystem(persist_directory=temp_brain_dir)
        
        await memory.update_self_model("Я начинаю понимать себя лучше")
        
        assert "понимать себя лучше" in memory.self_model
    
    @pytest.mark.asyncio
    async def test_get_self_model_context(self, temp_brain_dir):
        """Проверка получения контекста модели себя."""
        memory = MemorySystem(persist_directory=temp_brain_dir)
        
        await memory.update_self_model("Инсайт 1")
        await memory.update_self_model("Инсайт 2")
        
        context = await memory.get_self_model_context()
        
        assert "Инсайт 1" in context
        assert "Инсайт 2" in context
    
    @pytest.mark.asyncio
    async def test_consolidate_memories(self, temp_brain_dir, mock_llm_with_facts):
        """Проверка консолидации памяти."""
        memory = MemorySystem(persist_directory=temp_brain_dir)
        
        # Сохраняем несколько восприятий
        for i in range(5):
            await memory.store_perception(
                content=f"Воспоминание номер {i} для проверки консолидации памяти",
                drive_state={},
                importance=0.5
            )
        
        initial_count = len(memory.engrams)
        
        # Запускаем консолидацию
        await memory.consolidate_memories(llm_client=mock_llm_with_facts)
        
        # Некоторые энграммы должны быть удалены (prune слабых)
        # или добавлены семантические факты
        assert len(memory.engrams) != initial_count or len(memory.semantic_collection.get()["ids"]) > 0
    
    @pytest.mark.asyncio
    async def test_synapse_formation(self, temp_brain_dir):
        """Проверка формирования синапсов при сохранении восприятия."""
        memory = MemorySystem(persist_directory=temp_brain_dir)
        
        # Сохраняем похожие восприятия
        id1 = await memory.store_perception(
            content="Квантовая физика изучает микроскопические системы",
            drive_state={},
            importance=0.5
        )
        
        id2 = await memory.store_perception(
            content="Квантовая механика описывает поведение атомов",
            drive_state={},
            importance=0.5
        )
        
        # Должны сформироваться синапсы между похожими энграммами
        assert len(memory.synapses) > 0
        
        # Проверяем наличие синапсов
        synapse_exists = any(
            (id1 in key and id2 in key) or (id2 in key and id1 in key)
            for key in memory.synapses.keys()
        )
        assert synapse_exists
    
    @pytest.mark.asyncio
    async def test_save_and_load_state(self, temp_brain_dir):
        """Проверка сохранения и загрузки состояния памяти."""
        memory1 = MemorySystem(persist_directory=temp_brain_dir)
        
        await memory1.store_perception(
            content="Тестовое воспоминание для проверки персистентности",
            drive_state={},
            importance=0.5
        )
        
        initial_engrams = len(memory1.engrams)
        initial_synapses = len(memory1.synapses)
        
        # Создаем новый экземпляр (должен загрузить состояние)
        memory2 = MemorySystem(persist_directory=temp_brain_dir)
        
        assert len(memory2.engrams) == initial_engrams
        assert len(memory2.synapses) == initial_synapses
    
    @pytest.mark.asyncio
    async def test_forget_weak_memories(self, temp_brain_dir):
        """Проверка забывания слабых воспоминаний."""
        memory = MemorySystem(persist_directory=temp_brain_dir)
        
        # Сохраняем восприятие с низкой важностью
        engram_id = await memory.store_perception(
            content="Слабое воспоминание для проверки забывания",
            drive_state={},
            importance=0.1
        )
        
        # Искусственно занижаем retention_strength
        memory.engrams[engram_id].retention_strength = 0.05
        
        # Запускаем забывание
        await memory._forget_weak_memories(threshold=0.15)
        
        # Энграмма должна быть удалена
        assert engram_id not in memory.engrams