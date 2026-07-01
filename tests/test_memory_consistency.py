"""Тесты задачи 1.4: consistency ChromaDB <-> in-memory engrams/synapses.

Проверяем:
- После load выполняется sync, и Chroma отражает in-memory состояние
- Orphan records в Chroma удаляются при sync
- Метрики расхождений логируются
- Graceful degradation при недоступности Chroma
"""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from leya_core.memory import MemorySystem, MemoryType

# =================================================================================
# ФИКСТУРЫ И МОКИ
# =================================================================================


class FakeChromaCollection:
    """Мок Chroma-коллекции с in-memory хранением."""

    def __init__(self):
        self._store: dict = {}  # id -> {document, embedding, metadata}
        self.upsert_calls = 0
        self.delete_calls = 0

    def add(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ):
        """Добавление записей (алиас для upsert в тестах)."""
        self.upsert(ids, documents, embeddings, metadatas)

    def upsert(self, ids, documents=None, embeddings=None, metadatas=None):
        self.upsert_calls += 1
        for i, id_ in enumerate(ids):
            self._store[id_] = {
                "document": documents[i] if documents else None,
                "embedding": embeddings[i] if embeddings else None,
                "metadata": metadatas[i] if metadatas else None,
            }

    def delete(self, ids=None, where=None):
        self.delete_calls += 1
        if ids:
            for id_ in ids:
                self._store.pop(id_, None)

    def get(self, ids=None, include=None):
        if ids is None:
            return {"ids": list(self._store.keys())}
        return {"ids": [i for i in ids if i in self._store]}

    def query(self, query_embeddings=None, n_results=5, include=None):
        # Возвращаем все IDs (упрощённо)
        all_ids = list(self._store.keys())[:n_results]
        return {
            "ids": [all_ids],
            "documents": [[self._store[i]["document"] for i in all_ids]],
            "distances": [[0.1] * len(all_ids)],
            "metadatas": [[self._store[i]["metadata"] for i in all_ids]],
        }

    def count(self):
        return len(self._store)


class FakeChromaClient:
    """Мок chromadb.PersistentClient."""

    def __init__(self):
        self.collections = {
            "episodic": FakeChromaCollection(),
            "semantic": FakeChromaCollection(),
        }

    def get_or_create_collection(self, name, metadata=None):
        if name not in self.collections:
            self.collections[name] = FakeChromaCollection()
        return self.collections[name]


def _make_engram(id_: str, content: str, memory_type: str = "EPISODIC"):
    """Создаёт минимальный Engram-подобный объект."""
    from dataclasses import field

    mem_type_enum = MemoryType[memory_type]

    @dataclass
    class Engram:
        id: str
        content: str
        memory_type: MemoryType
        retention_strength: float = 1.0
        emotional_boost: float = 0.0
        retrieval_count: int = 0
        consolidation_level: float = 0.0
        metadata: dict = field(default_factory=dict)
        embedding: list = field(default_factory=lambda: [0.1] * 384)
        created_at: float = 0.0
        last_accessed: float = 0.0

        def to_dict(self):
            return {
                "id": self.id,
                "content": self.content,
                "memory_type": self.memory_type.value,
                "retention_strength": self.retention_strength,
                "emotional_boost": self.emotional_boost,
                "retrieval_count": self.retrieval_count,
                "consolidation_level": self.consolidation_level,
                "metadata": self.metadata,
                "embedding": self.embedding,
                "created_at": self.created_at,
                "last_accessed": self.last_accessed,
            }

        @classmethod
        def from_dict(cls, d):
            d = d.copy()
            if isinstance(d.get("memory_type"), str):
                d["memory_type"] = MemoryType[d["memory_type"]]
            return cls(**d)

    return Engram(id=id_, content=content, memory_type=mem_type_enum)


@pytest.fixture
def memory_with_fake_chroma(tmp_path):
    """Создаёт MemorySystem с мокнутым Chroma-клиентом."""
    from leya_core.config import MemoryConfig

    cfg = MemoryConfig(brain_dir=str(tmp_path), hmac_key="YURPm_zimc0fThT-YxV-wtBM383uh7TTkwk6SbJimh8")

    with patch("chromadb.PersistentClient") as mock_client_cls:
        fake_client = FakeChromaClient()
        mock_client_cls.return_value = fake_client

        # Мокаем sentence-transformers (эмбеддинги)
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_model.encode.return_value = [0.1] * 384
            mock_st.return_value = mock_model

            mem = MemorySystem(cfg)
            # Подменяем реальный клиент на fake для контроля
            mem._chroma_client = fake_client
            mem.episodic_collection = fake_client.get_or_create_collection("episodic")
            mem.semantic_collection = fake_client.get_or_create_collection("semantic")

            yield mem, fake_client


