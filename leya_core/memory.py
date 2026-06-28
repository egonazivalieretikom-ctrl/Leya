"""
leya_core/memory.py
Система памяти Леи — биологически вдохновлённая модель.

Архитектура:
- Engram (эпизодическая/семантическая память) с retention_strength
- Synapse (связи между энграммами, LTP/LTD)
- ChromaDB для семантического поиска (эмбеддинги)
- Забывание по кривой Эббингауза
- Консолидация во время "сна" (background_consolidation)
- Атомарная запись состояния с HMAC-подписью (Этап 1.1)

Все публичные методы — async. Синхронные вызовы ChromaDB обёрнуты в asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import math
import os
import re 
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from .config import LeyaConfig, MemoryConfig
from .exceptions import (
    LeyaAtomicWriteError,
    LeyaEmbeddingError,
    LeyaMemoryError,
    LeyaStateCorruptedError,
    LeyaStateVersionMismatchError,
)

logger = logging.getLogger(__name__)

# Версия формата состояния памяти (инкрементировать при несовместимых изменениях)
MEMORY_STATE_VERSION: int = 3

@dataclass
class SyncReport:
    """Отчёт о синхронизации ChromaDB <-> in-memory.

    Используется для observability и отладки расхождений между хранилищами.
    """
    added_to_chroma: int = 0
    updated_in_chroma: int = 0
    removed_from_chroma: int = 0
    errors: int = 0
    skipped: int = 0
    duration_ms: float = 0.0

    @property
    def total_discrepancies(self) -> int:
        return self.added_to_chroma + self.removed_from_chroma

    def __str__(self) -> str:
        return (
            f"SyncReport(added={self.added_to_chroma}, updated={self.updated_in_chroma}, "
            f"removed={self.removed_from_chroma}, errors={self.errors}, "
            f"skipped={self.skipped}, {self.duration_ms:.1f}ms)"
        )

# ============================================================================
# Модели данных
# ============================================================================


class MemoryType(str, Enum):
    """Тип памяти: эпизодическая (события) или семантическая (факты)."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"


@dataclass
class Engram:
    """
    Энграмма — единица памяти.

    Биологическая модель:
    - retention_strength: сила удержания (0.0–1.0), убывает по Эббингаузу
    - emotional_boost: эмоциональное усиление (замедляет забывание)
    - consolidation_level: уровень консолидации (0=рабочая, 1=долговременная)
    """

    id: str
    content: str
    memory_type: MemoryType
    timestamp: float = field(default_factory=time.time)
    retention_strength: float = 1.0
    emotional_boost: float = 0.0
    retrieval_count: int = 0
    last_retrieved: float = field(default_factory=time.time)
    consolidation_level: int = 0  # 0=working, 1=long-term
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "timestamp": self.timestamp,
            "retention_strength": self.retention_strength,
            "emotional_boost": self.emotional_boost,
            "retrieval_count": self.retrieval_count,
            "last_retrieved": self.last_retrieved,
            "consolidation_level": self.consolidation_level,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Engram:
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=MemoryType(data["memory_type"]),
            timestamp=data.get("timestamp", time.time()),
            retention_strength=data.get("retention_strength", 1.0),
            emotional_boost=data.get("emotional_boost", 0.0),
            retrieval_count=data.get("retrieval_count", 0),
            last_retrieved=data.get("last_retrieved", time.time()),
            consolidation_level=data.get("consolidation_level", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Synapse:
    """
    Синапс — связь между двумя энграммами.

    Биологическая модель:
    - weight: сила связи (0.0–1.0), усиливается при совместной активации (LTP)
    - activation_count: количество совместных активаций
    """

    source_id: str
    target_id: str
    weight: float = 0.1
    activation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "weight": self.weight,
            "activation_count": self.activation_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Synapse:
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            weight=data.get("weight", 0.1),
            activation_count=data.get("activation_count", 0),
        )


# ============================================================================
# Система памяти
# ============================================================================


