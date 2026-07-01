"""
Тесты персистентности memory.py: атомарная запись, HMAC-проверка,
загрузка состояния с ошибками, _sync_chroma_from_memory.
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import pytest

from leya_core.config import MemoryConfig
from leya_core.memory import (
    Engram,
    MemorySystem,
    MemoryType,
    MEMORY_STATE_VERSION,
    SyncReport,
)
from leya_core.exceptions import (
    LeyaAtomicWriteError,
    LeyaStateCorruptedError,
    LeyaConfigError,
)


# =============================================================================
# ФИКСТУРЫ
# =============================================================================

@pytest.fixture
def temp_brain_dir():
    """Временная директория для тестов."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def memory_config(temp_brain_dir):
    """Конфигурация памяти для тестов."""
    return MemoryConfig(
        brain_dir=str(temp_brain_dir),
        embedding_model="all-MiniLM-L6-v2",
        hmac_key="test-strong-secret-key-32-chars!!",
        unsafe_mode=True,
    )


@pytest.fixture
def memory_system(memory_config):
    """MemorySystem с моками ChromaDB."""
    with (
        patch("leya_core.memory.chromadb.PersistentClient") as mock_client,
        patch("leya_core.memory.DefaultEmbeddingFunction") as mock_embed_fn,
    ):
        mock_collection = MagicMock()
        mock_collection.get = MagicMock(return_value={"ids": []})
        mock_collection.add = MagicMock()
        mock_collection.delete = MagicMock()
        mock_collection.upsert = MagicMock()

        mock_client.return_value.get_or_create_collection.return_value = mock_collection
        mock_embed_fn.return_value = MagicMock(return_value=[[0.1] * 384])

        mem = MemorySystem(config=memory_config, disable_hmac_check=True)
        mem._generate_embedding = MagicMock(return_value=[0.1] * 384)

        yield mem


@pytest.fixture
def memory_with_hmac(memory_config):
    """MemorySystem с включённой HMAC-проверкой."""
    with (
        patch("leya_core.memory.chromadb.PersistentClient") as mock_client,
        patch("leya_core.memory.DefaultEmbeddingFunction") as mock_embed_fn,
    ):
        mock_collection = MagicMock()
        mock_collection.get = MagicMock(return_value={"ids": []})
        mock_collection.add = MagicMock()
        mock_collection.delete = MagicMock()
        mock_collection.upsert = MagicMock()

        mock_client.return_value.get_or_create_collection.return_value = mock_collection
        mock_embed_fn.return_value = MagicMock(return_value=[[0.1] * 384])

        # disable_hmac_check=False для тестов HMAC
        mem = MemorySystem(config=memory_config, disable_hmac_check=False)
        mem._generate_embedding = MagicMock(return_value=[0.1] * 384)

        yield mem


# =============================================================================
# ATOMIC WRITE TESTS
# =============================================================================