# =================================================================================
# ТЕСТЫ SYNC
# =================================================================================


class TestSyncChromaFromMemory:
    """Проверяем _sync_chroma_from_memory."""

    @pytest.mark.asyncio
    async def test_sync_adds_missing_engrams_to_chroma(self, memory_with_fake_chroma):
        """In-memory engram, отсутствующий в Chroma, добавляется при sync."""
        mem, fake_client = memory_with_fake_chroma
        epi = fake_client.collections["episodic"]

        # Добавляем engram только в in-memory
        mem.engrams = {
            "e1": _make_engram("e1", "memory one", "EPISODIC"),
            "e2": _make_engram("e2", "memory two", "EPISODIC"),
        }
        # Chroma пуст
        assert epi.count() == 0

        report = await mem._sync_chroma_from_memory()

        assert report.added_to_chroma == 2
        assert report.removed_from_chroma == 0
        assert epi.count() == 2
        assert "e1" in epi._store
        assert "e2" in epi._store

    @pytest.mark.asyncio
    async def test_sync_removes_orphan_records_from_chroma(self, memory_with_fake_chroma):
        """Orphan records в Chroma (нет в in-memory) удаляются."""
        mem, fake_client = memory_with_fake_chroma
        epi = fake_client.collections["episodic"]

        # В Chroma есть "orphan"
        epi.upsert(ids=["orphan1", "orphan2"], documents=["x", "y"])
        assert epi.count() == 2

        # In-memory пусто
        mem.engrams = {}

        report = await mem._sync_chroma_from_memory()

        assert report.removed_from_chroma == 2
        assert epi.count() == 0

    @pytest.mark.asyncio
    async def test_sync_updates_existing_engrams(self, memory_with_fake_chroma):
        """Если engram есть в обоих хранилищах — он обновляется (upsert)."""
        mem, fake_client = memory_with_fake_chroma
        epi = fake_client.collections["episodic"]

        # В Chroma старая версия
        epi.upsert(ids=["e1"], documents=["old content"])

        # В in-memory новая версия
        mem.engrams = {"e1": _make_engram("e1", "new content", "EPISODIC")}

        report = await mem._sync_chroma_from_memory()

        assert report.updated_in_chroma >= 1  # upsert всегда вызывается
        assert epi._store["e1"]["document"] == "new content"

    @pytest.mark.asyncio
    async def test_sync_handles_both_memory_types(self, memory_with_fake_chroma):
        """EPISODIC и SEMANTIC engrams идут в разные коллекции."""
        mem, fake_client = memory_with_fake_chroma

        mem.engrams = {
            "e1": _make_engram("e1", "episode", "EPISODIC"),
            "s1": _make_engram("s1", "fact", "SEMANTIC"),
        }

        report = await mem._sync_chroma_from_memory()

        assert fake_client.collections["episodic"].count() == 1
        assert fake_client.collections["semantic"].count() == 1
        assert report.added_to_chroma == 2

    @pytest.mark.asyncio
    async def test_sync_logs_discrepancies(self, memory_with_fake_chroma, caplog):
        """Расхождения логируются с метриками."""
        import logging

        mem, fake_client = memory_with_fake_chroma
        epi = fake_client.collections["episodic"]

        # Создаём расхождение
        epi.upsert(ids=["orphan"], documents=["x"])
        mem.engrams = {"new": _make_engram("new", "new", "EPISODIC")}

        with caplog.at_level(logging.INFO):
            report = await mem._sync_chroma_from_memory()

        # Должен быть лог с метриками
        assert any(
            "sync" in rec.message.lower()
            or "расхожд" in rec.message.lower()
            or "synchro" in rec.message.lower()
            for rec in caplog.records
        )
        assert report.added_to_chroma == 1
        assert report.removed_from_chroma == 1

    @pytest.mark.asyncio
    async def test_sync_idempotent(self, memory_with_fake_chroma):
        """Повторный sync без изменений не должен менять состояние."""
        mem, fake_client = memory_with_fake_chroma

        mem.engrams = {"e1": _make_engram("e1", "x", "EPISODIC")}
        await mem._sync_chroma_from_memory()

        # Второй sync
        report = await mem._sync_chroma_from_memory()
        # Добавлений/удалений быть не должно (только upsert существующих)
        assert report.added_to_chroma == 0
        assert report.removed_from_chroma == 0


