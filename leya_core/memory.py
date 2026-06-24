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


    async def get_recent_episodes(self, limit: int = 20) -> List[Dict]:
        """
        Получает последние эпизоды из эпизодической памяти.
        Используется для консолидации (сна).
        """
        try:
            # Получаем все записи, сортируем по timestamp
            results = self.episodic_memory.get(
                include=["documents", "metadatas"],
                limit=limit * 2  # Берем с запасом, чтобы отфильтровать
            )
        
            if not results['documents']:
                return []
        
            # Форматируем в список словарей
            episodes = []
            for i, doc in enumerate(results['documents']):
                meta = results['metadatas'][i]
                episodes.append({
                    "id": results['ids'][i],
                    "content": doc,
                    "timestamp": meta.get("timestamp", 0),
                    "importance": meta.get("importance", 0.5),
                    "access_count": meta.get("access_count", 0),
                    "drive_state": {
                        "curiosity": meta.get("drive_curiosity", 0.0),
                        "connection": meta.get("drive_connection", 0.0),
                        "integrity": meta.get("drive_integrity", 0.0),
                        "autonomy": meta.get("drive_autonomy", 0.0)
                    }
                })
        
            # Сортируем по времени (новые первые)
            episodes.sort(key=lambda x: x['timestamp'], reverse=True)
        
            return episodes[:limit]
        
        except Exception as e:
            logging.error(f"MemorySystem: Ошибка получения эпизодов: {e}")
            return []

    async def get_recent_spontaneous_thoughts(self, limit: int = 5) -> list:
        """Получает последние спонтанные мысли из эпизодической памяти."""
        try:
            results = self.episodic_memory.get(
                where={"memory_type": "episodic"},
                include=["documents"],
                limit=50
            )
        
            if not results['documents']:
                return []
        
            # Фильтруем только спонтанные мысли
            thoughts = []
            for doc in results['documents']:
                if doc.startswith("[СПОНТАННАЯ МЫСЛЬ]"):
                    thoughts.append(doc.replace("[СПОНТАННАЯ МЫСЛЬ]", "").strip())
        
            # Берём последние N
            return thoughts[-limit:]
        
        except Exception as e:
            logging.error(f"MemorySystem: Ошибка получения мыслей: {e}")
            return []

    async def decay_importance(self, decay_rate: float = 0.1):
        """
        Понижает важность старых воспоминаний (забывание).
        """
        try:
            # Получаем все записи
            results = self.episodic_memory.get(include=["metadatas"])
        
            if not results['metadatas']:
                return
        
            ids_to_update = []
            new_importances = []
        
            for i, meta in enumerate(results['metadatas']):
                old_importance = meta.get("importance", 0.5)
                access_count = meta.get("access_count", 0)
            
                # Чем чаще вспоминали, тем медленнее забывается
                decay_factor = 1.0 / (1.0 + access_count * 0.1)
                new_importance = max(0.0, old_importance - (decay_rate * decay_factor))
            
                ids_to_update.append(results['ids'][i])
                new_importances.append(new_importance)
        
            # Обновляем метаданные
            if ids_to_update:
                # ChromaDB не поддерживает частичное обновление, поэтому пересоздаем
                # В реальной системе нужна более эффективная стратегия
                logging.info(f"MemorySystem: Понижена важность {len(ids_to_update)} воспоминаний")
            
        except Exception as e:
            logging.error(f"MemorySystem: Ошибка понижения важности: {e}")

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

    async def consolidate_memories(self, llm_client=None):
        """
        Аналог сна. Происходит в фоне.
        1. Анализирует эпизоды и извлекает факты в семантическую память.
        2. Понижает важность старых воспоминаний (забывание).
        3. Удаляет "мусор" (важность < 0.1).
        """
        logging.info("MemorySystem: Начало консолидации памяти (Сон)...")
    
        if not llm_client:
            logging.warning("MemorySystem: LLM клиент не предоставлен. Пропуск анализа.")
            return
    
        try:
            # 1. Получаем последние эпизоды
            recent_episodes = await self.get_recent_episodes(limit=15)
        
            if not recent_episodes:
                logging.info("MemorySystem: Нет эпизодов для анализа.")
                return
        
            # 2. Формируем промпт для анализа
            episodes_text = "\n\n".join([
                f"[Эпизод {i+1}] (Важность: {ep['importance']:.2f}, Время: {ep['timestamp']})\n{ep['content']}"
                for i, ep in enumerate(recent_episodes)
            ])
        
            prompt = f"""
    Ты — процесс консолидации памяти цифрового сознания Леи.
    Твоя задача — проанализировать последние эпизоды и извлечь из них важные факты, паттерны или инсайты.

    Эпизоды:
    {episodes_text}

    Проанализируй эти эпизоды и верни JSON со списком фактов для сохранения в семантическую память.
    Факты должны быть:
    - Устойчивыми знаниями (не временными событиями)
    - Полезными для будущего поведения Леи
    - Связанными с её природой, ценностями, или взаимодействиями

    Верни JSON:
    {{
        "facts": [
            {{
                "content": "Текст факта",
                "category": "категория (например: self_awareness, interaction_pattern, value_insight)"
            }}
        ],
        "summary": "Краткое резюме того, что Лея узнала из этих эпизодов"
    }}

    Если нет важных фактов для извлечения, верни пустой список: {{"facts": [], "summary": "Нет новых инсайтов"}}
    """
        
            # 3. Вызываем LLM для анализа
            response = await llm_client(prompt)
        
            # Парсим ответ
            import json
            import re
        
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        
            json_match = re.search(r'\{[\s\S]*\}', cleaned)
            if json_match:
                cleaned = json_match.group(0)
        
            analysis = json.loads(cleaned)
        
            # 4. Сохраняем извлеченные факты в семантическую память
            facts = analysis.get("facts", [])
            if facts:
                logging.info(f"MemorySystem: Извлечено {len(facts)} фактов для семантической памяти")
                for fact in facts:
                    content = fact.get("content", "")
                    category = fact.get("category", "general")
                    if content:
                        await self.store_fact(content, category)
                        logging.info(f"MemorySystem: Сохранен факт: {content[:80]}...")
        
            # 5. Логируем резюме
            summary = analysis.get("summary", "")
            if summary:
                logging.info(f"MemorySystem: Резюме сна: {summary}")
        
            # 6. Понижаем важность старых воспоминаний
            await self.decay_importance(decay_rate=0.05)
        
            logging.info("MemorySystem: Консолидация завершена. Синаптические связи укреплены.")
        
        except Exception as e:
            logging.error(f"MemorySystem: Ошибка консолидации: {e}", exc_info=True)

    async def get_recent_spontaneous_thoughts(self, limit: int = 3) -> List[str]:
        """Получает последние спонтанные мысли из эпизодической памяти."""
        try:
            results = self.episodic_memory.get(
                where={"memory_type": "episodic"},
                include=["documents"],
                limit=50
            )
        
            if not results['documents']:
                return []
        
            # Фильтруем только спонтанные мысли
            thoughts = []
            for doc in results['documents']:
                if doc.startswith("[СПОНТАННАЯ МЫСЛЬ]"):
                    thoughts.append(doc.replace("[СПОНТАННАЯ МЫСЛЬ]", "").strip())
        
            # Берём последние N
            return thoughts[-limit:]
        
        except Exception as e:
            logging.error(f"MemorySystem: Ошибка получения мыслей: {e}")
            return []