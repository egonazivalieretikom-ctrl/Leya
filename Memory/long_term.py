import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
import time
import uuid
from Core.logger import log


class LongTermMemory:
    """
    Долговременная память Leya на основе ChromaDB.
    
    Биология: Аналог гиппокампа — консолидация эпизодической памяти.
    Каждое воспоминание имеет:
    - Текст (эпизод)
    - Метаданные (эмоция, время, сила, контекст)
    - Уникальный ID (для реконструкции)
    """
    
    def __init__(self, persist_directory: str = "./leya_memory_db", collection_name: str = "leya_memories"):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        
        # Инициализация ChromaDB с отключённой телеметрией (убирает ошибки PostHog)
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Получаем или создаём коллекцию
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Leya's episodic long-term memory"}
        )
        
        total = self.collection.count()
        log.info("Long-Term Memory (ChromaDB) initialized", 
                 path=persist_directory, total_memories=total)
    
    # ========================================================================
    # СОХРАНЕНИЕ ВОСПОМИНАНИЙ
    # ========================================================================
    
    def store(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Сохраняет воспоминание в долговременную память.
        
        Args:
            text: Текст воспоминания
            metadata: Дополнительные данные (mood, type, strength, etc.)
        
        Returns:
            ID сохранённого воспоминания (для последующей реконструкции)
        """
        if metadata is None:
            metadata = {}
        
        # Генерируем уникальный ID
        memory_id = str(uuid.uuid4())
        
        # Добавляем служебные метаданные
        metadata["id"] = memory_id
        metadata["created_at"] = time.time()
        if "strength" not in metadata:
            metadata["strength"] = 0.5  # Базовая сила воспоминания
        
        try:
            self.collection.add(
                ids=[memory_id],
                documents=[text],
                metadatas=[metadata]
            )
            log.debug("Memory stored", id=memory_id, text_preview=text[:50])
            return memory_id
        except Exception as e:
            log.error("Failed to store memory", error=str(e))
            return ""
    
    # ========================================================================
    # ПОИСК ВОСПОМИНАНИЙ
    # ========================================================================
    
    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Ищет воспоминания по запросу.
        
        Returns:
            Список воспоминаний с полными метаданными (включая ID)
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            if not results or not results.get("documents"):
                return []
            
            # Собираем результаты с ID и метаданными
            memories = []
            documents = results["documents"][0]
            metadatas = results.get("metadatas", [[]])[0]
            ids = results.get("ids", [[]])[0]
            
            for i, doc in enumerate(documents):
                memory = {
                    "memory_text": doc,
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "id": ids[i] if i < len(ids) else None
                }
                memories.append(memory)
            
            return memories
            
        except Exception as e:
            log.error("Memory search failed", error=str(e))
            return []
    
    # ========================================================================
    # 🆕 ОБНОВЛЕНИЕ МЕТАДАННЫХ (для реконструкции памяти)
    # ========================================================================
    
    def update_metadata(self, memory_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Обновляет метаданные существующего воспоминания.
        
        Биология: Аналог reconsolidation — при каждом извлечении память
        становится лабильной и может быть модифицирована.
        
        Args:
            memory_id: ID воспоминания
            metadata: Новые метаданные (будут объединены с существующими)
        
        Returns:
            True если обновление прошло успешно
        """
        try:
            # Сначала получаем текущие метаданные
            existing = self.collection.get(ids=[memory_id])
            if not existing or not existing.get("metadatas"):
                log.warning("Memory not found for update", id=memory_id)
                return False
            
            # Объединяем старые и новые метаданные
            old_metadata = existing["metadatas"][0]
            merged_metadata = {**old_metadata, **metadata}
            merged_metadata["id"] = memory_id  # Сохраняем ID
            
            # Обновляем в ChromaDB
            self.collection.update(
                ids=[memory_id],
                metadatas=[merged_metadata]
            )
            
            log.debug("Memory metadata updated", 
                     id=memory_id, 
                     strength=merged_metadata.get("strength"))
            return True
            
        except Exception as e:
            log.error("Failed to update memory metadata", 
                     id=memory_id, error=str(e))
            return False
    
    # ========================================================================
    # УДАЛЕНИЕ И СБРОС
    # ========================================================================
    
    def delete(self, memory_id: str) -> bool:
        """Удаляет воспоминание по ID."""
        try:
            self.collection.delete(ids=[memory_id])
            return True
        except Exception as e:
            log.error("Failed to delete memory", id=memory_id, error=str(e))
            return False
    
    def count(self) -> int:
        """Возвращает количество воспоминаний."""
        return self.collection.count()
    
    def clear(self):
        """Полная очистка памяти (использовать с осторожностью!)."""
        try:
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "Leya's episodic long-term memory"}
            )
            log.warning("Long-term memory cleared")
        except Exception as e:
            log.error("Failed to clear memory", error=str(e))