# =================================================================================
# ТЕСТЫ LOAD + SYNC
# =================================================================================


class TestLoadStateSync:
    """Проверяем, что _load_state вызывает sync."""

    @pytest.mark.asyncio
    async def test_load_state_calls_sync(self, memory_with_fake_chroma, tmp_path):
        """_load_state загружает state и вызывает sync (популяция Chroma). Используем реальный _save_state для валидного HMAC."""
        mem, fake_client = memory_with_fake_chroma
        epi = fake_client.collections["episodic"]
        assert epi.count() == 0

        mem.engrams = {"e1": _make_engram("e1", "from json", "EPISODIC")}
        mem.synapses = {}
        mem.self_model = "test"
        await mem._save_state()

        mem.engrams = {}
        mem.synapses = {}
        mem.self_model = ""
        await mem._load_state()
        assert epi.count() == 1

    @pytest.mark.asyncio
    async def test_load_state_removes_orphans_from_chroma(self, memory_with_fake_chroma, tmp_path):
        """После load orphan'ы удаляются из Chroma через sync."""
        mem, fake_client = memory_with_fake_chroma
        epi = fake_client.collections["episodic"]

        epi.upsert(ids=["orphan"], documents=["x"])
        assert epi.count() == 1

        mem.engrams = {}
        mem.synapses = {}
        mem.self_model = ""
        await mem._save_state()

        mem.engrams = {}
        mem.synapses = {}
        mem.self_model = ""
        await mem._load_state()
        assert epi.count() == 0


# =================================================================================
# ТЕСТЫ GRACEFUL DEGRADATION
# =================================================================================


class TestSyncGracefulDegradation:
    """Sync не должен ронять систему при проблемах с Chroma."""

    @pytest.mark.asyncio
    async def test_sync_survives_chroma_failure(self, memory_with_fake_chroma):
        """Если Chroma падает — sync логирует ошибку, но не роняет."""
        mem, fake_client = memory_with_fake_chroma
        mem.engrams = {"e1": _make_engram("e1", "x", "EPISODIC")}

        # Ломаем upsert
        fake_client.collections["episodic"].upsert = MagicMock(
            side_effect=RuntimeError("Chroma is down")
        )

        # Не должно упасть
        report = await mem._sync_chroma_from_memory()
        assert report.errors > 0 or report.added_to_chroma == 0

    @pytest.mark.asyncio
    async def test_sync_survives_embedding_failure(self, memory_with_fake_chroma):
        """Если генерация эмбеддинга падает — engram пропускается с warning."""
        mem, fake_client = memory_with_fake_chroma
        mem.engrams = {"e1": _make_engram("e1", "x", "EPISODIC")}

        # Ломаем генерацию эмбеддингов
        with patch.object(mem, "_generate_embedding", side_effect=RuntimeError("embed fail")):
            report = await mem._sync_chroma_from_memory()
            # Engram не добавлен, но система не упала
            assert report.errors >= 1 or report.added_to_chroma == 0


# =================================================================================
# ТЕСТЫ STORE/RETRIEVE CONSISTENCY
# =================================================================================


class TestStoreRetrieveConsistency:
    """Проверяем, что store_perception и retrieve_context не ломают consistency."""

    @pytest.mark.asyncio
    async def test_store_perception_maintains_consistency(self, memory_with_fake_chroma):
        """После store_perception in-memory и Chroma содержат один и тот же engram."""
        mem, fake_client = memory_with_fake_chroma

        # Мокаем Chroma query для поиска похожих (нет похожих)
        fake_client.collections["episodic"].query = MagicMock(
            return_value={"ids": [[]], "distances": [[]]}
        )

        # Store
        await mem.store_perception("test perception", metadata={})

        # In-memory должен содержать engram
        assert len(mem.engrams) >= 1

        # Chroma тоже
        assert fake_client.collections["episodic"].count() >= 1

        # IDs должны совпадать
        in_memory_ids = set(mem.engrams.keys())
        chroma_ids = set(fake_client.collections["episodic"]._store.keys())
        # Все in-memory IDs должны быть в Chroma
        assert in_memory_ids.issubset(chroma_ids)
