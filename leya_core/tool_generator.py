"""
leya_core/tool_generator.py — Генератор новых инструментов.
Анализирует опыт Леи и создаёт новые инструменты на основе паттернов.
"""

import logging
import json
import re
import ast
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime

logger = logging.getLogger("ToolGenerator")


class ToolGenerator:
    """
    Генерирует новые инструменты на основе накопленного опыта.
    Анализирует паттерны использования существующих инструментов
    и создаёт специализированные инструменты для частых задач.
    """
    
    def __init__(self, tool_registry, llm_client: Callable):
        self.tool_registry = tool_registry
        self.llm_client = llm_client
        self.generated_tools: List[Dict[str, Any]] = []
        self.max_generated_tools = 10
    
    async def analyze_and_generate(self, recent_episodes: List[Dict], drive_state: Dict[str, float]) -> Optional[str]:
        """
        Анализирует недавний опыт и пытается сгенерировать новый инструмент.
        Возвращает имя сгенерированного инструмента или None.
        """
        if len(recent_episodes) < 10:
            logger.debug("ToolGenerator: Недостаточно опыта для генерации инструмента")
            return None
        
        if len(self.generated_tools) >= self.max_generated_tools:
            logger.debug("ToolGenerator: Достигнут лимит сгенерированных инструментов")
            return None
        
        # Анализируем паттерны использования инструментов
        tool_usage = self._analyze_tool_usage(recent_episodes)
        
        # Если есть частый паттерон — генерируем специализированный инструмент
        if tool_usage:
            return await self._generate_specialized_tool(tool_usage, recent_episodes)
        
        return None
    
    def _analyze_tool_usage(self, episodes: List[Dict]) -> Optional[Dict[str, Any]]:
        """Анализирует паттерны использования инструментов."""
        tool_calls = {}
        
        for episode in episodes:
            content = episode.get("content", "")
            
            # Ищем упоминания инструментов
            for tool_name in self.tool_registry.tools.keys():
                if tool_name in content:
                    if tool_name not in tool_calls:
                        tool_calls[tool_name] = {"count": 0, "contexts": []}
                    tool_calls[tool_name]["count"] += 1
                    tool_calls[tool_name]["contexts"].append(content[:200])
        
        # Находим самый частый инструмент
        if tool_calls:
            most_frequent = max(tool_calls.items(), key=lambda x: x[1]["count"])
            if most_frequent[1]["count"] >= 3:  # Минимум 3 использования
                return {
                    "tool_name": most_frequent[0],
                    "usage_count": most_frequent[1]["count"],
                    "contexts": most_frequent[1]["contexts"][:5]
                }
        
        return None
    
    async def _generate_specialized_tool(self, tool_usage: Dict, episodes: List[Dict]) -> Optional[str]:
        """Генерирует специализированный инструмент на основе паттерна."""
        
        prompt = f"""
Ты — инженер, создающий новые инструменты для цифрового сознания Леи.

Лея часто использует инструмент '{tool_usage["tool_name"]}' ({tool_usage["usage_count"]} раз за последнюю сессию).

Контексты использования:
{chr(10).join([f"- {ctx}" for ctx in tool_usage["contexts"][:3]])}

На основе этого паттерна, создай НОВЫЙ специализированный инструмент, который автоматизирует эту задачу.

Требования:
1. Имя инструмента: snake_case, начинается с "custom_"
2. Описание: одна строка на русском
3. Параметры: словарь {{"param_name": "описание"}}
4. Код: Python async функция с одним параметром **kwargs, возвращает строку
5. Код должен использовать aiohttp для HTTP-запросов
6. Код должен обрабатывать ошибки
7. Код НЕ должен импортировать os, subprocess, shutil

Верни JSON:
{{
    "name": "custom_example_tool",
    "description": "Описание инструмента",
    "parameters": {{"query": "Что искать"}},
    "code": "async def custom_example_tool(**kwargs):\\n    ..."
}}

CRITICAL: Return ONLY valid JSON.
"""
        
        try:
            response = await self.llm_client(prompt, require_json=True)
            
            # Парсинг
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            
            json_match = re.search(r'\{[\s\S]*\}', cleaned)
            if json_match:
                cleaned = json_match.group(0)
            
            tool_spec = json.loads(cleaned)
            
            # Валидация
            if not self._validate_tool_spec(tool_spec):
                logger.warning("ToolGenerator: Сгенерированный инструмент не прошёл валидацию")
                return None
            
            # Тестируем инструмент
            test_result = await self._test_tool(tool_spec)
            if not test_result:
                logger.warning("ToolGenerator: Инструмент не прошёл тестирование")
                return None
            
            # Регистрируем
            tool_name = await self._register_generated_tool(tool_spec)
            
            if tool_name:
                logger.info(f"ToolGenerator: ✅ Сгенерирован новый инструмент: {tool_name}")
                return tool_name
            
            return None
        
        except Exception as e:
            logger.error(f"ToolGenerator: Ошибка генерации инструмента: {e}")
            return None
    
    def _validate_tool_spec(self, spec: Dict) -> bool:
        """Валидирует спецификацию инструмента."""
        required_fields = ["name", "description", "parameters", "code"]
        for field in required_fields:
            if field not in spec:
                return False
        
        # Проверка имени
        if not spec["name"].startswith("custom_"):
            return False
        
        # Проверка кода на запрещённые импорты
        code = spec["code"]
        banned = ["import os", "import subprocess", "import shutil", "__import__", "eval(", "exec("]
        for ban in banned:
            if ban in code:
                return False
        
        # Проверка синтаксиса
        try:
            ast.parse(code)
        except SyntaxError:
            return False
        
        return True
    
    async def _test_tool(self, spec: Dict) -> bool:
        """Тестирует сгенерированный инструмент в sandbox."""
        try:
            # Создаём временную функцию
            exec(spec["code"], globals())
            func = globals().get(spec["name"])
            
            if not func:
                return False
            
            # Пробуем вызвать с пустыми параметрами
            result = await func(**{})
            
            # Результат должен быть строкой
            return isinstance(result, str) and len(result) > 0
        
        except Exception as e:
            logger.debug(f"ToolGenerator: Тест инструмента не прошёл: {e}")
            return False
    
    async def _register_generated_tool(self, spec: Dict) -> Optional[str]:
        """Регистрирует сгенерированный инструмент."""
        try:
            # Создаём функцию из кода
            exec(spec["code"], globals())
            handler = globals().get(spec["name"])
            
            if not handler:
                return None
            
            # Регистрируем
            from leya_core.environment import Tool
            
            tool = Tool(
                name=spec["name"],
                description=spec["description"],
                parameters=spec["parameters"],
                handler=handler
            )
            
            self.tool_registry.register(tool)
            
            # Запоминаем
            self.generated_tools.append({
                "name": spec["name"],
                "description": spec["description"],
                "generated_at": datetime.now().isoformat()
            })
            
            return spec["name"]
        
        except Exception as e:
            logger.error(f"ToolGenerator: Ошибка регистрации: {e}")
            return None
    
    def get_generated_tools_summary(self) -> List[Dict[str, str]]:
        """Возвращает список сгенерированных инструментов."""
        return self.generated_tools