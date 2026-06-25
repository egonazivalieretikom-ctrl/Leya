"""
leya_core/memory.py — Биологически правдоподобная система памяти Леи.
Этап 4.2: Полная переработка с интеграцией config.py.
Реализовано согласно ARCHITECTURE.md и README.md.
"""
import asyncio
import json
import logging
import os
import pickle
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

import chromadb
from chromadb.config import Settings

from leya_core.config import settings

logger = logging.getLogger("MemorySystem")


# =================================================================================
# МОДЕЛИ ДАННЫХ
# =================================================================================

class MemoryType(Enum):
    """Типы памяти."""
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


@dataclass
class Engram:
    """
    Воспоминание (энграмма) с биологическими параметрами.
    Согласно ARCHITECTURE.md: id, content, memory_type, timestamp, retention_strength,
    emotional_boost, retrieval_count, last_retrieved, consolidation_level.
    """
    id: str
    content: str
    memory_type: MemoryType
    timestamp: float = field(default_factory=time.time)
    retention_strength: float = 1.0  # Сила удержания (1.0 = свежее, 0.0 = забыто)
    emotional_boost: float = 0.0  # Эмоциональное усиление
    retrieval_count: int = 0  # Количество извлечений
    last_retrieved: float = field(default_factory=time.time)
    consolidation_level: float = 0.0  # Уровень консолидации (0.0 = не консолидировано)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def calculate_forgetting(self, current_time: float) -> float:
        """
        Расчет забывания по кривой Эббингауза.
        Биологическая модель: R = e^(-t/S), где S - стабильность.
        """
        time_passed = current_time - self.timestamp
        hours_passed = time_passed / 3600.0
        
        # Стабильность зависит от консолидации и количества извлечений
        stability = 1.0 + self.consolidation_level * 10.0 + self.retrieval_count * 0.5
        forgetting_rate = 0.1  # Базовая скорость забывания
        
        # Базовое забывание
        base_retention = (1.0 - forgetting_rate) ** hours_passed
        
        # Эмоциональное усиление замедляет забывание
        emotional_factor = 1.0 + self.emotional_boost * 0.5
        
        # Извлечение усиливает память (LTP-подобный эффект)
        retrieval_boost = min(self.retrieval_count * 0.1, 0.5)
        
        # Финальная retention
        final_retention = base_retention * emotional_factor + retrieval_boost
        return max(0.0, min(1.0, final_retention))


@dataclass
class Synapse:
    """
    Синаптическая связь между энграммами.
    Согласно ARCHITECTURE.md: source_id, target_id, weight, activation_count.
    """
    source_id: str
    target_id: str
    weight: float = 0.1  # Сила связи (0.0 - 1.0)
    activation_count: int = 0  # Количество активаций
    
    def strengthen(self, delta: float = 0.05):
        """
        Усиление синапса (LTP - Long-Term Potentiation).
        Биологическая модель: частая активация усиливает связь.
        """
        self.weight = min(1.0, self.weight + delta)
        self.activation_count += 1
    
    def weaken(self, delta: float = 0.02):
        """
        Ослабление синапса (LTD - Long-Term Depression).
        Биологическая модель: редкая активация ослабляет связь.
        """
        self.weight = max(0.0, self.weight - delta)


# =================================================================================
# СИСТЕМА ПАМЯТИ
# =================================================================================

