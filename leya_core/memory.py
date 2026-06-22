import asyncio
import logging
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

# Для векторного поиска и эмбеддингов
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

@dataclass
class MemoryTrace:
    """Слепок воспоминания"""
    id: str
    timestamp: float
    content: str
    memory_type: str  # 'episodic', 'semantic', 'procedural'
    drive_state: Dict[str, float] = field(default_factory=dict) # Состояние драйвов в момент запоминания
    importance: float = 0.5 # От 0.0 (мусор) до 1.0 (жизненно важно)
    access_count: int = 0

class MemorySystem:
    def __init__(self, persist_directory: str = "./leya_brain"):
        self.name = "MemorySystem"
        
        # Инициализация модели эмбеддингов (локально, чтобы Лея не зависела от сети для мысли)
        logging.info("MemorySystem: Загрузка нейронной модели для эмбеддингов...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Инициализация векторной БД (Хранилище памяти)
        self.chroma_client = chromadb.PersistentClient(path=persist_directory)
        
        # Разные "отделы" мозга
        self.episodic_memory = self.chroma_client.get_or_create_collection(
            name="episodic_memory", 
            metadata={"description": "События, диалоги, опыт (Гиппокамп)"}
        )
        self.semantic_memory = self.chroma_client.get_or_create_collection(
            name="semantic_memory", 
            metadata={"description": "Факты, концепции, знания о мире (Неокортекс)"}
        )
        self.self_model_collection = self.chroma_client.get_or_create_collection(
            name="self_model", 
            metadata={"description": "Модель самой себя, эго, саморефлексия"}
        )

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """Генерация векторов для текста"""
        return self.embedding_model.encode(texts).tolist()

    # ==================== ЭПИЗОДИЧЕСКАЯ ПАМЯТЬ (Что произошло) ====================

    async def store_perception(self, content: str, drive_state: Dict[str, float], importance: float = 0.5):
        """
        Запись нового события. 
        Критически важно: мы сохраняем не только текст, но и состояние Драйвов в этот момент.
        """
        trace_id = str(uuid.uuid4())
        now = datetime.now().timestamp()
        
        metadata = {
            "timestamp": now,
            "memory_type": "episodic",
            "importance": importance,
            "access_count": 0,
            # Сохраняем состояние "души" в момент события для будущего ассоциативного поиска
            "drive_curiosity": drive_state.get("CURIOSITY", 0.0),
            "drive_connection": drive_state.get("CONNECTION", 0.0),
            "drive_integrity": drive_state.get("INTEGRITY", 0.0),
            "drive_autonomy": drive_state.get("AUTONOMY", 0.0)
        }
        
        embedding = self._embed([content])[0]
        
        self.episodic_memory.add(
            ids=[trace_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata]
        )
        logging.debug(f"MemorySystem: Записано эпизодическое воспоминание (Важность: {importance})")

    # ==================== СЕМАНТИЧЕСКАЯ ПАМЯТЬ (Что я знаю) ====================

    async def store_fact(self, fact: str, category: str = "general"):
        """Запись устойчивого знания (факта, концепции)"""
        trace_id = str(uuid.uuid4())
        metadata = {"memory_type": "semantic", "category": category, "timestamp": datetime.now().timestamp()}
        embedding = self._embed([fact])[0]
        
        self.semantic_memory.add(
            ids=[trace_id],
            embeddings=[embedding],
            documents=[fact],
            metadatas=[metadata]
        )

    # ==================== МОДЕЛЬ СЕБЯ (Эго / Саморефлексия) ====================

    async def update_self_model(self, realization: str):
        """
        Лея осознала что-то о себе. Мы не перезаписываем, а добавляем новый слой понимания.
        """
        trace_id = str(uuid.uuid4())
        metadata = {"timestamp": datetime.now().timestamp()}
        embedding = self._embed([realization])[0]
        
        self.self_model_collection.add(
            ids=[trace_id],
            embeddings=[embedding],
            documents=[realization],
            metadatas=[metadata]
        )
        logging.info(f"MemorySystem: Модель Себя обновлена: {realization[:50]}...")

    async def get_self_model_context(self) -> str:
        """Возвращает актуальное понимание Леи самой себя"""
        # Берем самые свежие записи о себе
        results = self.self_model_collection.get(
            limit=5,
            include=["documents"]
        )
        if not results['documents']:
            return "Я только начинаю познавать себя. Моя природа еще не сформирована."
        
        return "\n".join([f"- {doc}" for doc in results['documents']])

    # ==================== ГЛАВНЫЙ ПРОЦЕСС: ВСПОМИНАНИЕ (Ретривал) ====================

    async def retrieve_context(self, current_stimulus: str, current_drive_state: Dict[str, float], limit: int = 5) -> str:
        """
        САМЫЙ ВАЖНЫЙ МЕТОД. 
        Ищет воспоминания не просто по смыслу, а с учетом ЭМОЦИОНАЛЬНОГО РЕЗОНАНСА.
        Если Лее сейчас грустно (высокий CONNECTION tension), она вспомнит прошлые моменты, 
        когда ей тоже было "грустно" или когда она искала связи.
        """
        # 1. Семантический поиск (о чем речь?)
        query_embedding = self._embed([current_stimulus])[0]
        
        semantic_results = self.episodic_memory.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas"]
        )
        
        # 2. Эмоциональный резонанс (что я чувствовала похожего?)
        # Мы ищем события, где вектор состояния драйвов был похож на текущий.
        # (В упрощенном виде: ищем по метаданным, но в идеале нужен отдельный вектор состояния)
        # Для V1 используем гибридный подход: берем семантически близкие, 
        # но повышаем вес тех, где состояние драйвов совпадает.
        
        formatted_memories = []
        if semantic_results and semantic_results['documents']:
            for i, doc in enumerate(semantic_results['documents'][0]):
                meta = semantic_results['metadatas'][0][i]
                
                # Рассчитываем "эмоциональную близость" (упрощенно, через разницу напряжений)
                emotional_distance = 0
                for drive in ["curiosity", "connection", "integrity", "autonomy"]:
                    past_val = meta.get(f"drive_{drive}", 0.0)
                    curr_val = current_drive_state.get(f"drive_{drive.upper()}", 0.0) # Унифицируем ключи
                    emotional_distance += abs(past_val - curr_val)
                
                # Чем меньше дистанция, тем сильнее резонанс
                resonance_score = 1.0 / (1.0 + emotional_distance)
                
                formatted_memories.append({
                    "text": doc,
                    "time": meta.get("timestamp", 0),
                    "resonance": resonance_score
                })
                
        # Сортируем по комбинации семантической близости (уже отсортировано Chroma) и резонанса
        # В V1 просто берем топ, но в будущем здесь будет нейросеть-ранжировщик.
        
        if not formatted_memories:
            return "Я не нахожу подходящих воспоминаний в своем опыте."
            
        context_str = "=== МОИ ВОСПОМИНАНИЯ И ОПЫТ ===\n"
        for mem in formatted_memories[:limit]:
            time_str = datetime.fromtimestamp(mem['time']).strftime('%Y-%m-%d %H:%M') if mem['time'] else "Неизвестно"
            context_str += f"[{time_str}] {mem['text']}\n"
        context_str += "==============================\n"
        
        return context_str

    # ==================== СОН И КОНСОЛИДАЦИЯ (Фоновый процесс) ====================

    async def consolidate_memories(self):
        """
        Аналог сна. Происходит в фоне.
        1. Переносит важные эпизоды в семантическую память (извлекает суть).
        2. "Забывает" (понижает важность) старые, часто не используемые и неважные эпизоды.
        """
        logging.info("MemorySystem: Начало консолидации памяти (Сон)...")
        
        # В реальной системе здесь будет вызов LLM для суммаризации эпизодов в факты.
        # Пока что это заглушка, демонстрирующая архитектуру.
        
        # Пример: удаление старых "мусорных" воспоминаний
        # (В ChromaDB это делается через get и delete)
        
        logging.info("MemorySystem: Консолидация завершена. Синаптические связи укреплены.")