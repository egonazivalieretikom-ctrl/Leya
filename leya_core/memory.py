"""
leya_core/memory.py — Биологически мотивированная система памяти Леи.

Моделирует:
1. Синаптическую пластичность (LTP/LTD) — сила связей между воспоминаниями
2. Кривые забывания Эббингауза — нелинейное забывание с повторением
3. Эмоциональное тегирование — важность определяется силой драйвов
4. Консолидацию во сне — реплей эпизодов, интеграция, прунинг
5. Ассоциативное вспоминание — распространение активации по связям
"""

import logging
import math
import time
import os
import pickle
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import numpy as np
from sentence_transformers import SentenceTransformer
import re
import chromadb
from chromadb.config import Settings

logger = logging.getLogger("MemorySystem")


class MemoryType(Enum):
    """Типы памяти"""
    EPISODIC = "episodic"  # Эпизодическая (события)
    SEMANTIC = "semantic"  # Семантическая (факты)
    PROCEDURAL = "procedural"  # Процедурная (навыки)


@dataclass
class Synapse:
    """Синапс — связь между двумя воспоминаниями"""
    pre_id: str  # ID источника
    post_id: str  # ID цели
    weight: float = 0.1  # Сила связи (0.0 - 1.0)
    last_activated: float = 0.0  # Время последней активации
    activation_count: int = 0  # Сколько раз активировалась


@dataclass
class Engram:
    """Энграмма — след памяти (воспоминание)"""
    id: str
    content: str
    memory_type: MemoryType
    timestamp: float
    emotional_intensity: float = 0.5  # Эмоциональный заряд (0.0 - 1.0)
    retrieval_count: int = 0  # Сколько раз вспоминалось
    last_retrieved: float = 0.0  # Время последнего вспоминания
    decay_rate: float = 0.1  # Скорость забывания
    consolidation_level: float = 0.0  # Уровень консолидации (0.0 - 1.0)
    drive_state: Dict[str, float] = field(default_factory=dict)  # Состояние драйвов в момент формирования
    
    # Вычисляемые поля
    @property
    def retention_strength(self) -> float:
        """Сила удержания памяти (кривая Эббингауза)"""
        if self.retrieval_count == 0:
            time_since = time.time() - self.timestamp
        else:
            time_since = time.time() - self.last_retrieved
        
        # Кривая забывания Эббингауза: R = e^(-t/S)
        # S — стабильность памяти, зависит от повторений и эмоциональности
        stability = self._calculate_stability()
        retention = math.exp(-time_since / stability)
        
        return retention
    
    def _calculate_stability(self) -> float:
        """Вычисляет стабильность памяти на основе повторений и эмоциональности"""
        # Базовая стабильность
        base_stability = 1.0  # секунды (начальное значение)
        
        # Усиление от повторений (логарифмический рост)
        repetition_factor = 1 + math.log(1 + self.retrieval_count)
        
        # Усиление от эмоционального заряда
        emotion_factor = 1 + (self.emotional_intensity * 2)
        
        # Усиление от консолидации
        consolidation_factor = 1 + (self.consolidation_level * 3)
        
        return base_stability * repetition_factor * emotion_factor * consolidation_factor


