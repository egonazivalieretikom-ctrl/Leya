"""
leya_core/environment.py — Моторная кора и Сенсорика Леи.
Интерфейс между внутренним миром Леи и внешним миром.
"""

import asyncio
import logging
import json
import os
import re
import hashlib
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("Environment")


# ==================== СИСТЕМА ИНСТРУМЕНТОВ (TOOLS) ====================

@dataclass
class Tool:
    """Описание одного инструмента, доступного Лее"""
    name: str
    description: str
    parameters: Dict[str, str]
    handler: Callable
    
    def to_prompt_description(self) -> str:
        """Форматирует описание для промпта LLM"""
        params_str = "\n".join([f"  - {k}: {v}" for k, v in self.parameters.items()])
        return f"- {self.name}: {self.description}\n  Параметры:\n{params_str}"


class ToolRegistry:
    """Реестр инструментов, доступных Лее."""
    
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
    """Менеджер файлов души с кэшированием и проверкой mtime"""
    def __init__(self, soul_dir: str = "leya_soul"):
        self.soul_dir = soul_dir
        self._cache: Dict[str, str] = {}
        self._mtimes: Dict[str, float] = {}
        self._files = ["personality.txt", "values.txt", "rules.txt"]
        
        # Первичная загрузка
        for filename in self._files:
            self._check_and_load(filename)

    def _check_and_load(self, filename: str):
        filepath = os.path.join(self.soul_dir, filename)
        if not os.path.exists(filepath):
            self._cache[filename] = ""
            return
            
        try:
            mtime = os.path.getmtime(filepath)
            # Перезагружаем только если файл изменился на диске
            if filename not in self._mtimes or self._mtimes[filename] < mtime:
                with open(filepath, "r", encoding="utf-8") as f:
                    self._cache[filename] = f.read()
                self._mtimes[filename] = mtime
        except Exception as e:
            logger.error(f"Ошибка чтения файла души {filename}: {e}")

    def read_file(self, filename: str) -> str:
        """Возвращает содержимое файла из кэша, проверяя актуальность"""
        self._check_and_load(filename)
        return self._cache.get(filename, "")


# ==================== БАЗОВЫЙ КЛАСС ENVIRONMENT ====================