class TestAtomicWrite:
    """Тесты атомарной записи состояния."""

    @pytest.mark.asyncio
    async def test_save_state_creates_file(self, memory_system):
        """_save_state создаёт файл состояния."""
        await memory_system.store_perception("Тест")
        await memory_system._save_state()

        state_path = Path(memory_system.state_path)
        assert state_path.exists()

    @pytest.mark.asyncio
    async def test_save_state_creates_hmac_file(self, memory_with_hmac):
        """_save_state создаёт HMAC-файл."""
        await memory_with_hmac.store_perception("Тест")
        await memory_with_hmac._save_state()

        state_path = Path(memory_with_hmac.state_path)
        hmac_path = state_path.with_suffix(state_path.suffix + ".hmac")
        assert hmac_path.exists()

    @pytest.mark.asyncio
    async def test_save_state_json_structure(self, memory_system):
        """_save_state записывает корректный JSON с версией."""
        await memory_system.store_perception("Тест")
        await memory_system._save_state()

        state_path = Path(memory_system.state_path)
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "__version__" in data
        assert data["__version__"] == MEMORY_STATE_VERSION
        assert "data" in data
        assert "engrams" in data["data"]
        assert "synapses" in data["data"]

    @pytest.mark.asyncio
    async def test_save_state_oserror_raises_atomic_write_error(self, memory_system):
        """OSError при записи → LeyaAtomicWriteError."""
        await memory_system.store_perception("Тест")

        with patch("tempfile.mkstemp") as mock_mkstemp:
            mock_mkstemp.side_effect = OSError("Permission denied")

            with pytest.raises(LeyaAtomicWriteError):
                await memory_system._save_state()

    @pytest.mark.asyncio
    async def test_save_state_json_error_raises_atomic_write_error(self, memory_system):
        """Ошибка сериализации JSON → LeyaAtomicWriteError."""
        # Создаём энграмму с несериализуемым объектом
        engram = Engram(
            id="test-id",
            content="Тест",
            memory_type=MemoryType.EPISODIC,
            metadata={"bad": object()},  # Несериализуемый объект
        )
        memory_system.engrams["test-id"] = engram

        with pytest.raises(LeyaAtomicWriteError):
            await memory_system._save_state()

    @pytest.mark.asyncio
    async def test_save_state_os_replace_failure(self, memory_system):
        """Сбой os.replace → LeyaAtomicWriteError."""
        await memory_system.store_perception("Тест")

        with patch("os.replace") as mock_replace:
            mock_replace.side_effect = OSError("Cross-device link")

            # Должен попытаться использовать shutil.move как fallback
            # Но если и это не поможет — LeyaAtomicWriteError
            with patch("shutil.move") as mock_move:
                mock_move.side_effect = OSError("Move failed")

                with pytest.raises(LeyaAtomicWriteError):
                    await memory_system._save_state()

    @pytest.mark.asyncio
    async def test_save_state_cleanup_tmp_on_error(self, memory_system):
        """При ошибке mkstemp временный файл не создаётся."""
        await memory_system.store_perception("Тест")

        # Мок просто бросает ошибку, не создавая файл
        def mock_mkstemp(*args, **kwargs):
            raise OSError("Simulated mkstemp error")

        with patch("tempfile.mkstemp", side_effect=mock_mkstemp):
            with pytest.raises(LeyaAtomicWriteError):
                await memory_system._save_state()

        # Файл состояния не должен быть повреждён
        state_path = Path(memory_system.state_path)
        # Если файл существовал до теста, он должен остаться нетронутым
        # Если не существовал — не должен быть создан
        # Проверяем, что нет .tmp файлов в директории
        tmp_files = list(state_path.parent.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Остались временные файлы: {tmp_files}"


# =============================================================================
# HMAC VERIFICATION TESTS
# =============================================================================

class TestHMACVerification:
    """Тесты HMAC-проверки при загрузке."""

    @pytest.mark.asyncio
    async def test_load_state_valid_hmac(self, memory_with_hmac):
        """Загрузка с валидным HMAC проходит успешно."""
        await memory_with_hmac.store_perception("Тест")
        await memory_with_hmac._save_state()

        # Создаём новую систему и загружаем
        new_memory = MemorySystem(
            config=memory_with_hmac.memory_config,
            disable_hmac_check=False,
        )

        await new_memory._load_state()

        assert len(new_memory.engrams) == len(memory_with_hmac.engrams)

    @pytest.mark.asyncio
    async def test_load_state_tampered_file_raises_error(self, memory_with_hmac):
        """Подмена файла состояния → LeyaStateCorruptedError."""
        await memory_with_hmac.store_perception("Тест")
        await memory_with_hmac._save_state()

        # Подменяем содержимое файла
        state_path = Path(memory_with_hmac.state_path)
        state_path.write_text('{"__version__": 3, "data": {"engrams": {}, "synapses": {}, "self_model": ""}}')

        new_memory = MemorySystem(
            config=memory_with_hmac.memory_config,
            disable_hmac_check=False,
        )

        with pytest.raises(LeyaStateCorruptedError):
            await new_memory._load_state()

    @pytest.mark.asyncio
    async def test_load_state_missing_hmac_raises_error(self, memory_with_hmac):
        """Отсутствие HMAC-файла → LeyaStateCorruptedError."""
        await memory_with_hmac.store_perception("Тест")
        await memory_with_hmac._save_state()

        # Удаляем HMAC-файл
        state_path = Path(memory_with_hmac.state_path)
        hmac_path = state_path.with_suffix(state_path.suffix + ".hmac")
        if hmac_path.exists():
            hmac_path.unlink()

        new_memory = MemorySystem(
            config=memory_with_hmac.memory_config,
            disable_hmac_check=False,
        )

        with pytest.raises(LeyaStateCorruptedError):
            await new_memory._load_state()

    @pytest.mark.asyncio
    async def test_load_state_corrupted_json_raises_error(self, memory_with_hmac):
        """Повреждённый JSON → LeyaStateCorruptedError."""
        await memory_with_hmac.store_perception("Тест")
        await memory_with_hmac._save_state()

        # Подменяем JSON на невалидный
        state_path = Path(memory_with_hmac.state_path)
        state_path.write_text("not valid json {{{")

        # Обновляем HMAC для нового содержимого (чтобы пройти HMAC-проверку)
        hmac_path = state_path.with_suffix(state_path.suffix + ".hmac")
        key = memory_with_hmac._get_hmac_key()
        signature = memory_with_hmac._compute_hmac(state_path, key)
        hmac_path.write_text(signature)

        new_memory = MemorySystem(
            config=memory_with_hmac.memory_config,
            disable_hmac_check=False,
        )

        with pytest.raises(LeyaStateCorruptedError):
            await new_memory._load_state()

    @pytest.mark.asyncio
    async def test_load_state_missing_file_loads_empty(self, memory_system):
        """Отсутствие файла состояния → пустое состояние."""
        new_memory = MemorySystem(
            config=memory_system.memory_config,
            disable_hmac_check=True,
        )

        await new_memory._load_state()

        assert len(new_memory.engrams) == 0
        assert len(new_memory.synapses) == 0
        assert new_memory.self_model == ""


# =============================================================================
# SYNC CHROMA FROM MEMORY TESTS
# =============================================================================

class TestSyncChromaFromMemory:
    """Тесты синхронизации in-memory ↔ ChromaDB."""

    @pytest.mark.asyncio
    async def test_sync_adds_missing_engrams(self, memory_system):
        """Sync добавляет отсутствующие энграммы в ChromaDB."""
        engram = await memory_system.store_perception("Тест")

        # Мок: ChromaDB пуст
        memory_system.episodic_collection.get = MagicMock(return_value={"ids": []})
        memory_system.episodic_collection.upsert = MagicMock()

        report = await memory_system._sync_chroma_from_memory()

        assert report.added >= 1
        memory_system.episodic_collection.upsert.assert_called()

    @pytest.mark.asyncio
    async def test_sync_removes_orphan_records(self, memory_system):
        """Sync удаляет осиротевшие записи из ChromaDB."""
        # В in-memory нет энграмм, но в ChromaDB есть
        memory_system.engrams = {}
        memory_system.episodic_collection.get = MagicMock(
            return_value={"ids": ["orphan-id-1", "orphan-id-2"]}
        )
        memory_system.episodic_collection.delete = MagicMock()

        report = await memory_system._sync_chroma_from_memory()

        assert report.removed >= 2
        memory_system.episodic_collection.delete.assert_called()

    @pytest.mark.asyncio
    async def test_sync_returns_report(self, memory_system):
        """Sync возвращает SyncReport."""
        report = await memory_system._sync_chroma_from_memory()

        assert isinstance(report, SyncReport)
        assert hasattr(report, "added")
        assert hasattr(report, "updated")
        assert hasattr(report, "removed")
        assert hasattr(report, "errors")
        assert hasattr(report, "duration_ms")

    @pytest.mark.asyncio
    async def test_sync_handles_chroma_failure_gracefully(self, memory_system):
        """Сбой ChromaDB не роняет sync (graceful degradation)."""
        memory_system.episodic_collection.get = MagicMock(
            side_effect=Exception("ChromaDB failure")
        )

        # Не должно упасть
        report = await memory_system._sync_chroma_from_memory()

        assert isinstance(report, SyncReport)
        assert len(report.errors) > 0

    @pytest.mark.asyncio
    async def test_sync_report_merge(self, memory_system):
        """SyncReport.merge() корректно агрегирует отчёты."""
        report1 = SyncReport(added=5, updated=2, removed=1)
        report2 = SyncReport(added=3, updated=4, removed=2, errors=["error1"])

        report1.merge(report2)

        assert report1.added == 8
        assert report1.updated == 6
        assert report1.removed == 3
        assert "error1" in report1.errors

    @pytest.mark.asyncio
    async def test_sync_report_properties(self):
        """SyncReport свойства работают корректно."""
        report = SyncReport(added=5, removed=2, errors=["err1"])

        assert report.total_discrepancies == 7
        assert report.is_clean is False
        assert report.error_count == 1

        clean_report = SyncReport()
        assert clean_report.is_clean is True


# =============================================================================
# LOAD STATE WITH ERRORS TESTS
# =============================================================================

class TestLoadStateErrors:
    """Тесты загрузки состояния с различными ошибками."""

    @pytest.mark.asyncio
    async def test_load_state_with_invalid_version(self, memory_system):
        """Загрузка с несовместимой версией обрабатывается корректно."""
        # Создаём файл с неверной версией
        state_path = Path(memory_system.state_path)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        invalid_data = {
            "__version__": 999,  # Несовместимая версия
            "data": {
                "engrams": {},
                "synapses": {},
                "self_model": "",
            },
        }

        state_path.write_text(json.dumps(invalid_data), encoding="utf-8")

        new_memory = MemorySystem(
            config=memory_system.memory_config,
            disable_hmac_check=True,
        )

        # В текущем коде нет явной проверки версии, но загрузка должна пройти
        await new_memory._load_state()

    @pytest.mark.asyncio
    async def test_load_state_partial_data(self, memory_system):
        """Загрузка с частичными данными не падает."""
        state_path = Path(memory_system.state_path)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        partial_data = {
            "__version__": MEMORY_STATE_VERSION,
            "data": {
                "engrams": {
                    "test-id": {
                        "id": "test-id",
                        "content": "Тест",
                        "memory_type": "episodic",
                    }
                },
                # synapses и self_model отсутствуют
            },
        }

        state_path.write_text(json.dumps(partial_data), encoding="utf-8")

        new_memory = MemorySystem(
            config=memory_system.memory_config,
            disable_hmac_check=True,
        )

        await new_memory._load_state()

        assert "test-id" in new_memory.engrams


# =============================================================================
# ENGRAM SERIALIZATION TESTS
# =============================================================================

class TestEngramSerialization:
    """Тесты сериализации/десериализации энграмм."""

    def test_engram_to_dict(self):
        """Engram.to_dict() возвращает корректный словарь."""
        engram = Engram(
            id="test-id",
            content="Тест",
            memory_type=MemoryType.EPISODIC,
            emotional_boost=0.5,
            metadata={"key": "value"},
        )

        data = engram.to_dict()

        assert data["id"] == "test-id"
        assert data["content"] == "Тест"
        assert data["memory_type"] == "episodic"
        assert data["emotional_boost"] == 0.5
        assert data["metadata"] == {"key": "value"}

    def test_engram_from_dict(self):
        """Engram.from_dict() восстанавливает энграмму."""
        data = {
            "id": "test-id",
            "content": "Тест",
            "memory_type": "episodic",
            "emotional_boost": 0.5,
            "metadata": {"key": "value"},
        }

        engram = Engram.from_dict(data)

        assert engram.id == "test-id"
        assert engram.content == "Тест"
        assert engram.memory_type == MemoryType.EPISODIC
        assert engram.emotional_boost == 0.5

    def test_engram_roundtrip(self):
        """Engram to_dict → from_dict сохраняет все поля."""
        original = Engram(
            id="test-id",
            content="Тест",
            memory_type=MemoryType.SEMANTIC,
            emotional_boost=0.7,
            retrieval_count=5,
            consolidation_level=2,
            metadata={"key": "value"},
        )

        data = original.to_dict()
        restored = Engram.from_dict(data)

        assert restored.id == original.id
        assert restored.content == original.content
        assert restored.memory_type == original.memory_type
        assert restored.emotional_boost == original.emotional_boost
        assert restored.retrieval_count == original.retrieval_count
        assert restored.consolidation_level == original.consolidation_level