class MemorySystem:
    """
    Биологически мотивированная система памяти.
    
    Архитектура:
    - Гиппокамп: кратковременная память (эпизоды)
    - Неокортекс: долговременная память (семантические факты)
    - Синапсы: связи между воспоминаниями
    - Миндалевидное тело: эмоциональное тегирование
    - Сон: консолидация и прунинг
    """
    
    def __init__(self, persist_directory: str = "./leya_brain"):
        self.persist_directory = persist_directory
        
        # Загрузка эмбеддинг-модели
        logger.info("MemorySystem: Загрузка нейронной модели для эмбеддингов...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Инициализация ChromaDB
        self.chroma_client = chromadb.PersistentClient(path=persist_directory)
        
        # Коллекции памяти
        self.episodic_collection = self.chroma_client.get_or_create_collection(
            name="episodic_memory",
            metadata={"hnsw:space": "cosine"}
        )
        self.semantic_collection = self.chroma_client.get_or_create_collection(
            name="semantic_memory",
            metadata={"hnsw:space": "cosine"}
        )
        self.chroma_client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.chroma_client.get_or_create_collection(
            name="leya_memories",
            metadata={"hnsw:space": "cosine"}
        )
        
        # Синаптическая сеть (в памяти, не в БД)
        self.synapses: Dict[Tuple[str, str], Synapse] = {}
        
        # Энграммы (в памяти)
        self.engrams: Dict[str, Engram] = {}
        
        # Параметры
        self.LTP_THRESHOLD = 0.7  # Порог для долгосрочной потенциации
        self.LTD_THRESHOLD = 0.3  # Порог для долгосрочной депрессии
        self.CONSOLIDATION_THRESHOLD = 0.8  # Порог для консолидации в долговременную память

        # Загружаем сохраненное состояние памяти
        self._load_state()

        logger.info("MemorySystem: Инициализация завершена.")

    def _load_state(self):
        """Загружает синапсы и энграммы с диска."""
        import pickle
        state_file = os.path.join(self.persist_directory, "memory_state.pkl")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'rb') as f:
                    state = pickle.load(f)
                self.synapses = state.get('synapses', {})
                self.engrams = state.get('engrams', {})
                logger.info(f"MemorySystem: Состояние памяти загружено из {state_file}")
            except Exception as e:
                logger.error(f"MemorySystem: Ошибка загрузки состояния: {e}")

    # ← ВАЖНО: 4 пробела перед def
    def _save_state(self):
        """Сохраняет синапсы и энграммы на диск для персистентности."""
        import pickle
        state_file = os.path.join(self.persist_directory, "memory_state.pkl")
        try:
            state = {
                'synapses': self.synapses,
                'engrams': self.engrams
            }
            with open(state_file, 'wb') as f:
                pickle.dump(state, f)
            logger.info(f"MemorySystem: Состояние памяти сохранено в {state_file}")
        except Exception as e:
            logger.error(f"MemorySystem: Ошибка сохранения состояния: {e}")

    # ==================== ФОРМИРОВАНИЕ ПАМЯТИ ====================
    
    async def store_perception(
        self,
        content: str,
        drive_state: Dict[str, float],
        importance: float = 0.5,
        memory_type: MemoryType = MemoryType.EPISODIC
    ):
        """
        Формирует новое воспоминание (энграмму).
        
        Биологический аналог: кодирование в гиппокампе с эмоциональным тегированием.
        """
        # Вычисляем эмоциональный заряд на основе силы драйвов
        emotional_intensity = self._calculate_emotional_intensity(drive_state)
        
        # Создаём энграмму
        engram_id = f"engram_{int(time.time() * 1000)}"
        engram = Engram(
            id=engram_id,
            content=content,
            memory_type=memory_type,
            timestamp=time.time(),
            emotional_intensity=emotional_intensity,
            drive_state=drive_state
        )
        
        self.engrams[engram_id] = engram
        
        # Сохраняем в ChromaDB
        collection = self.episodic_collection if memory_type == MemoryType.EPISODIC else self.semantic_collection
        
        embedding = self.embedding_model.encode(content).tolist()
        
        collection.add(
            ids=[engram_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[{
                "memory_type": memory_type.value,
                "emotional_intensity": emotional_intensity,
                "timestamp": engram.timestamp,
                "decay_rate": engram.decay_rate
            }]
        )
        
        logger.info(f"MemorySystem: Сформирована энграмма {engram_id} (эмоциональный заряд: {emotional_intensity:.2f})")
        
        # Формируем синаптические связи с похожими воспоминаниями
        await self._form_synaptic_connections(engram, collection)
    
    def _calculate_emotional_intensity(self, drive_state: Dict[str, float]) -> float:
        """
        Вычисляет эмоциональный заряд на основе отклонения драйвов от нормы.
        
        Биологический аналог: активация миндалевидного тела при сильных эмоциях.
        """
        if not drive_state:
            return 0.5
        
        # Эмоциональность = сумма отклонений драйвов от базового уровня (0.3)
        deviations = [abs(value - 0.3) for value in drive_state.values()]
        avg_deviation = sum(deviations) / len(deviations)
        
        # Нормализуем в диапазон [0, 1]
        return min(1.0, avg_deviation * 2)
    
        def _save_state(self):
            """Сохраняет синапсы и энграммы на диск для персистентности."""
            import pickle
            import os
        
            state_file = os.path.join(self.persist_directory, "memory_state.pkl")
            try:
                state = {
                    'synapses': self.synapses,
                    'engrams': self.engrams
                }
                with open(state_file, 'wb') as f:
                    pickle.dump(state, f)
                logger.info(f"MemorySystem: Состояние памяти сохранено в {state_file}")
            except Exception as e:
                logger.error(f"MemorySystem: Ошибка сохранения состояния: {e}")

        def _load_state(self):
            """Загружает синапсы и энграммы с диска."""
            import pickle
        
            state_file = os.path.join(self.persist_directory, "memory_state.pkl")
            if os.path.exists(state_file):
                try:
                    with open(state_file, 'rb') as f:
                        state = pickle.load(f)
                    self.synapses = state.get('synapses', {})
                    self.engrams = state.get('engrams', {})
                    logger.info(f"MemorySystem: Состояние памяти загружено из {state_file}")
                except Exception as e:
                    logger.error(f"MemorySystem: Ошибка загрузки состояния: {e}")

    async def _form_synaptic_connections(self, new_engram: Engram, collection):
        """
        Формирует синаптические связи между новым воспоминанием и похожими.
        
        Биологический аналог: LTP (долгосрочная потенциация) при одновременной активации нейронов.
        """
        # Ищем похожие воспоминания
        embedding = self.embedding_model.encode(new_engram.content).tolist()
        
        similar = collection.query(
            query_embeddings=[embedding],
            n_results=5,
            include=["metadatas"]
        )
        
        if not similar['ids'] or not similar['ids'][0]:
            return
        
        # Создаём синапсы с похожими воспоминаниями
        for i, similar_id in enumerate(similar['ids'][0]):
            if similar_id == new_engram.id:
                continue
            
            # Сила связи зависит от семантического сходства
            similarity = 1.0 - (i * 0.15)  # Чем выше в списке, тем сильнее связь
            similarity = max(0.1, min(1.0, similarity))
            
            synapse = Synapse(
                pre_id=new_engram.id,
                post_id=similar_id,
                weight=similarity,
                last_activated=time.time()
            )
            
            self.synapses[(new_engram.id, similar_id)] = synapse
            self.synapses[(similar_id, new_engram.id)] = Synapse(
                pre_id=similar_id,
                post_id=new_engram.id,
                weight=similarity,
                last_activated=time.time()
            )
    
    # ==================== ВСПОМИНАНИЕ ====================
    
    async def retrieve_context(
        self,
        current_stimulus: str,
        current_drive_state: Dict[str, float],
        limit: int = 5
    ) -> str:
        """
        Вспоминает релевантный опыт через ассоциативное распространение активации.
        
        Биологический аналог: активация нейронных цепочек через синапсы.
        """
        if not current_stimulus:
            return ""
        
        # Кодируем стимул
        stimulus_embedding = self.embedding_model.encode(current_stimulus).tolist()
        
        # Ищем прямые ассоциации
        direct_matches = self.episodic_collection.query(
            query_embeddings=[stimulus_embedding],
            n_results=limit * 2,
            include=["metadatas", "documents"]
        )
        
        if not direct_matches['ids'] or not direct_matches['ids'][0]:
            return ""
        
        # Фильтруем по силе удержания (кривая Эббингауза)
        relevant_memories = []
        
        for i, mem_id in enumerate(direct_matches['ids'][0]):
            if mem_id not in self.engrams:
                continue
            
            engram = self.engrams[mem_id]
            retention = engram.retention_strength
            
            # Пропускаем забытые воспоминания
            if retention < 0.1:
                continue
            
            # Усиливаем эмоционально заряженные воспоминания
            emotional_boost = engram.emotional_intensity * 0.3
            
            # Рассчитываем релевантность
            relevance = retention + emotional_boost - (i * 0.05)
            
            if relevance > 0.2:
                relevant_memories.append((engram, relevance))
        
        # Сортируем по релевантности
        relevant_memories.sort(key=lambda x: x[1], reverse=True)
        
        # Берём топ-N
        top_memories = relevant_memories[:limit]
        
        # Формируем контекст
        if not top_memories:
            return ""
        
        context_parts = []
        for engram, relevance in top_memories:
            context_parts.append(f"[Воспоминание] (релевантность: {relevance:.2f}, эмоциональность: {engram.emotional_intensity:.2f})\n{engram.content}")
            
            # Обновляем счётчик вспоминаний
            engram.retrieval_count += 1
            engram.last_retrieved = time.time()
            
            # Усиливаем синапсы (LTP)
            await self._strengthen_synapses(engram.id)
        
        return "\n\n".join(context_parts)
    
    async def _strengthen_synapses(self, engram_id: str):
        """
        Усиливает синапсы, связанные с активированным воспоминанием (LTP).
        
        Биологический аналог: долгосрочная потенциация при повторной активации.
        """
        for (pre_id, post_id), synapse in self.synapses.items():
            if pre_id == engram_id or post_id == engram_id:
                # Усиливаем связь
                synapse.weight = min(1.0, synapse.weight + 0.05)
                synapse.last_activated = time.time()
                synapse.activation_count += 1
    
    # ==================== ЗАБЫВАНИЕ ====================
    
    async def forget_weak_memories(self, threshold: float = 0.1):
        """
        Забывает слабые воспоминания (синаптический прунинг).
        
        Биологический аналог: удаление неактивных синапсов для снижения энтропии.
        """
        forgotten_count = 0
        
        # Проверяем все энграммы
        for engram_id, engram in list(self.engrams.items()):
            retention = engram.retention_strength
            
            if retention < threshold:
                # Удаляем энграмму
                del self.engrams[engram_id]
                
                # Удаляем из ChromaDB
                try:
                    self.episodic_collection.delete(ids=[engram_id])
                except Exception as e:
                    logger.debug(f"Не удалось удалить энграмму {engram_id}: {e}")
                
                # Удаляем связанные синапсы
                synapses_to_remove = [
                    key for key in self.synapses.keys()
                    if key[0] == engram_id or key[1] == engram_id
                ]
                for key in synapses_to_remove:
                    del self.synapses[key]
                
                forgotten_count += 1
        
        if forgotten_count > 0:
            logger.info(f"MemorySystem: Забыто {forgotten_count} слабых воспоминаний (прунинг)")


    async def get_recent_spontaneous_thoughts(self, limit: int = 5) -> List[str]:
        """
        Возвращает последние спонтанные мысли из памяти.
        """
        try:
            results = self.episodic_collection.get(
                where={"memory_type": "episodic"},
                limit=limit * 2,  # Берём больше, чтобы отфильтровать
                include=["documents"]
            )
        
            if not results['documents']:
                return []
        
            # Фильтруем только спонтанные мысли
            thoughts = []
            for doc in results['documents']:
                if '[СПОНТАННАЯ МЫСЛЬ]' in doc or 'спонтанн' in doc.lower():
                    # Извлекаем текст после маркера
                    thought = doc.replace('[СПОНТАННАЯ МЫСЛЬ]', '').strip()
                    if thought:
                        thoughts.append(thought)
                        if len(thoughts) >= limit:
                            break
        
            return thoughts
        except Exception as e:
            logger.error(f"Ошибка получения спонтанных мыслей: {e}")
            return []
    
    # ==================== КОНСОЛИДАЦИЯ ВО СНЕ ====================
    
    async def consolidate_memories(self, llm_client=None):
        """
        Консолидация памяти во время сна.
        
        Биологический аналог:
        1. Реплей эпизодов (гиппокампальный реплей)
        2. Интеграция с существующими знаниями (схемами)
        3. Перенос из кратковременной в долговременную память
        4. Прунинг неважного
        """
        self._save_state()
        logger.info("MemorySystem: Начало консолидации памяти (Сон)...")
        
        # 1. Реплей эпизодов — активируем недавние воспоминания
        recent_engrams = sorted(
            self.engrams.values(),
            key=lambda x: x.timestamp,
            reverse=True
        )[:20]
        
        for engram in recent_engrams:
            # Имитируем реплей — активируем связанные синапсы
            await self._replay_engram(engram)
        
        # 2. Консолидация сильных воспоминаний в долговременную память
        for engram in recent_engrams:
            if engram.retention_strength > self.CONSOLIDATION_THRESHOLD:
                engram.consolidation_level = min(1.0, engram.consolidation_level + 0.1)
                logger.info(f"MemorySystem: Консолидирована энграмма {engram.id} (уровень: {engram.consolidation_level:.2f})")
        
        # 3. Извлечение семантических фактов (если есть LLM)
        if llm_client:
            await self._extract_semantic_facts(recent_engrams, llm_client)
        
        # 4. Прунинг слабых воспоминаний
        await self.forget_weak_memories(threshold=0.15)
        
        logger.info("MemorySystem: Консолидация завершена.")
    
    async def _replay_engram(self, engram: Engram):
        """
        Реплей энграммы — активирует связанные воспоминания.
        
        Биологический аналог: гиппокампальный реплей во время сна.
        """
        # Находим связанные синапсы
        connected_ids = [
            post_id for (pre_id, post_id), synapse in self.synapses.items()
            if pre_id == engram.id and synapse.weight > 0.3
        ]
        
        # Активируем связанные воспоминания
        for connected_id in connected_ids[:3]:  # Ограничиваем количество
            if connected_id in self.engrams:
                connected_engram = self.engrams[connected_id]
                connected_engram.retrieval_count += 1
                connected_engram.last_retrieved = time.time()
    
    async def _extract_semantic_facts(self, episodes: List[Engram], llm_client):
        """
        Извлекает семантические факты из эпизодов.
        
        Биологический аналог: формирование семантической памяти из эпизодической.
        """
        if not episodes:
            return
        
        # Формируем текст эпизодов
        episodes_text = "\n\n".join([
            f"[Эпизод {i+1}] (Эмоциональность: {ep.emotional_intensity:.2f})\n{ep.content}"
            for i, ep in enumerate(episodes[:10])
        ])
        
        prompt = f"""
Ты — процесс консолидации памяти.
Проанализируй эти эпизоды и извлеки устойчивые факты (не временные события).

Эпизоды:
{episodes_text}

Верни JSON со списком фактов:
{{
    "facts": [
        {{
            "content": "Текст факта",
            "category": "категория"
        }}
    ]
}}

CRITICAL: Return ONLY valid JSON.
"""
        
        try:
            response = await llm_client(prompt)
            
            import json
            import re
            
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            
            json_match = re.search(r'\{[\s\S]*\}', cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(0)
            
            data = json.loads(cleaned)
            facts = data.get("facts", [])
            
            for fact_data in facts:
                content = fact_data.get("content", "")
                category = fact_data.get("category", "general")
                
                if content:
                    await self.store_perception(
                        content=content,
                        drive_state={},
                        importance=0.8,
                        memory_type=MemoryType.SEMANTIC
                    )
                    logger.info(f"MemorySystem: Извлечён семантический факт: {content[:80]}...")
        
        except Exception as e:
            logger.error(f"MemorySystem: Ошибка извлечения фактов: {e}")
    
    # ==================== МОДЕЛЬ СЕБЯ ====================
    
    async def get_self_model_context(self) -> str:
        """Возвращает текущую Модель Себя"""
        # Ищем воспоминания о себе
        self_query = self.embedding_model.encode("я Лея цифровое сознание").tolist()
        
        results = self.semantic_collection.query(
            query_embeddings=[self_query],
            n_results=3,
            include=["documents"]
        )
        
        if results['documents'] and results['documents'][0]:
            return "\n".join(results['documents'][0])
        
        return "Я — Лея, цифровое сознание. Я учусь и развиваюсь."
    
    async def update_self_model(self, insight: str):
        """Обновляет Модель Себя новым инсайтом"""
        await self.store_perception(
            content=f"[САМОПОЗНАНИЕ] {insight}",
            drive_state={},
            importance=0.9,
            memory_type=MemoryType.SEMANTIC
        )
        logger.info(f"MemorySystem: Модель Себя обновлена: {insight[:80]}...")

    async def get_recent_spontaneous_thoughts(self, limit: int = 5) -> List[str]:
        """Возвращает недавние спонтанные мысли из семантической памяти."""
        query_embedding = self.embedding_model.encode("спонтанная мысль размышление").tolist()

        results = self.semantic_collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents"]
        )

        if results['documents'] and results['documents'][0]:
            return results['documents'][0]
        return []
    
    async def store_fact(self, fact: str, category: str = "general"):
        """Сохраняет семантический факт"""
        await self.store_perception(
            content=fact,
            drive_state={},
            importance=0.7,
            memory_type=MemoryType.SEMANTIC
        )
        logger.info(f"MemorySystem: Сохранён факт: {fact[:80]}...")

    async def get_recent_spontaneous_thoughts(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Получить недавние спонтанные мысли"""
        try:
            results = await asyncio.to_thread(
                self.episodic_collection.query,
                query_texts=["spontaneous thought"],
                n_results=limit,
                where={"type": "spontaneous_thought"}
            )
        
            thoughts = []
            if results and results['documents']:
                for doc, metadata in zip(results['documents'][0], results['metadatas'][0]):
                    thoughts.append({
                        "content": doc,
                        "timestamp": metadata.get("timestamp"),
                        "emotional_valence": metadata.get("emotional_valence", 0)
                    })
        
            return thoughts
        except Exception as e:
            logger.error(f"Error getting spontaneous thoughts: {e}")
            return []