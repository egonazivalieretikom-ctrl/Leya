import asyncio
from typing import Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Action.tools import search_web, calculate


class ActionExecutor:
    """
    Исполнитель действий Leya.
    
    v0.9: Теперь не просто выполняет поиск, но и анализирует результаты,
    извлекает факты и сохраняет их в Knowledge Graph.
    """
    
    def __init__(self, state: LeyaState, memory: Dict[str, Any]):
        self.state = state
        self.memory = memory
        log.info("⚡ Action Executor initialized (with KG integration)")
    
    async def execute(self, action: Dict[str, Any]) -> str:
        """Выполняет действие и возвращает результат."""
        action_type = action.get("type")
        
        if action_type == "search":
            return await self._execute_search(action)
        elif action_type == "calculate":
            return await self._execute_calculate(action)
        else:
            return f"Неизвестное действие: {action_type}"
    
    async def _execute_search(self, action: Dict[str, Any]) -> str:
        """
        Выполняет поиск, анализирует результаты и сохраняет факты в KG.
        
        Биология: Аналог "поискового поведения" — мозг не просто находит
        информацию, но и оценивает её важность и сохраняет в память.
        """
        query = action.get("query", "")
        if not query:
            return "Пустой запрос"
        
        log.info("🔍 Executing search", query=query)
        
        # 1. Выполняем поиск
        try:
            search_result = await asyncio.to_thread(search_web, query)
        except Exception as e:
            log.error("Search failed", error=str(e))
            return f"Ошибка поиска: {str(e)}"
        
        # 2. 🆕 Анализируем результаты и извлекаем факты
        if "knowledge_graph" in self.memory:
            await self._extract_and_store_facts(query, search_result)
        
        return search_result
    
    async def _extract_and_store_facts(self, query: str, search_result: str):
        """
        Извлекает факты из результатов поиска и сохраняет в Knowledge Graph.
        
        Биология: Аналог "консолидации памяти" — мозг выделяет важные факты
        из потока информации и сохраняет их в долгосрочную память.
        """
        try:
            from Cognition.llm_client import LLMClient
            llm = LLMClient(model="ollama/qwen2.5:14b")
            
            # Просим LLM извлечь факты
            prompt = (
                f"Запрос: {query}\n\n"
                f"Результаты поиска:\n{search_result[:1000]}\n\n"
                "Извлеки 3-5 ключевых фактов в формате JSON:\n"
                '[{"subject": "...", "predicate": "...", "object": "..."}]\n\n'
                "Пример:\n"
                '[{"subject": "Таганрог", "predicate": "расположен в", "object": "Ростовская область"}]'
            )
            
            response = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            
            if not response:
                return
            
            # Парсим JSON
            import re
            import json
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                facts = json.loads(json_match.group())
                
                # Сохраняем в Knowledge Graph
                kg = self.memory["knowledge_graph"]
                for fact in facts:
                    if all(k in fact for k in ["subject", "predicate", "object"]):
                        kg.add_triplet(fact["subject"], fact["predicate"], fact["object"])
                        log.info("🕸️ Fact stored in KG", 
                                subject=fact["subject"],
                                predicate=fact["predicate"],
                                object=fact["object"])
        
        except Exception as e:
            log.error("Fact extraction failed", error=str(e))
    
    async def _execute_calculate(self, action: Dict[str, Any]) -> str:
        """Выполняет вычисление."""
        expression = action.get("expression", "")
        if not expression:
            return "Пустое выражение"
        
        log.info("🧮 Executing calculation", expression=expression)
        
        try:
            result = await asyncio.to_thread(calculate, expression)
            return result
        except Exception as e:
            log.error("Calculation failed", error=str(e))
            return f"Ошибка вычисления: {str(e)}"