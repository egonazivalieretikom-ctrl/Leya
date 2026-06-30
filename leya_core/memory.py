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
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from .config import LeyaConfig, MemoryConfig
from .exceptions import (
    LeyaAtomicWriteError,
    LeyaConfigError,
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
    """
    Отчёт о операции синхронизации in-memory ↔ ChromaDB.
    """

    def __init__(self):  # ✅ Исправлено: убрано : MemoryConfig и запятая
        self.added_to_chroma: int = 0  # ✅ Исправлено: chroma
        self.updated_in_chroma: int = 0  # ✅ Исправлено: chroma
        self.removed_from_chroma: int = 0  # ✅ Исправлено: chroma
        self.errors: int = 0
        self.duration_ms: float = 0.0

    @property
    def total_discrepancies(self) -> int:
        return self.added_to_chroma + self.removed_from_chroma

    def __str__(self) -> str:
        return (
            f"SyncReport(added={self.added_to_chroma}, "
            f"updated={self.updated_in_chroma}, "
            f"removed={self.removed_from_chroma}, "
            f"errors={self.errors}, "
            f"duration={self.duration_ms:.1f}ms)"
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
    distance: float | None = None

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

    def __init__(
        self,
        config,
        *,
        disable_hmac_check: bool = False,
        llm_client=None,
    ) -> None:
        """
        Инициализация MemorySystem.

        Args:
            config: Может быть либо LeyaConfig (тогда извлекается config.memory),
                    либо MemoryConfig напрямую (для тестов и упрощённого использования).
            disable_hmac_check: Если True, отключает проверку HMAC при загрузке (для тестов).
            llm_client: Опциональный LLM-клиент для консолидации памяти.
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

        # Флаг для отключения HMAC в тестах
        self._disable_hmac_check = disable_hmac_check

        # LLM-клиент для консолидации (опциональный)
        self.llm_client = llm_client

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

        # Путь к файлу состояния (гарантированная инициализация)
        self.state_path: Path = Path(self.memory_config.brain_dir) / "memory_state.json"

        logger.info(f"MemorySystem инициализирован: {self.memory_config.brain_dir}")

    # ========================================================================
    # Публичные методы: работа с энграммами
    # ========================================================================

    async def store_perception(
        self,
        content: str,
        emotional_boost: float = 0.0,
        metadata: dict | None = None,
        memory_type: MemoryType = MemoryType.EPISODIC,
    ) -> Engram:
        """
        Сохранить восприятие как энграмму указанного типа.

        Биологическая модель:
        - Создание новой энграммы
        - Генерация эмбеддинга (в отдельном потоке)
        - Формирование синаптических связей (LTP) с похожими энграммами
        """
        engram_id = str(uuid.uuid4())
        engram = Engram(
            id=engram_id,
            content=content,
            memory_type=memory_type,  # ← ИСПРАВЛЕНО: используем переданный параметр
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

        # Выбор коллекции в зависимости от типа памяти
        collection = (
            self.episodic_collection
            if memory_type == MemoryType.EPISODIC
            else self.semantic_collection
        )

        # Сохранение в ChromaDB
        try:
            await asyncio.to_thread(
                collection.add,
                ids=[engram_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[
                    {
                        "timestamp": engram.timestamp,
                        "emotional_boost": engram.emotional_boost,
                        "retention_strength": engram.retention_strength,
                        "memory_type": memory_type.value,
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

        logger.debug(f"Сохранена энграмма: {engram_id} (type={memory_type.value}, boost={emotional_boost:.2f})")
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
                        engram.distance = score
                        adjusted_score = score * (1.0 - engram.emotional_boost * 0.5)
                        candidates.append((engram, adjusted_score))

        # Обработка семантических
        if semantic_results and semantic_results.get("ids"):
            for i, engram_id in enumerate(semantic_results["ids"][0]):
                if engram_id in self.engrams:
                    engram = self.engrams[engram_id]
                    if engram.retention_strength >= min_retention:
                        score = semantic_results.get("distances", [[1.0]])[0][i]
                        engram.distance = score
                        candidates.append((engram, score))

        # Сортировка по score (меньше = лучше)
        candidates.sort(key=lambda x: x[1])
        selected = [engram for engram, _ in candidates[:max_results]]

        # ===================================================================
        # ✅ Activation spreading через синаптические связи
        # Биологическая модель: связанные энграммы получают boost
        # ===================================================================
        if selected and self.synapses:
            try:
                synaptic_boost = self._apply_synaptic_spreading(
                    activated_engrams=selected,
                    spreading_depth=2,
                    decay_factor=0.7,
                )
            
                if synaptic_boost:
                    # Формируем расширенный список с учётом spreading
                    selected_ids = {e.id for e in selected}
                    extended_candidates: list[tuple[Engram, float]] = [
                        (engram, score) for engram, score in candidates
                        if engram.id in selected_ids
                    ]
                
                    # Добавляем связанные энграммы с их synaptic boost
                    for engram_id, boost in synaptic_boost.items():
                        if engram_id in self.engrams and engram_id not in selected_ids:
                            engram = self.engrams[engram_id]
                            # Применяем забывание перед включением
                            # (используем ту же логику, что и для основных candidates)
                            if engram.retention_strength >= min_retention:
                                # Boost: чем выше synaptic activation, тем ниже "distance"
                                # Преобразуем boost в pseudo-distance (инверсия)
                                pseudo_distance = max(0.0, 1.0 - boost)
                                extended_candidates.append((engram, pseudo_distance))
                
                    # Пересортировка с учётом spreading
                    extended_candidates.sort(key=lambda x: x[1])
                    selected = [engram for engram, _ in extended_candidates[:max_results]]
            except Exception as spreading_exc:
                logger.warning(
                    f"Ошибка synaptic spreading (graceful degradation): {spreading_exc}"
                )
                # Graceful degradation — продолжаем без spreading

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
    
        Async для единообразия API с другими методами памяти.
        """
        if limit <= 0:
            return []

        await asyncio.sleep(0)

        candidates = [
            e
            for e in self.engrams.values()
            if e.memory_type == MemoryType.EPISODIC and e.retention_strength > 0.05
        ]
        candidates.sort(key=lambda e: e.timestamp, reverse=True)
        return candidates[:limit]

    async def get_recent_spontaneous_thoughts(self, limit: int = 10) -> list[Engram]:
        """
        Получить недавние спонтанные мысли (помеченные в metadata).
    
        Async для единообразия API с другими методами памяти.
        """
        thoughts = [
            e
            for e in self.engrams.values()
            if e.metadata.get("thought_type") in ("spontaneous", "reflection")
            and e.retention_strength > 0.1
        ]
        thoughts.sort(key=lambda e: e.timestamp, reverse=True)
        return thoughts[:limit]

    async def get_recent_semantic_facts(self, limit: int = 5) -> list[str]:
        """
        Публичный API: получение недавних семантических фактов.

        Используется MetaCognition (reflection.py) для генерации инсайтов
        и HomeostasisEngine для анализа знаний.

        Args:
            limit: Максимальное количество фактов (по умолчанию 5)

        Returns:
            Список строк — содержимое недавних семантических энграмм,
            отсортированных по timestamp (новые первыми).
        """
        if limit <= 0:
            return []

        candidates = [
            e
            for e in self.engrams.values()
            if e.memory_type == MemoryType.SEMANTIC
            and e.retention_strength > 0.1
        ]
        candidates.sort(key=lambda e: e.timestamp, reverse=True)
        return [e.content for e in candidates[:limit]]

    # ========================================================================
    # Само-модель
    # ========================================================================

    async def update_self_model(self, new_content: str) -> None:
        """Обновление модели себя с ограничением длины."""
        timestamp = datetime.now().isoformat()
        max_length = self.memory_config.max_self_model_length

        # Проверка длины ДО конкатенации
        new_entry = f"[{timestamp}] {new_content}"
    
        if len(new_entry) > max_length:
            # Обрезаем new_content, а не весь результат
            available_space = max_length - len(f"[{timestamp}] ") - 10  # 10 для безопасности
            if available_space > 0:
                new_content = new_content[:available_space]
                new_entry = f"[{timestamp}] {new_content}"
            else:
                # Если даже timestamp не помещается, пропускаем
                logger.warning(
                    f"Self-model entry слишком длинный, пропускаем (длина={len(new_entry)})"
                )
                return

        updated_content = new_entry

        # Если общий self_model превышает лимит, обрезаем старые записи
        if len(updated_content) > max_length:
            # Обрезаем с начала, сохраняя последние записи
            updated_content = updated_content[-max_length:]
            logger.warning(
                f"Self-model обрезан до {max_length} символов (было {len(updated_content)})"
            )

        self.self_model = updated_content

        # Сохранение состояния
        await self._save_state()

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
            words = re.findall(r"\b[а-яА-ЯёЁ]{6,}\b", text)
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
        forgotten = await self.forget_weak_memories()
        stats["episodes_forgotten"] = forgotten

        await self._save_state()
        logger.info(f"Консолидация завершена: {stats}")
        return stats

    async def forget_weak_memories(self, threshold: float = 0.1) -> int:
        """Публичный API для забывания слабых воспоминаний."""
        return await asyncio.to_thread(self._forget_weak_memories_sync, threshold)

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

                logger_thoughts = logging.getLogger("leya.thoughts")
                logger_thoughts.debug(
                    "=== LTP (новый синапс) ===\n"
                    f"{new_engram_id[:8]} ↔ {related_id[:8]}\n"
                    f"Similarity: {similarity:.3f}\n"
                    f"Начальный вес: {weight:.3f}\n"
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
                    old_weight = synapse.weight
                    synapse.weight = min(1.0, synapse.weight + learning_rate)
                    synapse.activation_count += 1
                    
                    if synapse.weight > old_weight + 0.05:  # логируем только значимое усиление
                        logger_thoughts = logging.getLogger("leya.thoughts")
                        logger_thoughts.debug(
                            "=== LTP (усиление синапса) ===\n"
                            f"{synapse.source_id[:8]} → {synapse.target_id[:8]}\n"
                            f"Вес: {old_weight:.3f} → {synapse.weight:.3f}\n"
                            f"Активаций: {synapse.activation_count}\n"
                        )

                if key2 in self.synapses:
                    synapse = self.synapses[key2]
                    synapse.weight = min(1.0, synapse.weight + learning_rate)
                    synapse.activation_count += 1

    def _apply_synaptic_spreading(
        self,
        activated_engrams: list[Engram],
        spreading_depth: int = 2,
        decay_factor: float = 0.7,
    ) -> dict[str, float]:
        """
        Распространение активации по синаптическим связям (activation spreading).
    
        Биологическая модель: когда энграмма активируется (через ChromaDB query),
        связанные с ней энграммы получают boost пропорционально weight синапса.
        Это имитирует ассоциативную память — если вспомнили A, автоматически
        активируются связанные B, C (Hebbian spreading).
    
        Args:
            activated_engrams: Список активированных энграмм (из ChromaDB query)
            spreading_depth: Глубина распространения (сколько итераций BFS)
            decay_factor: Коэффициент затухания на каждом уровне (0.7 = 30% затухание)
    
        Returns:
            Словарь {engram_id: synaptic_boost} — дополнительный boost для каждой
            связанной энграммы (нормализованный к [0.0, 0.3]).
        """
        if not activated_engrams or not self.synapses:
            return {}
    
        # Инициализируем активацию для исходных энграмм (сила = 1.0)
        activation: dict[str, float] = {e.id: 1.0 for e in activated_engrams}
        activated_ids = set(activation.keys())
    
        # Итеративное распространение (BFS-like)
        for depth in range(spreading_depth):
            new_activation: dict[str, float] = {}
        
            for source_id, source_activation in activation.items():
                # Находим все синапсы, исходящие из source_id
                for synapse in self.synapses.values():
                    if synapse.source_id != source_id:
                        continue
                
                    target_id = synapse.target_id
                
                    # Пропускаем уже активированные с большей силой
                    current_target_activation = activation.get(target_id, 0.0)
                    propagated_activation = (
                        source_activation
                        * synapse.weight
                        * (decay_factor ** (depth + 1))
                    )
                
                    if propagated_activation <= current_target_activation:
                        continue
                
                    # Берём максимум, если target уже был активирован
                    if target_id in new_activation:
                        new_activation[target_id] = max(
                            new_activation[target_id], propagated_activation
                        )
                    else:
                        new_activation[target_id] = propagated_activation
        
            # Добавляем новую активацию к общей
            for engram_id, act in new_activation.items():
                if engram_id in activation:
                    activation[engram_id] = max(activation[engram_id], act)
                else:
                    activation[engram_id] = act
    
        # Убираем исходные энграммы (они уже в результате ChromaDB)
        for engram_id in activated_ids:
            activation.pop(engram_id, None)
    
        if not activation:
            return {}
    
        # Нормализуем и ограничиваем boost (максимум 30% от базового score)
        max_activation = max(activation.values())
        if max_activation <= 0:
            return {}
    
        synaptic_boost = {
            engram_id: (act / max_activation) * 0.3
            for engram_id, act in activation.items()
            if act > 0.1  # Порог значимости — отсекаем шум
        }
    
        if synaptic_boost:
            logger_thoughts = logging.getLogger("leya.thoughts")
            logger_thoughts.debug(
                "=== Synaptic Spreading ===\n"
                f"Активировано: {len(activated_engrams)} энграмм\n"
                f"Распространено на: {len(synaptic_boost)} связанных энграмм\n"
                f"Глубина: {spreading_depth}, decay: {decay_factor}\n"
            )
    
        return synaptic_boost

    def _forget_weak_memories_sync(self, threshold: float = 0.1) -> int:
        """Удаление энграмм с retention_strength ниже порога (sync версия)."""
        to_delete = [
            engram_id
            for engram_id, engram in self.engrams.items()
            if engram.retention_strength < threshold
        ]

        for engram_id in to_delete:
            # Удаление синапсов
            keys_to_delete = [key for key in self.synapses if engram_id in key]
            for key in keys_to_delete:
                del self.synapses[key]

            # Удаление из локального состояния
            del self.engrams[engram_id]

        if to_delete:
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
        """Извлечение семантических фактов из эпизодов через LLM с defensive проверкой."""
        if not hasattr(self, "llm_client") or not self.llm_client:
            return []

        episodes_text = "\n".join([f"- {e.content}" for e in episodes[:20]])
        prompt = f"""Проанализируй следующие эпизоды и извлеки из них ключевые семантические факты:
    {episodes_text}
    Верни список фактов (каждый с новой строки, без нумерации):"""

        try:
            # Defensive check: используем generate, если есть, иначе chat
            response = await self.llm_client.generate(prompt, max_tokens=500)

            facts = [line.strip() for line in response.split("\n") if line.strip()]
            return facts[:10]
        except AttributeError as e:
            logger.warning(f"llm_client не поддерживает generate(): {e}")
            return []
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
        Атомарное сохранение состояния памяти в JSON + HMAC.

        Биологическая модель:
        - Сохранение всех энграмм и синапсов
        - HMAC-SHA256 подпись для целостности
        - Атомарная запись через tempfile + os.replace

        Raises:
            LeyaAtomicWriteError: Ошибка записи файла
            LeyaConfigError: Отсутствие/слабость HMAC ключа
            LeyaMemoryError: Другие ошибки памяти
        """
        if not hasattr(self, "state_path") or self.state_path is None:
            if hasattr(self, "memory_config") and self.memory_config is not None:
                brain_dir = getattr(self.memory_config, "brain_dir", "./leya_brain")
            elif hasattr(self, "config") and self.config is not None:
                brain_dir = getattr(self.config, "brain_dir", "./leya_brain")
            else:
                brain_dir = "./leya_brain"
            self.state_path = Path(brain_dir) / "memory_state.json"

        state_path = Path(self.state_path).expanduser().resolve()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = None
        try:
            payload = {
                "__version__": MEMORY_STATE_VERSION,
                "data": {
                    "engrams": {k: v.to_dict() for k, v in self.engrams.items()},
                    "synapses": {k: v.to_dict() for k, v in self.synapses.items()},
                    "self_model": self.self_model,
                },
            }

            fd, tmp_path_str = tempfile.mkstemp(
                prefix=state_path.name + ".", suffix=".tmp", dir=str(state_path.parent)
            )
            tmp_path = Path(tmp_path_str)

            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            key = self._get_hmac_key()
            signature = self._compute_hmac(tmp_path, key)
            (state_path.with_suffix(state_path.suffix + ".hmac")).write_text(
                signature, encoding="utf-8"
            )

            try:
                os.replace(tmp_path, state_path)
            except OSError as ose:
                if "cross-device" in str(ose).lower():
                    import shutil
                    shutil.move(str(tmp_path), str(state_path))
                else:
                    raise

        except (OSError, IOError, PermissionError) as exc:
            # Конкретные исключения для файловых операций
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass  # Игнорируем ошибки очистки
            raise LeyaAtomicWriteError(
                f"Сбой атомарной записи состояния памяти [path='{state_path}', error='{exc}']",
                context={"path": str(state_path), "error": str(exc), "error_type": type(exc).__name__},
            ) from exc

        except (LeyaConfigError, LeyaMemoryError, LeyaAtomicWriteError):
            # Наши специфичные исключения — пробрасываем без обёртки
            raise

        except Exception as exc:
            # Last resort: неизвестные ошибки (но не CancelledError/KeyboardInterrupt)
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            raise LeyaAtomicWriteError(
                f"Неожиданная ошибка при сохранении состояния памяти [path='{state_path}']",
                context={"path": str(state_path), "error": str(exc), "error_type": type(exc).__name__},
            ) from exc

    async def save_state(self) -> None:
        """
        Публичный API для сохранения состояния памяти.
    
        Делегирует приватному методу _save_state().
        Вызывается из LeyaOS при shutdown.
        """
        await self._save_state()

    async def _load_state(self) -> None:
        """
        Загрузка состояния памяти с проверкой HMAC и версии.
        Поддержает отключение HMAC-проверки для тестов.
        """
        # Defensive guard
        if not hasattr(self, "state_path") or self.state_path is None:
            if hasattr(self, "memory_config") and self.memory_config:
                self.state_path = Path(self.memory_config.brain_dir) / "memory_state.json"
            else:
                self.state_path = Path("./leya_brain/memory_state.json")

        state_path = self.state_path.expanduser().resolve()

        if not state_path.exists():
            self.engrams = {}
            self.synapses = {}
            self.self_model = ""
            return

        hmac_path = state_path.with_suffix(state_path.suffix + ".hmac")

        # Проверка HMAC (если не отключена)
        if not self._disable_hmac_check:
            key = self._get_hmac_key()

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
        else:
            logger.debug("HMAC проверка отключена (тестовый режим)")

        # Десериализация
        try:
            import json

            with state_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (ValueError, json.JSONDecodeError) as exc:
            raise LeyaStateCorruptedError(
                "Повреждён memory_state",
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
        self.engrams = {k: Engram.from_dict(v) for k, v in data.get("engrams", {}).items()}
        self.synapses = {k: Synapse.from_dict(v) for k, v in data.get("synapses", {}).items()}
        self.self_model = data.get("self_model", "")

        logger.info(
            f"Состояние памяти загружено: {len(self.engrams)} энграмм, {len(self.synapses)} синапсов"
        )

        try:
            await self._sync_chroma_from_memory()
        except Exception as exc:
            logger.warning(f"Sync после _load_state не удался (graceful degradation): {exc}")

    def _ensure_state_path(self) -> Path:
        """
        Гарантирует наличие и валидность state_path.

        Returns:
            Path: Абсолютный путь к файлу состояния.
        """
        if not hasattr(self, "state_path") or self.state_path is None:
            if hasattr(self, "memory_config") and self.memory_config:
                self.state_path = Path(self.memory_config.brain_dir) / "memory_state.json"
            else:
                self.state_path = Path("./leya_brain/memory_state.json")
                logger.warning(
                    f"state_path не инициализирован, используем fallback: {self.state_path}"
                )

        return self.state_path.expanduser().resolve()

    async def _sync_collection(
        self,
        collection,
        memory_type: MemoryType,
    ) -> SyncReport:
        report = SyncReport()
        start_time = time.time()

        type_engrams = {
            eid: engram
            for eid, engram in self.engrams.items()
            if getattr(engram, "memory_type", None) == memory_type
        }

        if not type_engrams:
            try:
                chroma_data = await asyncio.to_thread(collection.get)
                chroma_ids = set(chroma_data.get("ids", [])) if chroma_data else set()
                if chroma_ids:
                    BATCH_SIZE = 500
                    ids_list = list(chroma_ids)
                    for i in range(0, len(ids_list), BATCH_SIZE):
                        batch = ids_list[i : i + BATCH_SIZE]
                        await asyncio.to_thread(collection.delete, ids=batch)
                    report.removed_from_chroma = len(chroma_ids)
            except Exception as exc:
                logger.error(
                    f"Ошибка удаления осиротевших {memory_type.value}: {exc}", exc_info=True
                )
                report.errors += 1
            finally:
                report.duration_ms = (time.time() - start_time) * 1000
            return report

        try:
            chroma_data = await asyncio.to_thread(collection.get)
            chroma_ids = set(chroma_data.get("ids", [])) if chroma_data else set()
            in_memory_ids = set(type_engrams.keys())

            ids_to_add = in_memory_ids - chroma_ids
            ids_to_update = in_memory_ids & chroma_ids
            ids_to_remove = chroma_ids - in_memory_ids

            if in_memory_ids:
                BATCH_SIZE = 500
                ids_list = list(in_memory_ids)

                for i in range(0, len(ids_list), BATCH_SIZE):
                    batch_ids = ids_list[i : i + BATCH_SIZE]
                    batch_engrams = [type_engrams[eid] for eid in batch_ids]

                    batch_documents: list[str] = []
                    batch_metadatas: list[dict] = []
                    batch_embeddings: list[list[float]] = []
                    valid_indices: list[int] = []

                    for idx, engram in enumerate(batch_engrams):
                        if getattr(engram, "retention_strength", 1.0) < 0.05:
                            continue
                        try:
                            emb = await asyncio.to_thread(self._generate_embedding, engram.content)
                        except Exception:
                            report.errors += 1
                            continue
                        if emb is None or len(emb) == 0:
                            report.errors += 1
                            continue

                        batch_documents.append(engram.content)
                        batch_embeddings.append(emb)
                        valid_indices.append(idx)

                        batch_metadatas.append(
                            {
                                "id": engram.id,
                                "memory_type": getattr(engram, "memory_type", memory_type).value,
                                "timestamp": getattr(engram, "timestamp", 0),
                                "retention_strength": getattr(engram, "retention_strength", 0.0),
                                "emotional_boost": getattr(engram, "emotional_boost", 0.0),
                                "retrieval_count": getattr(engram, "retrieval_count", 0),
                                "consolidation_level": getattr(engram, "consolidation_level", 0),
                            }
                        )

                    if not batch_documents:
                        continue

                    adj_ids = (
                        [batch_ids[v] for v in valid_indices]
                        if len(batch_documents) < len(batch_ids)
                        else batch_ids
                    )

                    try:
                        await asyncio.to_thread(
                            collection.upsert,
                            ids=adj_ids,
                            documents=batch_documents,
                            embeddings=batch_embeddings,
                            metadatas=batch_metadatas,
                        )
                    except Exception as exc:
                        report.errors += 1
                        raise LeyaMemoryError(
                            f"Сбой upsert в ChromaDB ({memory_type.value})",
                            context={"error": str(exc)},
                        ) from exc

                report.added_to_chroma = len(ids_to_add)
                report.updated_in_chroma = len(ids_to_update)

            if ids_to_remove:
                BATCH_SIZE = 500
                rem_list = list(ids_to_remove)
                for i in range(0, len(rem_list), BATCH_SIZE):
                    batch = rem_list[i : i + BATCH_SIZE]
                    try:
                        await asyncio.to_thread(collection.delete, ids=batch)
                    except Exception:
                        report.errors += 1
                report.removed_from_chroma = len(ids_to_remove)

        except Exception as exc:
            report.errors += 1
            logger.error(f"Критическая ошибка sync {memory_type.value}: {exc}", exc_info=True)
        finally:
            report.duration_ms = (time.time() - start_time) * 1000

        return report

    async def _sync_chroma_from_memory(self) -> SyncReport:
        """
        Синхронизация in-memory состояния с ChromaDB для обеих коллекций.

        Агрегирует результаты синхронизации эпизодической и семантической памяти
        в единый SyncReport.

        Returns:
            SyncReport с суммарной информацией о синхронизации.
        """
        logger.info("Начало синхронизации in-memory ↔ ChromaDB...")
        total_report = SyncReport()
        start_time = time.time()

        # 1. Синхронизация эпизодической памяти
        try:
            report_episodic = await self._sync_collection(
                collection=self.episodic_collection,
                memory_type=MemoryType.EPISODIC,
            )
            total_report.added_to_chroma += report_episodic.added_to_chroma
            total_report.updated_in_chroma += report_episodic.updated_in_chroma
            total_report.removed_from_chroma += report_episodic.removed_from_chroma
            total_report.errors += report_episodic.errors
            logger.info(f"Sync episodic: {report_episodic}")
        except Exception as exc:
            logger.error(f"Сбой sync episodic: {exc}", exc_info=True)
            total_report.errors += 1

        # 2. Синхронизация семантической памяти (ЕДИНСТВЕННЫЙ ВЫЗОВ)
        try:
            report_semantic = await self._sync_collection(
                collection=self.semantic_collection,
                memory_type=MemoryType.SEMANTIC,
            )
            total_report.added_to_chroma += report_semantic.added_to_chroma
            total_report.updated_in_chroma += report_semantic.updated_in_chroma
            total_report.removed_from_chroma += report_semantic.removed_from_chroma
            total_report.errors += report_semantic.errors
            logger.info(f"Sync semantic: {report_semantic}")
        except Exception as exc:
            logger.error(f"Сбой sync semantic: {exc}", exc_info=True)
            total_report.errors += 1

        # 3. Финальная длительность
        total_report.duration_ms = (time.time() - start_time) * 1000

        logger.info(
            f"✅ Полная синхронизация завершена: "
            f"added={total_report.added_to_chroma}, "
            f"updated={total_report.updated_in_chroma}, "
            f"removed={total_report.removed_from_chroma}, "
            f"errors={total_report.errors}, "
            f"duration={total_report.duration_ms:.1f}ms"
        )

        return total_report

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
        key = os.environ.get("LEYA_STATE_HMAC_KEY")

        if not key or len(key.strip()) < 32:
            raise LeyaConfigError(
                "LEYA_STATE_HMAC_KEY не установлен или слишком короткий (нужно минимум 32 символа). "
                "Сгенерируй ключ командой: python -c 'import secrets; print(secrets.token_urlsafe(32))' "
                "и добавь в файл .env: LEYA_STATE_HMAC_KEY=твой_ключ"
            )

        return key.encode("utf-8")
