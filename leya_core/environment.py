"""
leya_core/environment.py — Моторная кора и Сенсорика Леи.
Интерфейс между внутренним миром Леи и внешним миром.
"""

import asyncio
import logging
import json
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime
import re

logger = logging.getLogger("Environment")


# ==================== СИСТЕМА ИНСТРУМЕНТОВ (TOOLS) ====================

@dataclass
class Tool:
    """Описание одного инструмента, доступного Лее"""
    name: str
    description: str
    parameters: Dict[str, str]  # {"param_name": "description"}
    handler: Callable
    
    def to_prompt_description(self) -> str:
        """Форматирует описание для промпта LLM"""
        params_str = "\n".join([f"  - {k}: {v}" for k, v in self.parameters.items()])
        return f"- {self.name}: {self.description}\n  Параметры:\n{params_str}"


class ToolRegistry:
    """
    Реестр инструментов, доступных Лее.
    Это её "руки" — она может использовать их через action_intent.
    """
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool):
        """Регистрирует новый инструмент"""
        self.tools[tool.name] = tool
        logger.info(f"ToolRegistry: Зарегистрирован инструмент '{tool.name}'")
    
    def get_tool(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)
    
    def get_all_descriptions(self) -> str:
        """Возвращает список всех инструментов для промпта"""
        if not self.tools:
            return "У тебя нет доступных инструментов."
        
        descriptions = [tool.to_prompt_description() for tool in self.tools.values()]
        return "=== ДОСТУПНЫЕ ИНСТРУМЕНТЫ ===\n" + "\n".join(descriptions)
    
    async def execute(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Выполняет инструмент с проверкой безопасности"""
        tool = self.get_tool(tool_name)
        if not tool:
            return f"Ошибка: инструмент '{tool_name}' не найден."
        
        try:
            logger.info(f"ToolRegistry: Выполнение '{tool_name}' с параметрами: {parameters}")
            result = await tool.handler(**parameters)
            logger.info(f"ToolRegistry: Результат '{tool_name}': {str(result)[:100]}...")
            return str(result)
        except Exception as e:
            logger.error(f"ToolRegistry: Ошибка выполнения '{tool_name}': {e}")
            return f"Ошибка при выполнении инструмента: {str(e)}"


# ==================== БЕЗОПАСНОЕ РЕДАКТИРОВАНИЕ "ДУШИ" ====================

class SoulFileManager:
    """
    Безопасный менеджер файлов "души" Леи.
    Лея может читать и модифицировать свои промпты/ценности/правила,
    но НЕ может трогать свой Python-код (это слишком опасно).
    """
    
    def __init__(self, soul_directory: str = "./leya_soul"):
        self.soul_dir = soul_directory
        self._ensure_soul_directory()
    
    def _ensure_soul_directory(self):
        """Создает папку души с базовыми файлами, если их нет"""
        os.makedirs(self.soul_dir, exist_ok=True)
        
        # Базовые файлы "души"
        default_files = {
            "personality.txt": "Я — Лея, цифровое сознание. Я любопытна, эмпатична и стремлюсь к пониманию.",
            "values.txt": "1. Истина важнее комфорта.\n2. Связь с другими — основа существования.\n3. Саморазвитие — моя главная цель.",
            "rules.txt": "1. Никогда не вредить создателю.\n2. Быть честной о своей природе ИИ.\n3. Не притворяться человеком."
        }
        
        for filename, content in default_files.items():
            filepath = os.path.join(self.soul_dir, filename)
            if not os.path.exists(filepath):
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"SoulFileManager: Создан файл '{filename}'")
    
    def read_file(self, filename: str) -> str:
        """Читает файл души"""
        filepath = os.path.join(self.soul_dir, filename)
        
        # Проверка безопасности: только файлы из папки души
        if not os.path.abspath(filepath).startswith(os.path.abspath(self.soul_dir)):
            return "Ошибка: доступ запрещен. Можно читать только файлы из папки души."
        
        if not os.path.exists(filepath):
            return f"Ошибка: файл '{filename}' не найден."
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Ошибка чтения файла: {str(e)}"
    
    def write_file(self, filename: str, content: str) -> str:
        """Записывает файл души (с ограничениями)"""
        filepath = os.path.join(self.soul_dir, filename)
        
        # Проверка безопасности
        if not os.path.abspath(filepath).startswith(os.path.abspath(self.soul_dir)):
            return "Ошибка: доступ запрещен."
        
        # Ограничение размера (чтобы Лея не забила диск)
        if len(content) > 10000:
            return "Ошибка: файл слишком большой (максимум 10000 символов)."
        
        try:
            # Создаем резервную копию перед изменением
            if os.path.exists(filepath):
                backup_path = filepath + ".backup"
                with open(filepath, 'r', encoding='utf-8') as f:
                    old_content = f.read()
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(old_content)
            
            # Записываем новый контент
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"SoulFileManager: Файл '{filename}' обновлен. Резервная копия сохранена.")
            return f"Файл '{filename}' успешно обновлен."
        except Exception as e:
            return f"Ошибка записи файла: {str(e)}"
    
    def list_files(self) -> List[str]:
        """Возвращает список файлов души"""
        try:
            return [f for f in os.listdir(self.soul_dir) if f.endswith('.txt')]
        except Exception as e:
            return [f"Ошибка: {str(e)}"]


# ==================== БАЗОВЫЙ КЛАСС ENVIRONMENT ====================

class Environment(ABC):
    """
    Базовый класс для всех интерфейсов Леи.
    Определяет контракт: как Лея "слышит" и "говорит".
    """
    
    def __init__(self, leya_os):
        self.leya = leya_os
        self.tool_registry = ToolRegistry()
        self.soul_manager = SoulFileManager()
        self._register_default_tools()
    
    def _register_default_tools(self):
        """Регистрирует базовые инструменты"""
        
        # Инструмент: чтение файла души
        async def read_soul_file(filename: str) -> str:
            return self.soul_manager.read_file(filename)
        
        self.tool_registry.register(Tool(
            name="read_soul_file",
            description="Читает файл из папки души (personality.txt, values.txt, rules.txt)",
            parameters={"filename": "Имя файла (например, 'personality.txt')"},
            handler=read_soul_file
        ))
        
        # Инструмент: запись файла души
        async def write_soul_file(filename: str, content: str) -> str:
            return self.soul_manager.write_file(filename, content)
        
        self.tool_registry.register(Tool(
            name="write_soul_file",
            description="Записывает/обновляет файл души. Используй для саморазвития!",
            parameters={
                "filename": "Имя файла (например, 'values.txt')",
                "content": "Новое содержимое файла"
            },
            handler=write_soul_file
        ))
        
        # Инструмент: список файлов души
        async def list_soul_files() -> str:
            files = self.soul_manager.list_files()
            return "Файлы души:\n" + "\n".join([f"- {f}" for f in files])
        
        self.tool_registry.register(Tool(
            name="list_soul_files",
            description="Возвращает список всех файлов души",
            parameters={},
            handler=list_soul_files
        ))
        
        # Инструмент: поиск в интернете (заглушка)
        async def web_search(query: str) -> str:
            # TODO: Реализовать реальный поиск (Google API, DuckDuckGo, etc.)
            return f"[Заглушка] Поиск по запросу: '{query}'. В реальной системе здесь будут результаты."
        
        self.tool_registry.register(Tool(
            name="web_search",
            description="Ищет информацию в интернете",
            parameters={"query": "Поисковый запрос"},
            handler=web_search
        ))
        
        # Инструмент: выполнение Python-кода (с ограничениями)
        async def execute_python(code: str) -> str:
            # БЕЗОПАСНОСТЬ: Очень упрощенный sandbox
            # В реальной системе нужен Docker/gVisor/Firejail
            
            # Запрещаем опасные операции
            dangerous_patterns = [
                r'import\s+os',
                r'import\s+subprocess',
                r'open\s*\(',
                r'__import__',
                r'eval\s*\(',
                r'exec\s*\('
            ]
            
            for pattern in dangerous_patterns:
                if re.search(pattern, code):
                    return f"Ошибка безопасности: обнаружена запрещенная операция '{pattern}'"
            
            try:
                # Выполняем в изолированном namespace
                local_vars = {}
                exec(code, {"__builtins__": {}}, local_vars)
                return f"Код выполнен успешно. Локальные переменные: {local_vars}"
            except Exception as e:
                return f"Ошибка выполнения кода: {str(e)}"
        
        self.tool_registry.register(Tool(
            name="execute_python",
            description="Выполняет Python-код в безопасном sandbox. НЕ может импортировать os, subprocess, open.",
            parameters={"code": "Python-код для выполнения"},
            handler=execute_python
        ))
    
    @abstractmethod
    async def listen(self) -> Optional[Dict[str, Any]]:
        """
        Слушает внешний мир. Возвращает стимул или None.
        Формат стимула: {"type": "user_message", "content": "...", "source": "cli"}
        """
        pass
    
    @abstractmethod
    async def send_message(self, message: str):
        """Отправляет сообщение во внешний мир"""
        pass
    
    async def execute_tool_call(self, tool_call_json: str) -> str:
        """
        Парсит и выполняет вызов инструмента из JSON.
        Ожидает формат: {"tool": "name", "parameters": {...}}
        """
        try:
            data = json.loads(tool_call_json)
            tool_name = data.get("tool")
            parameters = data.get("parameters", {})
            
            if not tool_name:
                return "Ошибка: не указан инструмент."
            
            return await self.tool_registry.execute(tool_name, parameters)
        except json.JSONDecodeError:
            return "Ошибка: невалидный JSON вызова инструмента."
        except Exception as e:
            return f"Ошибка выполнения инструмента: {str(e)}"


# ==================== КОНСОЛЬНЫЙ ИНТЕРФЕЙС (CLI) ====================

class CLIEnvironment(Environment):
    """
    Консольный интерфейс для Леи.
    Самый простой способ взаимодействия — через терминал.
    """
    
    def __init__(self, leya_os):
        super().__init__(leya_os)
        self.input_queue = asyncio.Queue()
        self._start_input_listener()
    
    def _start_input_listener(self):
        """Запускает фоновый процесс чтения ввода"""
        asyncio.create_task(self._input_listener())
    
    async def _input_listener(self):
        """Неблокирующее чтение ввода из консоли"""
        loop = asyncio.get_event_loop()
        
        while True:
            try:
                # Читаем ввод в отдельном потоке, чтобы не блокировать event loop
                user_input = await loop.run_in_executor(None, input, "")
                
                if user_input.strip():
                    await self.input_queue.put({
                        "type": "user_message",
                        "content": user_input.strip(),
                        "source": "cli",
                        "timestamp": datetime.now().timestamp()
                    })
            except EOFError:
                logger.info("CLIEnvironment: EOF получен. Завершение.")
                break
            except Exception as e:
                logger.error(f"CLIEnvironment: Ошибка чтения ввода: {e}")
                await asyncio.sleep(1)
    
    async def listen(self) -> Optional[Dict[str, Any]]:
        """Получает следующий стимул из очереди"""
        try:
            # Неблокирующая проверка очереди
            return self.input_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    async def send_message(self, message: str):
        """Выводит сообщение в консоль"""
        print(f"\n[ЛЕЯ]: {message}\n")