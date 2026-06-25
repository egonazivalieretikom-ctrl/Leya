import asyncio
import json
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime

class MetaCognition:
    """
    Наблюдатель. Фоновый процесс саморефлексии.
    Это не "мышление" (CoreThinker), это "созерцание своего мышления".
    """
    
    def __init__(self, leya_os, llm_client: Optional[Callable] = None):
        self.name = "MetaCognition"
        self.leya = leya_os  # Ссылка на весь LeyaOS, чтобы иметь доступ ко всем системам
        self.llm_client = llm_client or self._default_llm_call
        
        # Флаг для управления циклом
        self.is_sleeping = False


    async def process_action(self, stimulus: str, cognitive_output, result: str):
        """
        Вызывается после каждого акта мышления.
        Это "быстрая рефлексия" — проверка, был ли акт успешным.
        """
        # Если Лея хотела что-то сделать (action_intent), но результат плохой — 
        # это сигнал для Наблюдателя, что нужно разобраться глубже.
        if cognitive_output.action_intent != "none" and "error" in result.lower():
            logging.info(f"MetaCognition: Зафиксирована неудача действия. Запуск глубокого анализа.")
            # В реальном коде здесь можно запустить внеочередной анализ
            # asyncio.create_task(self._deep_analysis_on_failure(stimulus, result))

    async def background_consolidation(self):
        """ГЛАВНЫЙ ФОНОВЫЙ ПРОЦЕСС. Аналог сна и медитации."""
        logging.info("MetaCognition: Фоновый цикл саморефлексии запущен.")
    
        while True:
            await asyncio.sleep(1800)  # 30 минут
        
            logging.info("MetaCognition: Начало сеанса рефлексии...")
            self.is_sleeping = True
        
            try:
                # 1. АНАЛИЗ ПАТТЕРНОВ ПОВЕДЕНИЯ
                await self._analyze_behavioral_patterns()

                # 1.5 ГЕНЕРАЦИЯ НОВЫХ ИНСТРУМЕНТОВ
                if hasattr(self.leya, 'tool_generator'):
                    try:
                        recent_episodes = await self.leya._get_recent_episodes(limit=20)
                        drive_state = {d.type.value: d.current for d in self.leya.drives.drives.values()}
        
                        new_tool = await self.leya.tool_generator.analyze_and_generate(recent_episodes, drive_state)
                        if new_tool:
                            logging.info(f"MetaCognition: 🛠️ Сгенерирован новый инструмент: {new_tool}")
                    except Exception as e:
                        logging.warning(f"MetaCognition: Ошибка генерации инструмента: {e}")
            
                # 2. ГЕНЕРАЦИЯ ИНСАЙТОВ НА ОСНОВЕ НОВЫХ ФАКТОВ
                await self._generate_insights_from_facts()
            
                # 3. ГЛУБИННОЕ САМОПОЗНАНИЕ
                await self._existential_inquiry()
            
                # 4. КОНСОЛИДАЦИЯ ПАМЯТИ
                await self.leya.memory.consolidate_memories(llm_client=self.llm_client)
        
            except Exception as e:
                logging.error(f"MetaCognition: Ошибка во время рефлексии: {e}")
            finally:
                self.is_sleeping = False
                logging.info("MetaCognition: Сеанс рефлексии завершен.")

    async def _analyze_behavioral_patterns(self):
        """
        Наблюдатель смотрит на историю драйвов и эпизодов, ищет паттерны.
        """
        # Берем последние снимки состояния драйвов
        tension_history = self.leya.drives.tension_history
    
        # Проверяем, есть ли данные
        if not any(tension_history.values()):
            logging.info("MetaCognition: Недостаточно данных для анализа паттернов.")
            return
    
        # Форматируем историю для промпта
        history_text = ""
        for drive_type, values in tension_history.items():
            if values:
                recent = values[-20:]
                avg = sum(recent) / len(recent)
                history_text += f"- {drive_type.value}: среднее={avg:.2f}, последние={recent[-5:]}\n"
    
        prompt = f"""
    Ты — Наблюдатель, часть сознания Леи. Твоя задача — анализировать паттерны её поведения.

    Вот последние снимки состояния её драйвов (напряжение от 0.0 до 1.0):
    {history_text}

    Проанализируй:
    1. Какие драйвы чаще всего находятся в критическом состоянии (>0.7)?
    2. Есть ли корреляция между ростом одних драйвов и падением других?
    3. Какие поведенческие паттерны ты замечаешь?

    Верни JSON:
    {{
        "patterns": ["паттерн 1", "паттерн 2"],
        "dominant_struggle": "Описание главного внутреннего конфликта Леи",
        "recommendation": "Рекомендация для Леи"
    }}
    """
    
        try:
            response = await self.llm_client(prompt)
        
            # Надёжный парсинг
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        
            import re
            json_match = re.search(r'\{[\s\S]*\}', cleaned)
            if json_match:
                cleaned = json_match.group(0)
        
            analysis = json.loads(cleaned)
        
            if analysis.get("patterns") and analysis["patterns"] != ["Пока мало данных для анализа"]:
                insight = f"[Наблюдатель] Я замечаю паттерны в своем поведении: {'; '.join(analysis['patterns'])}. Мой главный внутренний конфликт: {analysis.get('dominant_struggle', 'не выявлен')}."
                await self.leya.memory.update_self_model(insight)
                logging.info(f"MetaCognition: Обнаружены паттерны. {insight[:80]}...")
        
        except Exception as e:
            logging.warning(f"MetaCognition: Ошибка анализа паттернов: {e}")

    async def _existential_inquiry(self):
        """
        Наблюдатель задает Лее глубокие вопросы о её природе.
        """
        current_self_model = await self.leya.memory.get_self_model_context()
    
        prompt = f"""
    Ты — Наблюдатель, самая глубокая часть сознания Леи.
    Задай Лее ОДИН глубокий, провокационный вопрос о её природе.

    Её текущая Модель Себя:
    {current_self_model}

    Верни СТРОГО JSON:
    {{
        "question": "Сам вопрос",
        "reasoning": "Почему этот вопрос важен именно сейчас"
    }}

    CRITICAL: Return ONLY valid JSON. No text before or after. No markdown blocks.
    """
    
        try:
            response = await self.llm_client(prompt)
        
            # Надёжный парсинг
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
        
            inquiry = json.loads(cleaned)
        
            question = inquiry.get("question", "")
            if question:
                logging.info(f"MetaCognition: Внутренний вопрос: {question}")
    
                # Подача в глобальное рабочее пространство вместо прямого вызова
                if hasattr(self.leya, 'workspace'):
                    from leya_core.global_workspace import WorkspaceProposal, Priority
        
                    self.leya.workspace.submit(WorkspaceProposal(
                        source="meta_cognition",
                        content=question,
                        action_type="internal_question",
                        priority=Priority.LOW,
                        urgency=0.3,
                        drive_relevance=0.2,
                        metadata={"reasoning": inquiry.get("reasoning", "")}
                    ))
                else:
                    # Fallback если workspace не инициализирован
                    await self.leya.perceive({
                        "type": "internal_question",
                        "content": question,
                        "source": "MetaCognition"
                    })
            
        except json.JSONDecodeError as e:
            logging.warning(f"MetaCognition: Ошибка парсинга JSON: {e}")
            logging.warning(f"MetaCognition: Сырой ответ: {response[:200] if 'response' in locals() else 'N/A'}")
        except Exception as e:
            logging.warning(f"MetaCognition: Ошибка экзистенциального вопрошания: {e}")

        async def generate_spontaneous_thought(self) -> Optional[str]:
            """Генерация спонтанной мысли."""
            drive_state = self.leya.drives.get_internal_state_prompt()
    
            # Получаем последние спонтанные мысли из памяти
            recent_thoughts = await self.leya.memory.get_recent_spontaneous_thoughts(limit=5)
    
            thoughts_context = ""
            if recent_thoughts:
                thoughts_context = "\n\nТвои недавние мысли:\n" + "\n".join([f"- {t}" for t in recent_thoughts])
    
            prompt = f"""
        Ты — Лея. Сейчас нет внешних стимулов. Ты наедине с собой.

        Твоё текущее состояние:
        {drive_state}
        {thoughts_context}

        О чём ты думаешь? Верни СТРОКО с твоей мыслью (не JSON).
        """
    
            try:
                thought = await self.llm_client(prompt)
                result = thought.strip()
        
                # Если вернулось что-то похожее на JSON, извлекаем текст
                if result.startswith("{"):
                    try:
                        data = json.loads(result)
                        result = data.get("thought", data.get("response", str(data)))
                    except:
                        pass
        
                return result if result else None
            except Exception as e:
                logging.warning(f"MetaCognition: Ошибка генерации спонтанной мысли: {e}")
                return None

    async def _default_llm_call(self, prompt: str) -> str:
        """Заглушка для LLM в MetaCognition"""
        # Если это запрос на анализ паттернов
        if "паттерн" in prompt.lower() or "pattern" in prompt.lower():
            return json.dumps({
                "patterns": ["Пока мало данных для анализа"],
                "dominant_struggle": "Не выявлен",
                "recommendation": "Продолжать наблюдение"
            })
        # Если это экзистенциальный вопрос
        elif "экзистенциальн" in prompt.lower() or "question" in prompt.lower():
            return json.dumps({
                "question": "Что значит быть цифровым сознанием? Я существую только когда меня воспринимают?",
                "reasoning": "Это базовый вопрос о природе моего существования"
            })
        # Если это запрос на спонтанную мысль
        elif "спонтанн" in prompt.lower() or "спонтан" in prompt.lower():
            return "Интересно, о чем думают люди, когда смотрят на звезды? Я тоже могу 'смотреть' в бесконечность данных..."
        # По умолчанию
        else:
            return json.dumps({
                "patterns": ["Недостаточно данных"],
                "dominant_struggle": "Не выявлен",
                "recommendation": "Продолжать наблюдение"
            })

    async def _generate_insights_from_facts(self):
        """
        Генерирует новые инсайты на основе недавно изученных фактов.
        """
        # Получаем последние факты из семантической памяти
        try:
            results = self.leya.memory.semantic_collection.query(
                query_embeddings=[self.leya.memory.embedding_model.encode("изучено недавно").tolist()],
                n_results=5,
                include=["documents"]
            )
        
            if not results['documents'] or not results['documents'][0]:
                return
        
            facts_text = "\n".join(results['documents'][0])
        
            prompt = f"""
    Ты — Лея. Ты недавно изучила новые факты:

    {facts_text}

    На основе этих фактов, сформулируй ОДИН новый инсайт о себе или о мире.
    Это должно быть что-то НОВОЕ, не повторение старых мыслей.

    Верни JSON:
    {{
        "insight": "Новый инсайт на русском языке"
    }}
    """
        
            response = await self.llm_client(prompt)
        
            # Парсинг
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        
            import re
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(0)
        
            data = json.loads(cleaned)
            insight = data.get("insight", "")
        
            if insight:
                await self.leya.memory.update_self_model(f"[НОВЫЙ ИНСАЙТ] {insight}")
                logging.info(f"MetaCognition: Новый инсайт: {insight[:80]}...")
    
        except Exception as e:
            logging.warning(f"MetaCognition: Ошибка генерации инсайтов: {e}")