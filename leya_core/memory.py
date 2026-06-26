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
import logging
import math
import os
import pickle
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
MEMORY_STATE_VERSION: int = 2


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
            self.chroma_client = chromadb.PersistentClient(
                path=self.memory_config.brain_dir,
                settings=Settings(anonymized_telemetry=False),
            )
            self.episodic_collection = self.chroma_client.get_or_create_collection(
                name="episodic_memory",
                metadata={"description": "Эпизодическая память Леи"},
            )
            self.semantic_collection = self.chroma_client.get_or_create_collection(
                name="semantic_memory",
                metadata={"description": "Семантическая память Леи"},
            )
            self.embedding_fn = DefaultEmbeddingFunction()

        except Exception as exc:
            raise LeyaMemoryError(
                "Не удалось инициализировать ChromaDB",
                context={"brain_dir": self.memory_config.brain_dir, "error": str(exc)},
            ) from exc

        # Состояние памяти
        self.engrams: dict[str, Engram] = {}
        self.synapses: dict[str, Synapse] = {}  # key: "source_id->target_id"
        self.self_model: str = ""

        # Путь к файлу состояния
        self.state_path = Path(self.memory_config.brain_dir) / "memory_state.pkl"

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
        top_k: int = 5,
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
                n_results=top_k * 2,  # Берём с запасом для фильтрации
            )
            semantic_results = await asyncio.to_thread(
                self.semantic_collection.query,
                query_embeddings=[query_embedding],
                n_results=top_k,
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
        selected = [engram for engram, _ in candidates[:top_k]]

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

    async def get_memory_graph_data(
        self,
        min_retention: float = 0.1,
        max_nodes: int = 100,
        include_synapses: bool = True,
    ) -> dict:
        """
        Возвращает данные для визуализации графа памяти (nodes + edges).
        Вся логика фильтрации, сортировки и форматирования инкапсулирована здесь.

        Args:
            min_retention: минимальный retention_strength для включения
            max_nodes: максимальное количество узлов
            include_synapses: включать ли рёбра (synapses)

        Returns:
            {
                "nodes": [...],
                "edges": [...],
                "total_engrams": int,
                "total_synapses": int,
            }
        """
        # 1. Фильтрация и сортировка engrams
        engrams = [
            e for e in self.engrams.values()
            if e.retention_strength >= min_retention
        ]
        engrams.sort(key=lambda e: e.retention_strength, reverse=True)
        engrams = engrams[:max_nodes]

        total_engrams = len(self.engrams)
        total_synapses = len(self.synapses)

        # 2. Построение узлов
        nodes = []
        for engram in engrams:
            # Цвет по типу памяти
            if engram.memory_type.value == "episodic":
                color = "#00d4ff"  # cyan
            elif engram.memory_type.value == "semantic":
                color = "#ffb347"  # amber
            else:
                color = "#888888"

            # Размер по количеству извлечений
            size = 10 + min(30, engram.retrieval_count * 2)

            # Label: усечённый контент
            label = engram.content[:50] + "..." if len(engram.content) > 50 else engram.content

            # Title: полная информация для tooltip
            title = (
                f"**{engram.memory_type.value}**\n\n"
                f"{engram.content}\n\n"
                f"Retention: {engram.retention_strength:.2f}\n"
                f"Retrievals: {engram.retrieval_count}\n"
                f"Emotional: {engram.emotional_boost:.2f}\n"
                f"Consolidation: {engram.consolidation_level}"
            )

            nodes.append({
                "id": engram.id,
                "label": label,
                "title": title,
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
                "consolidation_level": engram.consolidation_level,
            })

        # 3. Построение рёбер
        edges = []
        if include_synapses:
            node_ids = {n["id"] for n in nodes}
            for synapse in self.synapses.values():
                if synapse.source_id in node_ids and synapse.target_id in node_ids:
                    edges.append({
                        "from": synapse.source_id,
                        "to": synapse.target_id,
                        "width": 1 + synapse.weight * 5,
                        "color": {
                            "color": f"rgba(0, 212, 255, {min(1.0, synapse.weight)})",
                            "highlight": "#ffffff",
                        },
                        "title": (
                            f"Weight: {synapse.weight:.2f}\n"
                            f"Activations: {synapse.activation_count}"
                        ),
                    })

        return {
            "nodes": nodes,
            "edges": edges,
            "total_engrams": total_engrams,
            "total_synapses": total_synapses,
        }

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

    async def update_self_model(self, reflection: str) -> None:
        """Обновить само-модель на основе рефлексии."""
        if not reflection.strip():
            return

        # Добавляем как семантический факт о себе
        await self.store_fact(
            content=f"[Self-Model Update] {reflection}",
            metadata={"type": "self_model_update", "timestamp": time.time()},
        )

        # Обновляем текущую само-модель (конкатенация с ограничением длины)
        max_length = self.memory_config.max_self_model_length
        if len(self.self_model) + len(reflection) > max_length:
            # Обрезаем старую часть
            self.self_model = self.self_model[-(max_length - len(reflection)) :] + reflection
        else:
            self.self_model += f"\n{reflection}"

        await self._save_state()
        logger.debug(f"Само-модель обновлена (+{len(reflection)} символов)")

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
        """
        Атомарное сохранение состояния памяти с HMAC-подписью.

        Формат: {'__version__': N, 'data': {'engrams': {...}, 'synapses': {...}, 'self_model': str}}
        """
        state_path = Path(self.state_path).expanduser().resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "__version__": MEMORY_STATE_VERSION,
            "data": {
                "engrams": {k: v.to_dict() for k, v in self.engrams.items()},
                "synapses": {k: v.to_dict() for k, v in self.synapses.items()},
                "self_model": self.self_model,
            },
        }

        # Временный файл в той же ФС для атомарности os.replace
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=state_path.name + ".",
            suffix=".tmp",
            dir=str(state_path.parent),
        )
        tmp_path = Path(tmp_path_str)

        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

            # HMAC-подпись
            key = self._get_hmac_key()
            signature = self._compute_hmac(tmp_path, key)
            hmac_path = state_path.with_suffix(state_path.suffix + ".hmac")
            hmac_path.write_text(signature, encoding="utf-8")

            # Атомарная замена
            try:
                os.replace(tmp_path, state_path)
            except OSError as exc:
                raise LeyaAtomicWriteError(
                    "Атомарная замена memory_state не удалась",
                    context={"path": str(state_path), "error": str(exc)},
                ) from exc
        except LeyaMemoryError:
            raise
        except Exception as exc:
            raise LeyaMemoryError(
                "Сбой при сохранении состояния памяти",
                context={"path": str(state_path), "error": str(exc)},
            ) from exc

        finally:
            if tmp_path.exists():
                with contextlib.suppress(OSError):
                    tmp_path.unlink()

    async def _load_state(self) -> None:
        """
        Загрузка состояния памяти с проверкой HMAC и версии.

        Если файл отсутствует — инициализирует пустые структуры.
        """
        state_path = Path(self.state_path).expanduser().resolve()
        if not state_path.exists():
            self.engrams = {}
            self.synapses = {}
            self.self_model = ""
            return

        hmac_path = state_path.with_suffix(state_path.suffix + ".hmac")
        key = self._get_hmac_key()

        # Проверка HMAC
        if hmac_path.exists():
            expected = hmac_path.read_text(encoding="utf-8").strip()
            actual = self._compute_hmac(state_path, key)
            if not hmac.compare_digest(expected, actual):
                raise LeyaStateCorruptedError(
                    "HMAC memory_state не совпадает",
                    context={"path": str(state_path)},
                )
        else:
            raise LeyaStateCorruptedError(
                "Отсутствует HMAC для memory_state",
                context={"path": str(state_path)},
            )

        # Десериализация
        try:
            with state_path.open("rb") as f:
                raw = pickle.load(f)
        except (pickle.PickleError, EOFError, ValueError) as exc:
            raise LeyaStateCorruptedError(
                "Повреждён memory_state.pkl",
                context={"path": str(state_path), "error": str(exc)},
            ) from exc

        # Проверка версии
        if not isinstance(raw, dict) or raw.get("__version__") != MEMORY_STATE_VERSION:
            raise LeyaStateVersionMismatchError(
                "Несовместимая версия memory_state",
                context={
                    "path": str(state_path),
                    "file_version": raw.get("__version__") if isinstance(raw, dict) else None,
                    "expected_version": MEMORY_STATE_VERSION,
                },
            )

        # Восстановление состояния
        data = raw.get("data", {})

        # Восстановление энграмм
        self.engrams = {k: Engram.from_dict(v) for k, v in data.get("engrams", {}).items()}

        # Восстановление синапсов
        self.synapses = {k: Synapse.from_dict(v) for k, v in data.get("synapses", {}).items()}

        # Восстановление само-модели
        self.self_model = data.get("self_model", "")

        logger.info(
            f"Состояние памяти загружено: {len(self.engrams)} энграмм, {len(self.synapses)} синапсов"
        )

    def _get_hmac_key(self) -> bytes:
        """Получение ключа HMAC из окружения или fallback."""
        key = os.environ.get("LEYA_STATE_HMAC_KEY")
        if key:
            return key.encode("utf-8")
        return b"leya-dev-key-change-me-in-production"

    def _compute_hmac(self, path: Path, key: bytes) -> str:
        """Вычисление HMAC-SHA256 для файла."""
        h = hmac.new(key, digestmod=hashlib.sha256)
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
