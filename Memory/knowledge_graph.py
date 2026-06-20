import json
import networkx as nx
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from Core.logger import log

class KnowledgeGraph:
    """
    Символическая память Leya.
    Хранит факты о мире в виде графа (Субъект -> Предикат -> Объект).
    """
    
    def __init__(self, db_path: str = "./leya_knowledge_graph.json"):
        self.db_path = Path(db_path)
        self.graph = nx.DiGraph()
        self._load()
        log.info("🕸️ Knowledge Graph initialized", nodes=self.graph.number_of_nodes(), edges=self.graph.number_of_edges())
    
    def _load(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.graph = nx.node_link_graph(data)
            except Exception as e:
                log.error("Failed to load Knowledge Graph", error=str(e))
    
    def _save(self):
        try:
            data = nx.node_link_data(self.graph)
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error("Failed to save Knowledge Graph", error=str(e))
    
    def add_triplet(self, subject: str, predicate: str, obj: str):
        """Добавляет факт: (Владислав) -[создатель]-> (Leya)"""
        self.graph.add_edge(subject, obj, relation=predicate)
        self._save()
        log.debug("KG triplet added", s=subject, p=predicate, o=obj)
    
    def query(self, subject: Optional[str] = None, predicate: Optional[str] = None, obj: Optional[str] = None) -> List[Dict]:
        """Запрос к графу. Можно указать любой параметр."""
        results = []
        for u, v, data in self.graph.edges(data=True):
            if subject and u != subject:
                continue
            if obj and v != obj:
                continue
            if predicate and data.get('relation') != predicate:
                continue
            results.append({"subject": u, "predicate": data.get('relation'), "object": v})
        return results
    
    def get_context_for(self, entity: str, max_hops: int = 2) -> str:
        """Возвращает все известные факты о сущности (для инъекции в LLM)."""
        facts = []
        # Прямые связи
        for _, v, data in self.graph.edges(entity, data=True):
            facts.append(f"{entity} {data.get('relation')} {v}")
        for u, _, data in self.graph.in_edges(entity, data=True):
            facts.append(f"{u} {data.get('relation')} {entity}")
        
        if not facts:
            return "Нет известных фактов."
        return "\n".join(facts[:10])  # Ограничиваем контекст