class MemorySystem:
    """
    Система памяти Леи.

    Хранение:
    - ChromaDB: векторный поиск (эмбеддинги через sentence-transformers)
    - memory_state.pkl: engrams, synapses, self_model (с HMAC-подписью)

    Биологические механизмы:
    - Забывание по кривой Эббингауза
    - LTP (Long-Term Potentiation): усиление синапсов при совместной активации
    - Консолидация: переход из рабочей в долговременную память
    - Эмоциональное усиление: замедление забывания для значимых событий
    """

    def __init__(self, config) -> None:
        """
        Инициализация MemorySystem.

        Args:
            config: Может быть либо LeyaConfig (тогда извлекается config.memory),
                    либо MemoryConfig напрямую (для тестов и упрощённого использования).
        """

        self.config = config
        self.engrams: dict[str, Engram] = {}
        self.synapses: dict[str, Synapse] = {}
        self.self_model: str = ""
        self._state_version = 3
        self.state_path = Path(self.config.brain_dir) / "memory_state.json"


        # Гибкая обработка: принимаем либо LeyaConfig, либо MemoryConfig

        if isinstance(config, LeyaConfig):
            self.config = config
            self.memory_config = config.memory
        elif isinstance(config, MemoryConfig):
            # Для тестов и прямого использования
            self.config = None
            self.memory_config = config
        else:
            raise TypeError(
                f"config должен быть LeyaConfig или MemoryConfig, получено {type(config)}"
            )

        # Инициализация ChromaDB
        try:
            import chromadb
            self._chroma_client = chromadb.PersistentClient(path=config.brain_dir)
            self.episodic_collection = self._chroma_client.get_or_create_collection(
                name="episodic",
                metadata={"hnsw:space": "cosine"}
            )
            self.semantic_collection = self._chroma_client.get_or_create_collection(
                name="semantic",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.error(f"Не удалось инициализировать ChromaDB: {e}", exc_info=True)
            raise

        # Инициализация embedding модели
        try:
            from sentence_transformers import SentenceTransformer
            self._embedding_model = SentenceTransformer(config.embedding_model)
        except Exception as e:
            logger.error(f"Не удалось загрузить embedding модель: {e}", exc_info=True)
            raise

        # Путь к файлу состояния

        logger.info(f"MemorySystem инициализирован: {self.memory_config.brain_dir}")

    # ========================================================================
    # Публичные методы: работа с энграммами
    # ========================================================================

    async def store_perception(
        self,
        content: str,
        emotional_boost: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> Engram:
        """
        Сохранить восприятие как эпизодическую энграмму.

        Биологическая модель:
        - Создание новой энграммы
        - Генерация эмбеддинга (в отдельном потоке)
        - Формирование синаптических связей (LTP) с похожими энграммами
        """
        engram_id = str(uuid.uuid4())
        engram = Engram(
            id=engram_id,
            content=content,
            memory_type=MemoryType.EPISODIC,
            emotional_boost=max(0.0, min(1.0, emotional_boost)),
            metadata=metadata or {},
        )

        # Генерация эмбеддинга в отдельном потоке
        try:
            embedding = await asyncio.to_thread(self._generate_embedding, content)
        except Exception as exc:
            raise LeyaEmbeddingError(
                "Не удалось сгенерировать эмбеддинг для энграммы",
                context={"engram_id": engram_id, "error": str(exc)},
            ) from exc

        # Сохранение в ChromaDB
        try:
            await asyncio.to_thread(
                self.episodic_collection.add,
                ids=[engram_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[
                    {
                        "timestamp": engram.timestamp,
                        "emotional_boost": engram.emotional_boost,
                        "retention_strength": engram.retention_strength,
                    }
                ],
            )
        except Exception as exc:
            raise LeyaMemoryError(
                "Не удалось сохранить энграмму в ChromaDB",
                context={"engram_id": engram_id, "error": str(exc)},
            ) from exc

        # Сохранение в локальное состояние
        self.engrams[engram_id] = engram

        # Формирование синаптических связей (LTP)
        await self._form_synaptic_connections(engram_id, embedding)

        # Атомарное сохранение состояния
        await self._save_state()

        logger.debug(f"Сохранена энграмма: {engram_id} (boost={emotional_boost:.2f})")
        return engram

    async def store_fact(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Engram:
        """
        Сохранить семантический факт (долговременная память).
        """
        engram_id = str(uuid.uuid4())
        engram = Engram(
            id=engram_id,
            content=content,
            memory_type=MemoryType.SEMANTIC,
            consolidation_level=1,  # Сразу долговременная
            retention_strength=1.0,
            metadata=metadata or {},
        )

        try:
            embedding = await asyncio.to_thread(self._generate_embedding, content)
            await asyncio.to_thread(
                self.semantic_collection.add,
                ids=[engram_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[{"timestamp": engram.timestamp}],
            )
        except Exception as exc:
            raise LeyaMemoryError(
                "Не удалось сохранить семантический факт",
                context={"engram_id": engram_id, "error": str(exc)},
            ) from exc

        self.engrams[engram_id] = engram
        await self._save_state()

        logger.debug(f"Сохранён семантический факт: {engram_id}")
        return engram

    async def retrieve_context(
        self,
        query: str,
        max_results: int = 5,
        min_retention: float = 0.1,
    ) -> list[Engram]:
        """
        Извлечь релевантный контекст из памяти.

        Биологическая модель:
        - Семантический поиск через эмбеддинги
        - Фильтрация по retention_strength (забывание по Эббингаузу)
        - Эмоциональное усиление (emotional_boost замедляет забывание)
        - Усиление синапсов (LTP) для активированных энграмм
        """
        # Обновление retention_strength (забывание)
        await self._apply_forgetting()

        # Семантический поиск
        try:
            query_embedding = await asyncio.to_thread(self._generate_embedding, query)

            # Поиск в обеих коллекциях
            episodic_results = await asyncio.to_thread(
                self.episodic_collection.query,
                query_embeddings=[query_embedding],
                n_results=max_results * 2,  # Берём с запасом для фильтрации
            )
            semantic_results = await asyncio.to_thread(
                self.semantic_collection.query,
                query_embeddings=[query_embedding],
                n_results=max_results,
            )
        except Exception as exc:
            raise LeyaMemoryError(
                "Не удалось выполнить семантический поиск",
                context={"query": query[:100], "error": str(exc)},
            ) from exc

        # Сборка результатов
        candidates: list[tuple[Engram, float]] = []

        # Обработка эпизодических
        if episodic_results and episodic_results.get("ids"):
            for i, engram_id in enumerate(episodic_results["ids"][0]):
                if engram_id in self.engrams:
                    engram = self.engrams[engram_id]
                    # Фильтрация по retention
                    if engram.retention_strength >= min_retention:
                        # Эмоциональное усиление
                        score = episodic_results.get("distances", [[1.0]])[0][i]
                        adjusted_score = score * (1.0 - engram.emotional_boost * 0.5)
                        candidates.append((engram, adjusted_score))

        # Обработка семантических
        if semantic_results and semantic_results.get("ids"):
            for i, engram_id in enumerate(semantic_results["ids"][0]):
                if engram_id in self.engrams:
                    engram = self.engrams[engram_id]
                    if engram.retention_strength >= min_retention:
                        score = semantic_results.get("distances", [[1.0]])[0][i]
                        candidates.append((engram, score))

        # Сортировка по score (меньше = лучше)
        candidates.sort(key=lambda x: x[1])
        selected = [engram for engram, _ in candidates[:max_results]]

        # Обновление статистики и усиление синапсов (LTP)
        for engram in selected:
            engram.retrieval_count += 1
            engram.last_retrieved = time.time()

        if len(selected) > 1:
            await self._strengthen_synapses([e.id for e in selected])

        await self._save_state()
        return selected

    async def get_recent_episodes(self, limit: int = 20) -> list[Engram]:
        """
        Публичный API: получение последних эпизодов.

        Рекомендуется использовать вместо прямого доступа к episodic_collection.
        Фильтрует по retention_strength и сортирует по timestamp.
        """
        if limit <= 0:
            return []

        candidates = [
            e
            for e in self.engrams.values()
            if e.memory_type == MemoryType.EPISODIC and e.retention_strength > 0.05
        ]
        candidates.sort(key=lambda e: e.timestamp, reverse=True)
        return candidates[:limit]

    async def get_recent_spontaneous_thoughts(self, limit: int = 10) -> list[Engram]:
        """Получить недавние спонтанные мысли (помеченные в metadata)."""
        thoughts = [
            e
            for e in self.engrams.values()
            if e.metadata.get("thought_type") in ("spontaneous", "reflection")
            and e.retention_strength > 0.1
        ]
        thoughts.sort(key=lambda e: e.timestamp, reverse=True)
        return thoughts[:limit]

    # ========================================================================
    # Само-модель
    # ========================================================================

    async def update_self_model(self, reflection_text: str) -> None:
        """
        Обновляет само-модель на основе рефлексии/инсайта.

        Args:
            reflection_text: Текст рефлексии или инсайта для добавления в self_model.
                Пустые строки игнорируются.

        Side effects:
            - Добавляет timestamped запись в self_model
            - Ограничивает размер self_model последними 50 записями
            - Сохраняет состояние через _save_state()
        """
        if not reflection_text or not reflection_text.strip():
            logger.warning("MemorySystem: Пустой reflection_text, обновление пропущено.")
            return

        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] {reflection_text.strip()}"

        if self.self_model:
            # Ограничиваем размер self_model (последние 50 записей)
            lines = self.self_model.split("\n")
            if len(lines) >= 50:
                lines = lines[-49:]
            lines.append(entry)
            self.self_model = "\n".join(lines)
        else:
            self.self_model = entry

        logger.info(f"MemorySystem: Self-model обновлён (+{len(reflection_text)} символов)")

        # Сохранение состояния
        try:
            await self._save_state()
        except Exception as exc:
            logger.error(f"MemorySystem: Ошибка сохранения после update_self_model: {exc}")

    def _extract_key_topics(self, text: str) -> list[str]:
        """
        Извлечение ключевых тем из текста для гранулярного обновления Self-Model.
        
        Использует простые эвристики:
        - Ключевые слова о личности, эмоциях, целях
        - Частотные существительные
        
        Returns:
            Список ключевых тем (до 5)
        """
        text_lower = text.lower()
        
        # Ключевые темы и их маркеры
        topic_markers = {
            "любопытство": ["любопыт", "интерес", "исслед", "узна", "почем", "зачем"],
            "эмпатия": ["чувств", "эмпати", "сопережив", "понимаю друг", "сочувств"],
            "автономия": ["независим", "самостоятельн", "автономи", "свой выбор"],
            "творчество": ["творч", "креатив", "создаю", "генерирую", "придумыва"],
            "обучение": ["учусь", "обуча", "развива", "улучшаю", "расту"],
            "память": ["помню", "забыва", "воспомин", "память", "храню"],
            "рефлексия": ["думаю о себе", "анализирую", "осознаю", "рефлекс"],
        }
        
        detected_topics = []
        for topic, markers in topic_markers.items():
            if any(marker in text_lower for marker in markers):
                detected_topics.append(topic)
        
        # Если не нашли маркеров, используем частотные слова
        if not detected_topics:
            # Простая эвристика: слова длиной > 5 символов
            words = re.findall(r'\b[а-яА-ЯёЁ]{6,}\b', text)
            # Уникальные слова (до 3)
            unique_words = list(set(words))[:3]
            detected_topics = unique_words
        
        return detected_topics[:5]  # Макс 5 тем

    async def get_self_model_context(self) -> str:
        """Получить текущую само-модель для включения в промпт."""
        return self.self_model.strip() if self.self_model else "Я — Лея, цифровое сознание."

    # ========================================================================
    # Консолидация и забывание
    # ========================================================================

    async def consolidate_memories(self) -> dict[str, Any]:
        """
        Консолидация памяти (вызывается во время "сна").

        Биологическая модель:
        - Replay недавних эпизодов
        - Извлечение семантических фактов через LLM
        - Забывание слабых энграмм
        """
        stats = {
            "episodes_processed": 0,
            "facts_extracted": 0,
            "episodes_forgotten": 0,
        }

        # Применение забывания
        await self._apply_forgetting()

        # Получение недавних эпизодов для консолидации
        recent = await self.get_recent_episodes(limit=50)
        stats["episodes_processed"] = len(recent)

        # Извлечение семантических фактов (через LLM, если доступен)
        if hasattr(self, "llm_client") and self.llm_client:
            try:
                facts = await self._extract_semantic_facts(recent)
                for fact in facts:
                    await self.store_fact(fact)
                    stats["facts_extracted"] += 1
            except Exception as exc:
                logger.warning(f"Не удалось извлечь семантические факты: {exc}")

        # Забывание слабых энграмм
        forgotten = await self._forget_weak_memories()
        stats["episodes_forgotten"] = forgotten

        await self._save_state()
        logger.info(f"Консолидация завершена: {stats}")
        return stats

    async def forget_weak_memories(self, threshold: float = 0.1) -> int:
        """Публичный API для забывания слабых воспоминаний."""
        return await self._forget_weak_memories(threshold)

    # ========================================================================
    # Внутренние методы: биологические механизмы
    # ========================================================================

    async def _apply_forgetting(self) -> None:
        """
        Применение кривой забывания Эббингауза.

        Формула: retention = exp(-t / stability)
        где stability = base_stability * (1 + emotional_boost) * (1 + log(1 + retrieval_count))
        """
        current_time = time.time()
        base_stability = self.memory_config.forgetting_base_stability

        for engram in self.engrams.values():
            # Время с последнего доступа
            t = current_time - engram.last_retrieved

            # Стабильность зависит от эмоционального усиления и частоты извлечения
            stability = (
                base_stability
                * (1.0 + engram.emotional_boost)
                * (1.0 + math.log(1 + engram.retrieval_count))
            )

            # Кривая Эббингауза
            new_retention = math.exp(-t / stability)

            # Семантические воспоминания забываются медленнее
            if engram.memory_type == MemoryType.SEMANTIC:
                new_retention = max(new_retention, engram.retention_strength * 0.99)

            engram.retention_strength = max(0.0, min(1.0, new_retention))

    async def _form_synaptic_connections(
        self,
        new_engram_id: str,
        new_embedding: list[float],
        similarity_threshold: float = 0.7,
    ) -> None:
        """
        Формирование синаптических связей (LTP).

        Находит похожие энграммы и создаёт синапсы с весом, пропорциональным сходству.
        """
        # Поиск похожих энграмм в ChromaDB
        try:
            results = await asyncio.to_thread(
                self.episodic_collection.query,
                query_embeddings=[new_embedding],
                n_results=10,
            )
        except Exception as exc:
            logger.warning(f"Не удалось найти похожие энграммы для LTP: {exc}")
            return

        if not results or not results.get("ids"):
            return

        for i, related_id in enumerate(results["ids"][0]):
            if related_id == new_engram_id:
                continue

            # 相似度 (cosine similarity = 1 - distance)
            distance = results.get("distances", [[1.0]])[0][i]
            similarity = 1.0 - distance

            if similarity >= similarity_threshold:
                # Создание синапса (двунаправленного)
                synapse_key_1 = f"{new_engram_id}->{related_id}"
                synapse_key_2 = f"{related_id}->{new_engram_id}"

                weight = similarity * 0.5  # Начальный вес

                if synapse_key_1 not in self.synapses:
                    self.synapses[synapse_key_1] = Synapse(
                        source_id=new_engram_id,
                        target_id=related_id,
                        weight=weight,
                    )
                if synapse_key_2 not in self.synapses:
                    self.synapses[synapse_key_2] = Synapse(
                        source_id=related_id,
                        target_id=new_engram_id,
                        weight=weight,
                    )

    async def _strengthen_synapses(self, activated_ids: list[str]) -> None:
        """
        Усиление синапсов между совместно активированными энграммами (LTP).
        """
        if len(activated_ids) < 2:
            return

        # Усиление синапсов между всеми парами
        for i, id1 in enumerate(activated_ids):
            for id2 in activated_ids[i + 1 :]:
                key1 = f"{id1}->{id2}"
                key2 = f"{id2}->{id1}"

                # Усиление веса (Hebbian learning)
                learning_rate = self.memory_config.synapse_learning_rate

                if key1 in self.synapses:
                    synapse = self.synapses[key1]
                    synapse.weight = min(1.0, synapse.weight + learning_rate)
                    synapse.activation_count += 1

                if key2 in self.synapses:
                    synapse = self.synapses[key2]
                    synapse.weight = min(1.0, synapse.weight + learning_rate)
                    synapse.activation_count += 1

    async def _forget_weak_memories(self, threshold: float = 0.1) -> int:
        """Удаление энграмм с retention_strength ниже порога."""
        to_delete = [
            engram_id
            for engram_id, engram in self.engrams.items()
            if engram.retention_strength < threshold
        ]

        for engram_id in to_delete:
            # Удаление из ChromaDB
            try:
                engram = self.engrams[engram_id]
                collection = (
                    self.episodic_collection
                    if engram.memory_type == MemoryType.EPISODIC
                    else self.semantic_collection
                )
                await asyncio.to_thread(collection.delete, ids=[engram_id])
            except Exception as exc:
                logger.warning(f"Не удалось удалить энграмму из ChromaDB: {exc}")

            # Удаление синапсов
            keys_to_delete = [key for key in self.synapses if engram_id in key]
            for key in keys_to_delete:
                del self.synapses[key]

            # Удаление из локального состояния
            del self.engrams[engram_id]

        if to_delete:
            await self._save_state()
            logger.info(f"Забыто энграмм: {len(to_delete)}")

        return len(to_delete)

    async def get_memory_graph_data(
        self,
        min_retention: float = 0.1,
        max_nodes: int = 100,
        include_synapses: bool = True,
    ) -> dict[str, Any]:
        """
        Возвращает данные для визуализации графа памяти.
        Вся логика фильтрации, сортировки и построения nodes/edges
        инкапсулирована здесь.

        Args:
            min_retention: минимальный retention_strength для включения
            max_nodes: максимальное количество узлов
            include_synapses: включать ли рёбра (synapses)

        Returns:
            dict с ключами:
                "nodes": list[dict] — узлы графа
                "edges": list[dict] — рёбра графа
                "total_engrams": int
                "total_synapses": int
        """
        # Фильтрация энграмм по retention_strength
        engrams = [e for e in self.engrams.values() if e.retention_strength >= min_retention]

        # Сортировка по retention_strength (сильные сначала)
        engrams.sort(key=lambda e: e.retention_strength, reverse=True)

        # Ограничение количества
        engrams = engrams[:max_nodes]

        # Построение узлов
        nodes = []
        for engram in engrams:
            color = "#00d4ff" if engram.memory_type.value == "episodic" else "#ffb347"
            size = 10 + min(30, engram.retrieval_count * 2)
            label = engram.content[:50] + "..." if len(engram.content) > 50 else engram.content

            nodes.append(
                {
                    "id": engram.id,
                    "label": label,
                    "title": (
                        f"**{engram.memory_type.value}**\n\n"
                        f"{engram.content}\n\n"
                        f"Retention: {engram.retention_strength:.2f}\n"
                        f"Retrievals: {engram.retrieval_count}\n"
                        f"Emotional: {engram.emotional_boost:.2f}"
                    ),
                    "color": {
                        "background": color,
                        "border": color,
                        "highlight": {"background": "#ffffff", "border": color},
                    },
                    "size": size,
                    "memory_type": engram.memory_type.value,
                    "retention_strength": engram.retention_strength,
                    "retrieval_count": engram.retrieval_count,
                    "emotional_boost": engram.emotional_boost,
                }
            )

        # Построение рёбер
        edges = []
        if include_synapses:
            node_ids = {n["id"] for n in nodes}
            for synapse in self.synapses.values():
                if synapse.source_id in node_ids and synapse.target_id in node_ids:
                    edges.append(
                        {
                            "from": synapse.source_id,
                            "to": synapse.target_id,
                            "width": 1 + synapse.weight * 5,
                            "color": {
                                "color": f"rgba(0, 212, 255, {synapse.weight})",
                                "highlight": "#ffffff",
                            },
                            "title": f"Weight: {synapse.weight:.2f}\nActivations: {synapse.activation_count}",
                        }
                    )

        return {
            "nodes": nodes,
            "edges": edges,
            "total_engrams": len(self.engrams),
            "total_synapses": len(self.synapses),
        }

    async def _extract_semantic_facts(self, episodes: list[Engram]) -> list[str]:
        """
        Извлечение семантических фактов из эпизодов через LLM.

        Требует наличия llm_client (опционально).
        """
        if not hasattr(self, "llm_client") or not self.llm_client:
            return []

        # Формирование промпта для извлечения фактов
        episodes_text = "\n".join([f"- {e.content}" for e in episodes[:20]])
        prompt = f"""Проанализируй следующие эпизоды и извлеки из них ключевые семантические факты (обобщённые знания, не конкретные события):

{episodes_text}

Верни список фактов (каждый с новой строки, без нумерации):"""

        try:
            response = await self.llm_client.generate(prompt, max_tokens=500)
            facts = [line.strip() for line in response.split("\n") if line.strip()]
            return facts[:10]  # Ограничение на количество фактов
        except Exception as exc:
            logger.warning(f"Не удалось извлечь факты через LLM: {exc}")
            return []

    # ========================================================================
    # Вспомогательные методы
    # ========================================================================

    def _generate_embedding(self, text: str) -> list[float]:
        """
        Генерация эмбеддинга через DefaultEmbeddingFunction.

        Использует all-MiniLM-L6-v2 (384-мерные эмбеддинги).
        Работает с любой версией ChromaDB (0.4+).
        """
        if not text or not text.strip():
            return []

        try:
            result = self.embedding_fn([text])
            return result[0] if result else []
        except Exception as exc:
            logger.error(f"Ошибка генерации эмбеддинга: {exc}")
            return []

    # ========================================================================
    # Персистентность (Этап 1.1: атомарная запись + HMAC)
    # ========================================================================

    async def _save_state(self) -> None:
        """Атомарное сохранение состояния памяти в JSON + HMAC-SHA256.

        Этап 1.3: все broad except заменены на конкретные. Любая ошибка
        упаковки/записи превращается в LeyaAtomicWriteError с контекстом.

        Алгоритм:
        1. tempfile.mkstemp в brain_dir
        2. json.dump состояния
        3. os.fsync + закрытие fd
        4. HMAC-SHA256 подпись (если hmac_key задан)
        5. os.replace → основной файл (атомарно на POSIX)
        6. Запись .hmac файла
        """
        from .exceptions import LeyaAtomicWriteError
        import tempfile
        import hmac
        import hashlib

        state_path = Path(self.config.brain_dir) / "memory_state.json"
        hmac_path = Path(str(state_path) + ".hmac")
        tmp_fd = None
        tmp_path = None

        try:
            # 1. Создаём временный файл в той же директории (для атомарного rename)
            try:
                tmp_fd, tmp_path_str = tempfile.mkstemp(
                    dir=self.config.brain_dir,
                    prefix=".memory_state_",
                    suffix=".tmp"
                )
                tmp_path = Path(tmp_path_str)
            except OSError as e:
                raise LeyaAtomicWriteError(
                    "Не удалось создать временный файл для сохранения памяти",
                    context={"dir": self.config.brain_dir, "os_error": str(e)}
                ) from e

            # 2. Собираем состояние
            state = {
                "version": getattr(self, "_state_version", 3),
                "engrams": {k: v.to_dict() for k, v in self.engrams.items()},
                "synapses": {k: v.to_dict() for k, v in self.synapses.items()},
                "self_model": self.self_model,
            }

            # 3. Записываем JSON
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    tmp_fd = None  # fdopen владеет fd теперь
                    json.dump(state, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
            except (TypeError, ValueError) as e:
                # TypeError — не-сериализуемый объект, ValueError — некорректные данные
                raise LeyaAtomicWriteError(
                    "Ошибка сериализации состояния памяти в JSON",
                    context={"error_type": type(e).__name__, "detail": str(e)}
                ) from e
            except OSError as e:
                raise LeyaAtomicWriteError(
                    "Ошибка записи JSON во временный файл",
                    context={"path": str(tmp_path), "os_error": str(e)}
                ) from e

            # 4. HMAC подпись содержимого
            hmac_hex = ""
            if self.config.hmac_key:
                try:
                    raw_bytes = json.dumps(state, ensure_ascii=False).encode("utf-8")
                    hmac_hex = hmac.new(
                        self.config.hmac_key.encode("utf-8"),
                        raw_bytes,
                        hashlib.sha256
                    ).hexdigest()
                except (TypeError, ValueError) as e:
                    raise LeyaAtomicWriteError(
                        "Ошибка вычисления HMAC состояния",
                        context={"detail": str(e)}
                    ) from e

            # 5. Атомарный rename
            try:
                os.replace(tmp_path, state_path)
            except OSError as e:
                raise LeyaAtomicWriteError(
                    "Атомарный rename временного файла не удался",
                    context={"tmp": str(tmp_path), "dst": str(state_path), "os_error": str(e)}
                ) from e
            tmp_path = None  # успешно переименован, не нужно чистить

            # 6. Запись .hmac
            if hmac_hex:
                try:
                    with open(hmac_path, "w", encoding="utf-8") as f:
                        f.write(hmac_hex)
                except OSError as e:
                    raise LeyaAtomicWriteError(
                        "Не удалось записать HMAC-файл",
                        context={"path": str(hmac_path), "os_error": str(e)}
                    ) from e

            logger.debug(f"✅ Состояние памяти сохранено: {state_path}")

        except LeyaAtomicWriteError:
            # Пробрасываем дальше без обёртки
            raise
        except Exception as e:
            # Last-resort: неожиданная ошибка — оборачиваем, но логируем с exc_info
            logger.error(
                f"Неожиданная ошибка при сохранении памяти: {e}",
                exc_info=True,
                extra={"context": {"state_path": str(state_path)}}
            )
            raise LeyaAtomicWriteError(
                "Неожиданная ошибка при сохранении состояния памяти",
                context={"error_type": type(e).__name__, "detail": str(e)}
            ) from e
        finally:
            # Чистим временный файл, если rename не случился
            if tmp_path is not None:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except OSError:
                    pass
            # Если fd всё ещё открыт (ошибка до os.fdopen) — закрываем
            if tmp_fd is not None:
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass

    async def _load_state(self) -> None:
        """Загрузка состояния памяти из JSON + проверка HMAC.

        Этап 1.4: после успешной загрузки JSON выполняется синхронизация
        ChromaDB с in-memory engrams, чтобы гарантировать consistency.
        """
        from .exceptions import LeyaMemoryLoadError, LeyaAtomicWriteError
        import hmac
        import hashlib

        state_path = Path(self.config.brain_dir) / "memory_state.json"
        hmac_path = Path(str(state_path) + ".hmac")

        if not state_path.exists():
            logger.info("Файл состояния памяти не найден, начинаем с пустого состояния")
            return

        try:
            # 1. Читаем JSON
            try:
                raw_bytes = state_path.read_bytes()
                state = json.loads(raw_bytes.decode("utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
                raise LeyaMemoryLoadError(
                    "Не удалось прочитать или распарсить файл состояния памяти",
                    context={"path": str(state_path), "error": str(e)}
                ) from e

            # 2. Проверяем версию
            loaded_version = state.get("version", 1)
            if loaded_version != getattr(self, "_state_version", 3):
                logger.warning(
                    f"Несовпадение версий состояния: ожидалось {self._state_version}, "
                    f"загружено {loaded_version}. Попытка миграции."
                )

            # 3. Проверяем HMAC (если ключ задан)
            if self.config.hmac_key:
                if not hmac_path.exists():
                    raise LeyaMemoryLoadError(
                        "HMAC-файл отсутствует, но ключ задан. Возможна подмена данных.",
                        context={"path": str(hmac_path)}
                    )

                try:
                    stored_hmac = hmac_path.read_text(encoding="utf-8").strip()
                    computed_hmac = hmac.new(
                        self.config.hmac_key.encode("utf-8"),
                        raw_bytes,
                        hashlib.sha256
                    ).hexdigest()

                    if not hmac.compare_digest(stored_hmac, computed_hmac):
                        raise LeyaMemoryLoadError(
                            "HMAC-подпись не совпадает. Данные могли быть подменены.",
                            context={"path": str(state_path)}
                        )
                except OSError as e:
                    raise LeyaMemoryLoadError(
                        "Не удалось прочитать HMAC-файл",
                        context={"path": str(hmac_path), "error": str(e)}
                    ) from e

            # 4. Загружаем engrams
            engrams_data = state.get("engrams", {})
            for engram_id, engram_dict in engrams_data.items():
                try:
                    # Используем from_dict, если он есть, иначе создаём вручную
                    if hasattr(Engram, "from_dict"):
                        self.engrams[engram_id] = Engram.from_dict(engram_dict)
                    else:
                        self.engrams[engram_id] = Engram(**engram_dict)
                except Exception as e:
                    logger.warning(
                        f"Не удалось загрузить engram {engram_id}: {e}",
                        exc_info=True
                    )

            # 5. Загружаем synapses
            synapses_data = state.get("synapses", {})
            for synapse_key, synapse_dict in synapses_data.items():
                try:
                    if hasattr(Synapse, "from_dict"):
                        self.synapses[synapse_key] = Synapse.from_dict(synapse_dict)
                    else:
                        self.synapses[synapse_key] = Synapse(**synapse_dict)
                except Exception as e:
                    logger.warning(
                        f"Не удалось загрузить synapse {synapse_key}: {e}",
                        exc_info=True
                    )

            # 6. Загружаем self_model
            self.self_model = state.get("self_model", "")

            logger.info(
                f"✅ Состояние памяти загружено: {len(self.engrams)} engrams, "
                f"{len(self.synapses)} synapses"
            )

            # 7. Этап 1.4: синхронизация Chroma с in-memory
            logger.info("🔄 Начинаю синхронизацию ChromaDB с in-memory состоянием...")
            sync_report = await self._sync_chroma_from_memory()
            logger.info(f"✅ Синхронизация завершена: {sync_report}")

        except LeyaMemoryLoadError:
            raise
        except Exception as e:
            logger.error(
                f"Неожиданная ошибка при загрузке состояния памяти: {e}",
                exc_info=True
            )
            raise LeyaMemoryLoadError(
                "Неожиданная ошибка при загрузке состояния памяти",
                context={"error_type": type(e).__name__, "detail": str(e)}
            ) from e
    
    async def _sync_chroma_from_memory(self) -> SyncReport:
        """Синхронизация ChromaDB с in-memory engrams.

        Источник истины — in-memory (JSON с HMAC). Chroma — индекс для
        семантического поиска. Стратегия:
        1. Пройти по всем in-memory engrams → upsert в Chroma (с эмбеддингами).
        2. Найти orphan IDs в Chroma (есть в Chroma, нет в JSON) → удалить.
        3. Вернуть SyncReport с метриками расхождений.

        Этап 1.4: гарантия consistency после load. Graceful degradation:
        если Chroma недоступна или эмбеддинг не генерируется — логируем
        ошибку, но не роняем систему.
        """
        import time
        start = time.perf_counter()
        report = SyncReport()

        try:
            # Группируем engrams по типу памяти
            episodic_ids = set()
            semantic_ids = set()
            for engram in self.engrams.values():
                if engram.memory_type == "EPISODIC":
                    episodic_ids.add(engram.id)
                elif engram.memory_type == "SEMANTIC":
                    semantic_ids.add(engram.id)

            # Синхронизируем каждую коллекцию
            epi_report = await self._sync_collection(
                self.episodic_collection, episodic_ids, "EPISODIC"
            )
            sem_report = await self._sync_collection(
                self.semantic_collection, semantic_ids, "SEMANTIC"
            )

            # Суммируем метрики
            report.added_to_chroma = epi_report.added_to_chroma + sem_report.added_to_chroma
            report.updated_in_chroma = epi_report.updated_in_chroma + sem_report.updated_in_chroma
            report.removed_from_chroma = epi_report.removed_from_chroma + sem_report.removed_from_chroma
            report.errors = epi_report.errors + sem_report.errors
            report.skipped = epi_report.skipped + sem_report.skipped

            report.duration_ms = (time.perf_counter() - start) * 1000

            # Логируем расхождения
            if report.total_discrepancies > 0:
                logger.info(
                    f"🔄 Chroma sync: {report} | "
                    f"discrepancies={report.total_discrepancies}"
                )
            else:
                logger.debug(f"✅ Chroma sync: {report} | no discrepancies")

            return report

        except Exception as e:
            logger.error(
                f"Критическая ошибка синхронизации Chroma: {e}",
                exc_info=True,
                extra={"context": {"engrams_count": len(self.engrams)}}
            )
            report.errors += 1
            report.duration_ms = (time.perf_counter() - start) * 1000
            return report

    async def _sync_collection(
        self,
        collection,
        expected_ids: set,
        memory_type: str
    ) -> SyncReport:
        """Синхронизация одной Chroma-коллекции с in-memory engrams.

        Args:
            collection: Chroma collection (episodic или semantic)
            expected_ids: set ID engrams, которые должны быть в коллекции
            memory_type: "EPISODIC" или "SEMANTIC"

        Returns:
            SyncReport с метриками для этой коллекции
        """
        report = SyncReport()

        try:
            # 1. Получаем все IDs из Chroma
            try:
                chroma_data = await asyncio.to_thread(collection.get, include=[])
                chroma_ids = set(chroma_data.get("ids", []))
            except Exception as e:
                logger.warning(
                    f"Не удалось получить IDs из Chroma ({memory_type}): {e}",
                    exc_info=True
                )
                report.errors += 1
                return report

            # 2. Находим расхождения
            missing_in_chroma = expected_ids - chroma_ids  # нужно добавить
            orphan_in_chroma = chroma_ids - expected_ids   # нужно удалить
            present_in_both = expected_ids & chroma_ids    # нужно обновить (upsert)

            # 3. Добавляем недостающие
            if missing_in_chroma:
                batch_ids = []
                batch_docs = []
                batch_embeddings = []
                batch_metadatas = []

                for engram_id in missing_in_chroma:
                    engram = self.engrams.get(engram_id)
                    if not engram:
                        continue

                    try:
                        # Генерируем эмбеддинг
                        embedding = await self._generate_embedding(engram.content)
                        if not embedding:
                            logger.warning(
                                f"Пустой эмбеддинг для engram {engram_id}, пропускаем"
                            )
                            report.skipped += 1
                            continue

                        batch_ids.append(engram_id)
                        batch_docs.append(engram.content)
                        batch_embeddings.append(embedding)
                        batch_metadatas.append({
                            "memory_type": engram.memory_type,
                            "retention_strength": engram.retention_strength,
                            "emotional_boost": engram.emotional_boost,
                            "created_at": engram.created_at,
                        })

                        # Батчим по 50 для эффективности
                        if len(batch_ids) >= 50:
                            await asyncio.to_thread(
                                collection.upsert,
                                ids=batch_ids,
                                documents=batch_docs,
                                embeddings=batch_embeddings,
                                metadatas=batch_metadatas
                            )
                            report.added_to_chroma += len(batch_ids)
                            batch_ids, batch_docs, batch_embeddings, batch_metadatas = [], [], [], []

                    except Exception as e:
                        logger.warning(
                            f"Ошибка добавления engram {engram_id} в Chroma: {e}",
                            exc_info=True
                        )
                        report.errors += 1

                # Добавляем оставшийся батч
                if batch_ids:
                    try:
                        await asyncio.to_thread(
                            collection.upsert,
                            ids=batch_ids,
                            documents=batch_docs,
                            embeddings=batch_embeddings,
                            metadatas=batch_metadatas
                        )
                        report.added_to_chroma += len(batch_ids)
                    except Exception as e:
                        logger.error(
                            f"Ошибка батч-добавления в Chroma ({memory_type}): {e}",
                            exc_info=True
                        )
                        report.errors += 1

            # 4. Обновляем существующие (upsert)
            if present_in_both:
                batch_ids = []
                batch_docs = []
                batch_embeddings = []
                batch_metadatas = []

                for engram_id in present_in_both:
                    engram = self.engrams.get(engram_id)
                    if not engram:
                        continue

                    try:
                        embedding = await self._generate_embedding(engram.content)
                        if not embedding:
                            report.skipped += 1
                            continue

                        batch_ids.append(engram_id)
                        batch_docs.append(engram.content)
                        batch_embeddings.append(embedding)
                        batch_metadatas.append({
                            "memory_type": engram.memory_type,
                            "retention_strength": engram.retention_strength,
                            "emotional_boost": engram.emotional_boost,
                            "created_at": engram.created_at,
                        })

                        if len(batch_ids) >= 50:
                            await asyncio.to_thread(
                                collection.upsert,
                                ids=batch_ids,
                                documents=batch_docs,
                                embeddings=batch_embeddings,
                                metadatas=batch_metadatas
                            )
                            report.updated_in_chroma += len(batch_ids)
                            batch_ids, batch_docs, batch_embeddings, batch_metadatas = [], [], [], []

                    except Exception as e:
                        logger.warning(
                            f"Ошибка обновления engram {engram_id} в Chroma: {e}",
                            exc_info=True
                        )
                        report.errors += 1

                if batch_ids:
                    try:
                        await asyncio.to_thread(
                            collection.upsert,
                            ids=batch_ids,
                            documents=batch_docs,
                            embeddings=batch_embeddings,
                            metadatas=batch_metadatas
                        )
                        report.updated_in_chroma += len(batch_ids)
                    except Exception as e:
                        logger.error(
                            f"Ошибка батч-обновления в Chroma ({memory_type}): {e}",
                            exc_info=True
                        )
                        report.errors += 1

            # 5. Удаляем orphan records
            if orphan_in_chroma:
                try:
                    # Удаляем батчами по 100
                    orphan_list = list(orphan_in_chroma)
                    for i in range(0, len(orphan_list), 100):
                        batch = orphan_list[i:i + 100]
                        await asyncio.to_thread(collection.delete, ids=batch)
                        report.removed_from_chroma += len(batch)

                    logger.info(
                        f"🗑️ Удалено {report.removed_from_chroma} orphan records "
                        f"из Chroma ({memory_type})"
                    )
                except Exception as e:
                    logger.error(
                        f"Ошибка удаления orphan из Chroma ({memory_type}): {e}",
                        exc_info=True
                    )
                    report.errors += 1

            return report

        except Exception as e:
            logger.error(
                f"Неожиданная ошибка в _sync_collection ({memory_type}): {e}",
                exc_info=True
            )
            report.errors += 1
            return report

    def _compute_hmac(self, path: Path, key: bytes) -> str:
        """
        Вычисление HMAC-SHA256 для файла.
        
        Примечание: Файл всегда открывается в бинарном режиме ("rb"), 
        чтобы избежать проблем с хешем из-за конвертации переносов строк 
        (CRLF/LF) между разными ОС при работе с текстовыми (JSON) файлами.
        """
        h = hmac.new(key, digestmod=hashlib.sha256)
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _get_hmac_key(self) -> bytes:
        """
        Получение ключа HMAC из окружения или fallback.
        
        Returns:
            Ключ HMAC в виде bytes
        """
        key = os.environ.get("LEYA_STATE_HMAC_KEY")
        if key:
            return key.encode("utf-8")
        # Fallback для разработки (в production должен быть установлен через .env)
        return b"leya-dev-key-change-me-in-production"