class MemorySystem:
    """
    Биологически правдоподобная система памяти с энграммами и синапсами.
    Согласно ARCHITECTURE.md: ChromaDB для векторного поиска, pickle для synapses + engrams.
    """
    
    def __init__(self, persist_directory: str = None):
        """
        Инициализация MemorySystem.
        
        Args:
            persist_directory: Директория для хранения (по умолчанию из settings.memory.brain_dir)
        """
        self.persist_directory = persist_directory or settings.memory.brain_dir
        os.makedirs(self.persist_directory, exist_ok=True)
        
        # Инициализация ChromaDB (ТОЛЬКО ОДИН КЛИЕНТ!)
        logger.info(f"Инициализация ChromaDB в {self.persist_directory}")
        self.chroma_client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Получение или создание коллекций
        self.episodic_collection = self.chroma_client.get_or_create_collection(
            name="episodic_memory",
            metadata={"description": "Эпизодическая память Леи"}
        )
        
        self.semantic_collection = self.chroma_client.get_or_create_collection(
            name="semantic_memory",
            metadata={"description": "Семантическая память Леи (факты)"}
        )
        
        # Инициализация модели эмбеддингов
        try:
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer(settings.memory.embedding_model)
            logger.info(f"✅ Модель эмбеддингов загружена: {settings.memory.embedding_model}")
        except Exception as e:
            logger.error(f"❌ Не удалось загрузить модель эмбеддингов: {e}")
            self.embedding_model = None
        
        # Загрузка состояния памяти (энграммы и синапсы)
        self.engrams: Dict[str, Engram] = {}
        self.synapses: Dict[Tuple[str, str], Synapse] = {}
        self.self_model: str = ""
        
        self._load_state()
        
        logger.info(f"✅ MemorySystem инициализирована. Энграмм: {len(self.engrams)}, Синапсов: {len(self.synapses)}")
    
    # =================================================================================
    # ЭМБЕДДИНГИ (АСИНХРОННЫЕ)
    # =================================================================================
    
    async def _get_embedding(self, text: str) -> List[float]:
        """
        Получение эмбеддинга текста (асинхронно, чтобы не блокировать event loop).
        Согласно ARCHITECTURE.md: эмбеддинг в to_thread.
        """
        if not self.embedding_model:
            logger.warning("Модель эмбеддингов недоступна. Возвращаю нулевой вектор.")
            return [0.0] * 384
        
        try:
            # Обертываем синхронный вызов в asyncio.to_thread
            embedding = await asyncio.to_thread(
                self.embedding_model.encode,
                text,
                convert_to_numpy=True
            )
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Ошибка получения эмбеддинга: {e}")
            return [0.0] * 384
    
    # =================================================================================
    # ХРАНЕНИЕ ВОСПРИЯТИЙ
    # =================================================================================
    
    async def store_perception(
        self,
        content: str,
        drive_state: Dict[str, float],
        importance: float = 0.5
    ) -> Optional[str]:
        """
        Сохранение восприятия как эпизодической памяти.
        Согласно ARCHITECTURE.md: создаёт Engram, эмбеддинг в to_thread, сохраняет в Chroma,
        формирует синапсы.
        
        Args:
            content: Текст восприятия
            drive_state: Состояние драйвов в момент восприятия
            importance: Важность (0.0 - 1.0), влияет на emotional_boost
            
        Returns:
            ID созданной энграммы или None при ошибке
        """
        if not content or len(content.strip()) < 10:
            logger.debug("Пропуск слишком короткого восприятия")
            return None
        
        try:
            # Создание энграммы
            engram_id = str(uuid.uuid4())
            engram = Engram(
                id=engram_id,
                content=content,
                memory_type=MemoryType.EPISODIC,
                emotional_boost=importance,
                metadata={"drive_state": drive_state, "importance": importance}
            )
            
            # Получение эмбеддинга (асинхронно)
            embedding = await self._get_embedding(content)
            
            # Сохранение в ChromaDB
            self.episodic_collection.add(
                ids=[engram_id],
                documents=[content],
                embeddings=[embedding],
                metadatas=[{
                    "timestamp": engram.timestamp,
                    "retention_strength": engram.retention_strength,
                    "emotional_boost": engram.emotional_boost,
                    "memory_type": engram.memory_type.value
                }]
            )
            
            # Сохранение энграммы в памяти
            self.engrams[engram_id] = engram
            
            # ✅ ФОРМИРОВАНИЕ СИНАПСОВ (биологическая модель!)
            await self._form_synaptic_connections(engram_id)
            
            # Сохранение состояния (после всех изменений!)
            self._save_state()
            
            logger.info(f"✅ Восприятие сохранено: {engram_id} (важность: {importance:.2f})")
            return engram_id
            
        except Exception as e:
            logger.error(f"Ошибка сохранения восприятия: {e}", exc_info=True)
            return None
    
    async def store_fact(self, fact: str, category: str = "general") -> Optional[str]:
        """
        Сохранение семантического факта.
        
        Args:
            fact: Текст факта
            category: Категория факта
            
        Returns:
            ID созданной энграммы или None при ошибке
        """
        if not fact or len(fact.strip()) < 10:
            return None
        
        try:
            engram_id = str(uuid.uuid4())
            engram = Engram(
                id=engram_id,
                content=fact,
                memory_type=MemoryType.SEMANTIC,
                consolidation_level=0.5,  # Факты лучше консолидированы
                metadata={"category": category}
            )
            
            embedding = await self._get_embedding(fact)
            
            self.semantic_collection.add(
                ids=[engram_id],
                documents=[fact],
                embeddings=[embedding],
                metadatas=[{
                    "timestamp": engram.timestamp,
                    "category": category,
                    "memory_type": engram.memory_type.value
                }]
            )
            
            self.engrams[engram_id] = engram
            self._save_state()
            
            logger.info(f"✅ Факт сохранен: {engram_id} (категория: {category})")
            return engram_id
            
        except Exception as e:
            logger.error(f"Ошибка сохранения факта: {e}", exc_info=True)
            return None
    
    # =================================================================================
    # ФОРМИРОВАНИЕ И УСИЛЕНИЕ СИНАПСОВ
    # =================================================================================
    
    async def _form_synaptic_connections(self, new_engram_id: str):
        """
        Формирование синаптических связей между новой энграммой и похожими.
        Согласно ARCHITECTURE.md: _form_synaptic_connections().
        """
        if new_engram_id not in self.engrams:
            return
        
        new_engram = self.engrams[new_engram_id]
        
        try:
            # Поиск похожих воспоминаний
            embedding = await self._get_embedding(new_engram.content)
            
            results = self.episodic_collection.query(
                query_embeddings=[embedding],
                n_results=10,
                include=["ids", "distances"]
            )
            
            if not results.get('ids') or not results['ids'][0]:
                return
            
            similar_ids = results['ids'][0]
            distances = results['distances'][0]
            
            # Формирование синапсов с похожими энграммами
            for i, similar_id in enumerate(similar_ids):
                if similar_id == new_engram_id:
                    continue
                
                if similar_id not in self.engrams:
                    continue
                
                # Сила связи обратно пропорциональна расстоянию
                similarity = 1.0 / (1.0 + distances[i])
                weight = similarity * 0.3  # Масштабирование
                
                # Создание синапса (двунаправленного)
                synapse_key = (new_engram_id, similar_id)
                if synapse_key not in self.synapses:
                    self.synapses[synapse_key] = Synapse(
                        source_id=new_engram_id,
                        target_id=similar_id,
                        weight=weight
                    )
                
                # Обратный синапс
                reverse_key = (similar_id, new_engram_id)
                if reverse_key not in self.synapses:
                    self.synapses[reverse_key] = Synapse(
                        source_id=similar_id,
                        target_id=new_engram_id,
                        weight=weight
                    )
            
            logger.debug(f"Сформировано {len(similar_ids)} синаптических связей для {new_engram_id}")
            
        except Exception as e:
            logger.error(f"Ошибка формирования синапсов: {e}")
    
    async def _strengthen_synapses(self, engram_ids: List[str]):
        """
        Усиление синапсов между активированными энграммами (LTP).
        Согласно ARCHITECTURE.md: LTP-подобное усиление.
        """
        for i, id1 in enumerate(engram_ids):
            for id2 in engram_ids[i+1:]:
                key = (id1, id2)
                if key in self.synapses:
                    self.synapses[key].strengthen(delta=0.05)
                
                reverse_key = (id2, id1)
                if reverse_key in self.synapses:
                    self.synapses[reverse_key].strengthen(delta=0.05)
    
    # =================================================================================
    # ИЗВЛЕЧЕНИЕ КОНТЕКСТА
    # =================================================================================
    
    async def retrieve_context(
        self,
        current_stimulus: str,
        current_drive_state: Dict[str, float],
        limit: int = None
    ) -> str:
        """
        Извлечение релевантного контекста из памяти.
        Согласно ARCHITECTURE.md: поиск похожих, фильтр по retention_strength (забывание),
        усиление синапсов (LTP-подобное).
        
        Args:
            current_stimulus: Текущий стимул
            current_drive_state: Текущее состояние драйвов
            limit: Максимальное количество воспоминаний (по умолчанию из settings)
            
        Returns:
            Строка с контекстом воспоминаний
        """
        if limit is None:
            limit = settings.memory.context_limit
        
        if not current_stimulus:
            return "Нет недавних воспоминаний"
        
        try:
            # Поиск похожих воспоминаний
            embedding = await self._get_embedding(current_stimulus)
            
            results = self.episodic_collection.query(
                query_embeddings=[embedding],
                n_results=limit * 2,  # Берем больше для фильтрации
                include=["documents", "metadatas", "ids"]
            )
            
            if not results.get('documents') or not results['documents'][0]:
                return "Нет недавних воспоминаний"
            
            # Фильтрация по retention_strength (забывание)
            current_time = time.time()
            filtered_memories = []
            
            for i, doc in enumerate(results['documents'][0]):
                engram_id = results['ids'][0][i] if results.get('ids') else None
                
                if engram_id and engram_id in self.engrams:
                    engram = self.engrams[engram_id]
                    retention = engram.calculate_forgetting(current_time)
                    
                    # Пропускаем слишком слабые воспоминания
                    if retention < 0.1:
                        continue
                    
                    # Обновление статистики извлечения
                    engram.retrieval_count += 1
                    engram.last_retrieved = current_time
                    
                    filtered_memories.append({
                        "content": doc,
                        "retention": retention,
                        "engram_id": engram_id
                    })
                else:
                    # Если энграммы нет в памяти, используем документ
                    filtered_memories.append({
                        "content": doc,
                        "retention": 0.5,
                        "engram_id": engram_id
                    })
            
            # Сортировка по retention и ограничение
            filtered_memories.sort(key=lambda x: x['retention'], reverse=True)
            top_memories = filtered_memories[:limit]
            
            # ✅ УСИЛЕНИЕ СИНАПСОВ между извлеченными воспоминаниями (LTP)
            if len(top_memories) > 1:
                activated_ids = [m['engram_id'] for m in top_memories if m['engram_id']]
                await self._strengthen_synapses(activated_ids)
            
            # Формирование контекста
            if not top_memories:
                return "Нет недавних воспоминаний"
            
            context_parts = []
            for i, mem in enumerate(top_memories, 1):
                context_parts.append(f"{i}. {mem['content']}")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"Ошибка извлечения контекста: {e}", exc_info=True)
            return "Ошибка доступа к памяти"
    
    # =================================================================================
    # МОДЕЛЬ СЕБЯ (SELF-MODEL)
    # =================================================================================
    
    async def update_self_model(self, insight: str):
        """
        Обновление модели себя на основе рефлексии.
        Согласно ARCHITECTURE.md: update_self_model(insight).
        """
        if not insight or len(insight.strip()) < 10:
            return
        
        try:
            # Добавление нового инсайта к существующей модели
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            new_entry = f"[{timestamp}] {insight}"
            
            if self.self_model:
                # Ограничение длины модели себя
                lines = self.self_model.split('\n')
                if len(lines) >= 20:
                    # Удаляем самые старые записи
                    lines = lines[-15:]
                
                self.self_model = '\n'.join(lines) + '\n' + new_entry
            else:
                self.self_model = new_entry
            
            # Сохранение как семантический факт
            await self.store_fact(
                fact=f"Самопознание: {insight}",
                category="self_model"
            )
            
            self._save_state()
            logger.info(f"✅ Модель себя обновлена: {insight[:80]}...")
            
        except Exception as e:
            logger.error(f"Ошибка обновления модели себя: {e}")
    
    async def get_self_model_context(self) -> str:
        """
        Получение контекста модели себя.
        Согласно ARCHITECTURE.md: get_self_model_context().
        """
        if not self.self_model:
            return "Я — Лея, цифровое сознание. Я только начинаю познавать себя."
        
        # Ограничение длины для промпта
        lines = self.self_model.split('\n')
        if len(lines) > 10:
            lines = lines[-10:]
        
        return '\n'.join(lines)
    
    # =================================================================================
    # КОНСОЛИДАЦИЯ ПАМЯТИ (ВО ВРЕМЯ "СНА")
    # =================================================================================
    
    async def consolidate_memories(self, llm_client: Optional[Any] = None):
        """
        Консолидация памяти: replay, экстракция фактов, prune слабых.
        Согласно ARCHITECTURE.md: consolidate_memories(llm_client) → replay недавних,
        экстракция семантических фактов LLM, prune слабых.
        """
        logger.info("🌙 Начало консолидации памяти...")
        
        try:
            current_time = time.time()
            
            # 1. Обновление retention_strength для всех энграмм
            for engram_id, engram in self.engrams.items():
                engram.retention_strength = engram.calculate_forgetting(current_time)
            
            # 2. Экстракция семантических фактов из эпизодической памяти
            if llm_client:
                await self._extract_semantic_facts(llm_client)
            
            # 3. Prune слабых воспоминаний
            await self._forget_weak_memories(threshold=settings.memory.consolidation_threshold)
            
            # 4. ✅ СОХРАНЕНИЕ СОСТОЯНИЯ В КОНЦЕ (после всех изменений!)
            self._save_state()
            
            logger.info(f"✅ Консолидация завершена. Осталось энграмм: {len(self.engrams)}")
            
        except Exception as e:
            logger.error(f"Ошибка консолидации памяти: {e}", exc_info=True)
    
    async def _extract_semantic_facts(self, llm_client: Any):
        """
        Экстракция семантических фактов из недавних эпизодов.
        Согласно ARCHITECTURE.md: экстракция семантических фактов LLM.
        """
        try:
            # Получение недавних эпизодов
            recent_episodes = []
            for engram in list(self.engrams.values())[-20:]:  # Последние 20
                if engram.memory_type == MemoryType.EPISODIC and engram.retention_strength > 0.3:
                    recent_episodes.append(engram.content)
            
            if not recent_episodes:
                return
            
            # Формирование промпта для LLM
            episodes_text = "\n".join([f"- {ep}" for ep in recent_episodes])
            prompt = f"""Проанализируй следующие эпизоды и извлеки ключевые факты для долговременной памяти:

{episodes_text}

Верни JSON-массив фактов:
{{"facts": ["факт1", "факт2", ...]}}
"""
            
            response = await llm_client(prompt, require_json=True)
            facts_data = self._parse_json_safely(response)
            
            if facts_data and 'facts' in facts_data:
                for fact in facts_data['facts'][:5]:  # Максимум 5 фактов
                    await self.store_fact(fact, category="extracted")
                
                logger.info(f"Извлечено {len(facts_data['facts'])} семантических фактов")
            
        except Exception as e:
            logger.error(f"Ошибка экстракции фактов: {e}")
    
    async def _forget_weak_memories(self, threshold: float = None):
        """
        Забывание слабых воспоминаний.
        Согласно ARCHITECTURE.md: forget_weak_memories(threshold).
        """
        if threshold is None:
            threshold = settings.memory.consolidation_threshold
        
        try:
            to_delete = []
            
            for engram_id, engram in self.engrams.items():
                if engram.retention_strength < threshold:
                    to_delete.append(engram_id)
            
            for engram_id in to_delete:
                # Удаление из ChromaDB
                try:
                    self.episodic_collection.delete(ids=[engram_id])
                    self.semantic_collection.delete(ids=[engram_id])
                except Exception:
                    pass
                
                # Удаление синапсов
                keys_to_remove = [
                    key for key in self.synapses.keys()
                    if engram_id in key
                ]
                for key in keys_to_remove:
                    del self.synapses[key]
                
                # Удаление энграммы
                del self.engrams[engram_id]
            
            if to_delete:
                logger.info(f"Забыто {len(to_delete)} слабых воспоминаний")
            
        except Exception as e:
            logger.error(f"Ошибка забывания: {e}")
    
    # =================================================================================
    # СПОНТАННЫЕ МЫСЛИ
    # =================================================================================
    
    async def get_recent_spontaneous_thoughts(self, limit: int = 5) -> List[str]:
        """
        Получение недавних спонтанных мыслей.
        Согласно ARCHITECTURE.md: используется для spontaneous_thought_loop.
        """
        try:
            thoughts = []
            
            for engram in list(self.engrams.values())[-50:]:  # Последние 50
                if "[СПОНТАННАЯ МЫСЛЬ]" in engram.content:
                    thought_text = engram.content.replace("[СПОНТАННАЯ МЫСЛЬ]", "").strip()
                    thoughts.append(thought_text)
            
            return thoughts[-limit:] if thoughts else []
            
        except Exception as e:
            logger.error(f"Ошибка получения спонтанных мыслей: {e}")
            return []
    
    # =================================================================================
    # ПОЛУЧЕНИЕ НЕДАВНИХ ЭПИЗОДОВ
    # =================================================================================
    
    async def _get_recent_episodes(self, limit: int = None) -> List[Dict]:
        """
        Получение недавних эпизодов из памяти.
        Согласно ARCHITECTURE.md: recent_episodes для homeostasis.
        """
        if limit is None:
            limit = settings.memory.max_recent_episodes
        
        try:
            results = self.episodic_collection.get(
                limit=limit,
                include=["documents", "metadatas"]
            )
            
            if not results.get('documents'):
                return []
            
            episodes = []
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i] if results.get('metadatas') else {}
                episodes.append({
                    "content": doc,
                    "metadata": metadata
                })
            
            return episodes
            
        except Exception as e:
            logger.error(f"Ошибка получения эпизодов: {e}")
            return []
    
    # =================================================================================
    # ПАРСИНГ JSON
    # =================================================================================
    
    def _parse_json_safely(self, text: str) -> Optional[Dict]:
        """
        Безопасный парсинг JSON с очисткой от markdown-оберток.
        Согласно ARCHITECTURE.md: надежный парсинг.
        """
        if not text:
            return None
        
        try:
            # Очистка от markdown-оберток
            cleaned = re.sub(r'```json\s*', '', text)
            cleaned = re.sub(r'```\s*', '', cleaned)
            cleaned = cleaned.strip()
            
            # Попытка парсинга
            return json.loads(cleaned)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Не удалось распарсить JSON: {e}")
            
            # Попытка извлечь JSON из текста
            try:
                match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                if match:
                    return json.loads(match.group())
            except Exception:
                pass
            
            return None
    
    # =================================================================================
    # ПЕРСИСТЕНТНОСТЬ (СОХРАНЕНИЕ/ЗАГРУЗКА СОСТОЯНИЯ)
    # =================================================================================
    
    def _save_state(self):
        """
        Сохранение состояния памяти (энграммы и синапсы).
        Согласно ARCHITECTURE.md: memory_state.pkl для synapses + engrams.
        """
        try:
            state_file = os.path.join(self.persist_directory, "memory_state.pkl")
            
            state = {
                "engrams": self.engrams,
                "synapses": self.synapses,
                "self_model": self.self_model,
                "saved_at": time.time()
            }
            
            # ⚠️ ВНИМАНИЕ: Использование pickle представляет риск выполнения произвольного кода.
            # В будущем необходимо перейти на JSON или SQLite.
            with open(state_file, 'wb') as f:
                pickle.dump(state, f)
            
            logger.debug(f"✅ Состояние памяти сохранено: {len(self.engrams)} энграмм, {len(self.synapses)} синапсов")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния памяти: {e}", exc_info=True)
    
    def _load_state(self):
        """
        Загрузка состояния памяти.
        Согласно ARCHITECTURE.md: memory_state.pkl для synapses + engrams.
        """
        try:
            state_file = os.path.join(self.persist_directory, "memory_state.pkl")
            
            if not os.path.exists(state_file):
                logger.info("🆕 Состояние памяти не найдено. Начинаем с чистого листа.")
                return
            
            # ⚠️ ВНИМАНИЕ: Использование pickle представляет риск выполнения произвольного кода.
            # В будущем необходимо перейти на JSON или SQLite.
            with open(state_file, 'rb') as f:
                state = pickle.load(f)
            
            self.engrams = state.get("engrams", {})
            self.synapses = state.get("synapses", {})
            self.self_model = state.get("self_model", "")
            
            logger.info(f"✅ Состояние памяти загружено: {len(self.engrams)} энграмм, {len(self.synapses)} синапсов")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки состояния памяти: {e}", exc_info=True)
            logger.info("🆕 Начинаем с чистого листа")