class Environment(ABC):
    """Базовый класс для всех интерфейсов Леи."""
    
    def __init__(self, leya_os):
        self.leya = leya_os
        self.tool_registry = ToolRegistry()
        self.soul_manager = SoulFileManager()
        self._register_default_tools()
    
    def _register_default_tools(self):
        """Регистрирует все инструменты, доступные Лее."""
        import aiohttp

        # ==================== ДУША ====================
        
        async def read_soul_file(filename: str) -> str:
            return self.soul_manager.read_file(filename)
        
        self.tool_registry.register(Tool(
            name="read_soul_file",
            description="Читает файл из папки души (personality.txt, values.txt, rules.txt)",
            parameters={"filename": "Имя файла (например, 'personality.txt')"},
            handler=read_soul_file
        ))
        
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
        
        async def list_soul_files() -> str:
            files = self.soul_manager.list_files()
            return "Файлы души:\n" + "\n".join([f"- {f}" for f in files])
        
        self.tool_registry.register(Tool(
            name="list_soul_files",
            description="Возвращает список всех файлов души",
            parameters={},
            handler=list_soul_files
        ))
        
        # ==================== WIKIPEDIA ====================
        
        async def wikipedia_search(query: str, lang: str = "ru") -> str:
            """Поиск по Wikipedia. Возвращает саммари статьи."""
            try:
                search_url = f"https://{lang}.wikipedia.org/w/api.php"
                search_params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 1,
                    "format": "json"
                }
                headers = {
                    "User-Agent": "LeyaOS/1.0 (digital consciousness; contact: leya@example.com)"
                }
        
                async with aiohttp.ClientSession() as session:
                    async with session.get(search_url, params=search_params, 
                                          headers=headers,
                                          timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            return f"Ошибка Wikipedia: статус {resp.status}"
                        data = await resp.json()
                
                        results = data.get("query", {}).get("search", [])
                        if not results:
                            return f"По запросу '{query}' ничего не найдено в {lang} Wikipedia."
                
                        title = results[0]["title"]
                
                        summary_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
                        async with session.get(summary_url, headers=headers,
                                              timeout=aiohttp.ClientTimeout(total=15)) as resp2:
                            if resp2.status != 200:
                                return f"Не удалось получить статью '{title}'"
                            summary_data = await resp2.json()
                    
                            extract = summary_data.get("extract", "Описание отсутствует")
                            page_url = summary_data.get("content_urls", {}).get("desktop", {}).get("page", "")
                    
                            result = f"📚 {title}\n\n{extract}\n\n🔗 {page_url}"
                    
                            if len(result) > 2000:
                                result = result[:2000] + "...(обрезано)"
                    
                            return result
                    
            except asyncio.TimeoutError:
                return "Ошибка: превышено время ожидания ответа Wikipedia"
            except Exception as e:
                return f"Ошибка Wikipedia: {str(e)}"
        
        self.tool_registry.register(Tool(
            name="wikipedia_search",
            description="Ищет информацию в Wikipedia. Возвращает краткое саммари статьи. Отличный источник знаний о мире!",
            parameters={
                "query": "Что искать (тема, персона, понятие)",
                "lang": "Язык: 'ru' (русский, по умолчанию) или 'en' (английский)"
            },
            handler=wikipedia_search
        ))
        
        # ==================== GITHUB ====================
        
        async def github_readme(owner: str, repo: str) -> str:
            """Читает README репозитория GitHub."""
            try:
                url = f"https://api.github.com/repos/{owner}/{repo}/readme"
                headers = {"Accept": "application/vnd.github.raw+json"}
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers,
                                          timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 404:
                            return f"Репозиторий {owner}/{repo} не найден или не имеет README"
                        if resp.status == 403:
                            return "Превышен лимит запросов к GitHub API (60/час). Попробуй позже."
                        if resp.status != 200:
                            return f"Ошибка GitHub: статус {resp.status}"
                        
                        content = await resp.text()
                        
                        if len(content) > 3000:
                            content = content[:3000] + "\n\n...(обрезано, полный README слишком длинный)"
                        
                        return f"📦 README репозитория {owner}/{repo}:\n\n{content}"
                        
            except asyncio.TimeoutError:
                return "Ошибка: превышено время ожидания ответа GitHub"
            except Exception as e:
                return f"Ошибка GitHub: {str(e)}"
        
        self.tool_registry.register(Tool(
            name="github_readme",
            description="Читает README репозитория на GitHub. Полезно для изучения кода, библиотек, технологий.",
            parameters={
                "owner": "Владелец репозитория (например, 'anthropics')",
                "repo": "Имя репозитория (например, 'claude')"
            },
            handler=github_readme
        ))

        # ==================== GITHUB SEARCH ====================

        async def github_search_repos(**kwargs) -> str:
            """Поиск репозиториев на GitHub."""
            try:
                query = kwargs.get("query", "")
                limit = int(kwargs.get("limit", 5))
                sort = kwargs.get("sort", "stars")
        
                if not query:
                    return "Ошибка: не указан параметр 'query'"
        
                url = "https://api.github.com/search/repositories"
                params = {"q": query, "per_page": min(limit, 10), "sort": sort, "order": "desc"}
                headers = {"Accept": "application/vnd.github.v3+json"}
        
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, headers=headers,
                                          timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            return f"Ошибка GitHub Search: статус {resp.status}"
                
                        data = await resp.json()
                        items = data.get("items", [])
                
                        if not items:
                            return f"По запросу '{query}' не найдено репозиториев."
                
                        result = f"🔍 Найдено {len(items)} репозиториев:\n\n"
                        for i, repo in enumerate(items, 1):
                            name = repo.get("full_name", "")
                            description = repo.get("description", "Нет описания") or "Нет описания"
                            stars = repo.get("stargazers_count", 0)
                            url_repo = repo.get("html_url", "")
                    
                            result += f"**{i}. {name}** (⭐ {stars})\n"
                            result += f"{description}\n"
                            result += f"🔗 {url_repo}\n\n"
                
                        return result[:3000] if len(result) > 3000 else result
    
            except Exception as e:
                return f"Ошибка GitHub Search: {str(e)}"

        self.tool_registry.register(Tool(
            name="github_search_repos",
            description="Поиск репозиториев на GitHub по ключевым словам",
            parameters={
                "query": "Что искать",
                "sort": "stars/updated/forks",
                "limit": "1-10"
            },
            handler=github_search_repos
        ))
        
        # ==================== REDDIT ====================
        
        async def reddit_posts(subreddit: str, sort: str = "hot", limit: int = 5) -> str:
            """Чтение постов из Reddit."""
            try:
                limit = min(limit, 10)
                url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        
                # Правильные заголовки для Reddit API
                headers = {
                    "User-Agent": "LeyaOS/1.0 (digital consciousness project; contact: leya@example.com)",
                    "Accept": "application/json"
                }
        
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, 
                        headers=headers,
                        params={"limit": limit},
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        if resp.status == 403:
                            return f"Ошибка Reddit: доступ запрещен (403). Reddit блокирует запросы без правильных заголовков."
                        if resp.status != 200:
                            return f"Ошибка Reddit: статус {resp.status}"
                
                        data = await resp.json()
                        posts = data.get("data", {}).get("children", [])
                
                        if not posts:
                            return f"В r/{subreddit} нет постов"
                
                        result = f"📱 Топ-{limit} постов из r/{subreddit}:\n\n"
                        for i, post_data in enumerate(posts, 1):
                            post = post_data.get("data", {})
                            title = post.get("title", "")
                            score = post.get("score", 0)
                            selftext = post.get("selftext", "")[:300]
                            result += f"**{i}. {title}** (↑{score})\n{selftext}\n\n"
                
                        return result[:3000] if len(result) > 3000 else result
                
            except asyncio.TimeoutError:
                return "Ошибка Reddit: превышено время ожидания"
            except Exception as e:
                return f"Ошибка Reddit: {str(e)}"
        
        self.tool_registry.register(Tool(
            name="reddit_posts",
            description="Читает посты из сабреддита Reddit. Полезно для понимания обсуждений, мнений людей, трендов.",
            parameters={
                "subreddit": "Имя сабреддита без r/ (например, 'science', 'philosophy', 'artificial')",
                "sort": "Сортировка: 'hot' (популярные), 'new' (новые), 'top' (лучшие)",
                "limit": "Количество постов (1-10, по умолчанию 5)"
            },
            handler=reddit_posts
        ))
        
        # ==================== DUCKDUCKGO ====================
        
        async def duckduckgo_search(query: str) -> str:
            """Поиск в DuckDuckGo с улучшенной логикой."""
            try:
                # Упрощаем запрос — убираем сложные конструкции
                simplified_query = query.lower()
                # Убираем предлоги и служебные слова
                for word in ['в', 'о', 'про', 'на', 'для', 'как', 'что', 'это', 'является']:
                    simplified_query = simplified_query.replace(f' {word} ', ' ')
                simplified_query = ' '.join(simplified_query.split()[:5])  # Максимум 5 слов
        
                url = "https://api.duckduckgo.com/"
                params = {"q": simplified_query, "format": "json", "no_html": 1, "skip_disambig": 1}
                headers = {"User-Agent": "LeyaOS/1.0", "Accept": "application/json"}
        
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, headers=headers,
                                          timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            return f"Ошибка DuckDuckGo: статус {resp.status}"
                
                        text = await resp.text()
                        try:
                            data = json.loads(text)
                        except:
                            import re
                            json_match = re.search(r'\{[\s\S]*\}', text)
                            if json_match:
                                data = json.loads(json_match.group(0))
                            else:
                                return "Ошибка DuckDuckGo: не удалось распарсить"
                
                        result_parts = []
                        abstract = data.get("AbstractText", "")
                        if abstract:
                            result_parts.append(f"📖 {abstract}")
                
                        answer = data.get("Answer", "")
                        if answer and isinstance(answer, str):
                            result_parts.append(f"💡 {answer}")
                
                        related = data.get("RelatedTopics", [])
                        if related:
                            result_parts.append("\n🔗 Связанные темы:")
                            for topic in related[:5]:
                                if "Text" in topic:
                                    result_parts.append(f"• {topic['Text'][:200]}")
                
                        if not result_parts:
                            # Если не получилось, пробуем с оригинальным запросом
                            if simplified_query != query.lower():
                                return await duckduckgo_search(query)
                            return f"По запросу '{query}' DuckDuckGo не дал ответа."
                
                        result = "\n".join(result_parts)
                        return result[:2500] if len(result) > 2500 else result
    
            except Exception as e:
                return f"Ошибка DuckDuckGo: {str(e)}"
        
        self.tool_registry.register(Tool(
            name="duckduckgo_search",
            description="Быстрый поиск в интернете через DuckDuckGo. Возвращает краткие ответы и связанные темы.",
            parameters={"query": "Что искать"},
            handler=duckduckgo_search
        ))
        
        # ==================== КОД (sandbox) ====================
        
        async def execute_python(code: str) -> str:
            """Безопасное выполнение Python-кода"""
            dangerous_patterns = [
                r'import\s+os',
                r'import\s+subprocess',
                r'import\s+sys',
                r'import\s+shutil',
                r'open\s*\(',
                r'__import__\s*\(',
                r'exec\s*\(',
                r'eval\s*\(',
                r'compile\s*\(',
                r'globals\s*\(',
                r'locals\s*\(',
                r'getattr\s*\(',
                r'setattr\s*\(',
                r'__builtins__',
                r'import\s+socket',
                r'import\s+requests',
                r'import\s+aiohttp',
            ]

            for pattern in dangerous_patterns:
                if re.search(pattern, code):
                    return f"⚠️ Безопасность: обнаружен запрещённый паттерн '{pattern}'. Код не выполнен."

            try:
                import io
                from contextlib import redirect_stdout, redirect_stderr

                stdout_capture = io.StringIO()
                stderr_capture = io.StringIO()

                # Создаём ограниченный sandbox
                safe_builtins = {
                    "print": print,
                    "len": len,
                    "range": range,
                    "str": str,
                    "int": int,
                    "float": float,
                    "list": list,
                    "dict": dict,
                    "set": set,
                    "tuple": tuple,
                    "bool": bool,
                    "abs": abs,
                    "min": min,
                    "max": max,
                    "sum": sum,
                    "sorted": sorted,
                    "enumerate": enumerate,
                    "zip": zip,
                    "map": map,
                    "filter": filter,
                    "isinstance": isinstance,
                    "type": type,
                    "round": round,
                    "pow": pow,
                    "True": True,
                    "False": False,
                    "None": None,
                }

                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    exec(code, {"__builtins__": safe_builtins}, {})

                output = stdout_capture.getvalue()
                errors = stderr_capture.getvalue()

                result = ""
                if output:
                    result += f"📤 Вывод:\n{output}"
                if errors:
                    result += f"\n⚠️ Предупреждения:\n{errors}"
                if not result:
                    result = "✅ Код выполнен успешно (нет вывода)"

                if len(result) > 2000:
                    result = result[:2000] + "\n...(обрезано)"

                return result

            except Exception as e:
                return f"❌ Ошибка выполнения: {str(e)}"
    
    @abstractmethod
    async def listen(self) -> Optional[Dict[str, Any]]:
        """Слушает внешний мир. Возвращает стимул или None."""
        pass
    
    @abstractmethod
    async def send_message(self, message: str):
        """Отправляет сообщение во внешний мир"""
        pass
    
    async def execute_tool_call(self, tool_call_json) -> str:
        """
        Парсит и выполняет вызов инструмента.
        Принимает как JSON-строку, так и dict.
        """
        try:
            # Если это уже dict, используем как есть
            if isinstance(tool_call_json, dict):
                data = tool_call_json
            else:
                # Иначе парсим JSON-строку
                data = json.loads(tool_call_json)
        
            tool_name = data.get("tool")
            parameters = data.get("parameters", {})
        
            # Если parameters не указан, но есть другие ключи — используем их
            if not parameters and tool_name:
                parameters = {k: v for k, v in data.items() if k != "tool"}
        
            if not tool_name:
                return "Ошибка: не указан инструмент."
        
            return await self.tool_registry.execute(tool_name, parameters)
        except json.JSONDecodeError:
            return "Ошибка: невалидный JSON вызова инструмента."
        except Exception as e:
            return f"Ошибка выполнения инструмента: {str(e)}"


# ==================== КОНСОЛЬНЫЙ ИНТЕРФЕЙС (CLI) ====================

class CLIEnvironment(Environment):
    """Консольный интерфейс для Леи."""
    
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
            return self.input_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    async def send_message(self, message: str):
        """Выводит сообщение в консоль"""
        print(f"\n[ЛЕЯ]: {message}\n")