import uuid
import time
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from Core.logger import log

class LongTermMemory:
    """
    Долгосрочная векторная память (Жесткий диск мозга).
    Использует ChromaDB для семантического поиска по прошлому опыту.
    """
    
    def __init__(self, db_path: str = "./leya_memory_db"):
        # 1. Настраиваем отключение телеметрии
        settings = Settings(anonymized_telemetry=False)
        
        # 2. Инициализируем клиент ChromaDB с правильными настройками
        self.client = chromadb.PersistentClient(path=db_path, settings=settings)
        
        # 3. Создаем или получаем коллекцию "опыта"
        # Метрика "cosine" отлично подходит для сравнения смысловой близости текстов
        self.collection = self.client.get_or_create_collection(
            name="leya_experiences",
            metadata={"hnsw:space": "cosine"}
        )
        
        log.info("Long-Term Memory (ChromaDB) initialized", path=db_path, total_memories=self.collection.count())

    def store(self, text: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Сохранить новое воспоминание.
        ChromaDB автоматически создаст эмбеддинг (вектор) для текста.
        """
        if not metadata:
            metadata = {}
            
        metadata["timestamp"] = time.time()
        
        try:
            self.collection.add(
                documents=[text],
                metadatas=[metadata],
                ids=[str(uuid.uuid4())]
            )
            log.debug("Stored in LTM", text_preview=text[:50] + "...", metadata=metadata)
        except Exception as e:
            log.error("Failed to store memory", error=str(e))

    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Вспомнить что-то, основываясь на запросе (семантический поиск).
        Возвращает список воспоминаний, отсортированных по релевантности.
        """
        if self.collection.count() == 0:
            return []

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            formatted_memories = []
            if results and results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    formatted_memories.append({
                        "memory_text": doc,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "relevance_distance": results['distances'][0][i] if results['distances'] else 1.0
                    })
            return formatted_memories
            
        except Exception as e:
            log.error("Failed to search memory", error=str(e))
            return []

    async def consolidate(self, context: List[Dict[str, Any]], cycle_id: int):
        """
        Метод вызывается в фазе LEARN когнитивного цикла.
        Анализирует краткосрочный контекст и решает, что стоит запомнить навсегда.
        """
        log.debug("Consolidating memories...", context_items=len(context))
        
        for event in context:
            if not isinstance(event, dict):
                continue
                
            importance = event.get("importance", 0.0)
            event_type = event.get("type", "unknown")
            
            if importance > 0.7 or event_type in ["user_command", "major_discovery", "error"]:
                text_to_remember = str(event.get("content", event))
                self.store(
                    text=text_to_remember, 
                    metadata={
                        "cycle_id": cycle_id, 
                        "type": event_type,
                        "importance": importance
                    }
                )