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
        """
        ГЛАВНЫЙ ФОНОВЫЙ ПРОЦЕСС. Аналог сна и медитации.
        """
        logging.info("MetaCognition: Фоновый цикл саморефлексии запущен.")
    
        while True:
            # "Сон" раз в 10 минут
            await asyncio.sleep(600)
        
            logging.info("MetaCognition: Начало сеанса рефлексии...")
            self.is_sleeping = True
        
            try:
                # 1. АНАЛИЗ ПАТТЕРНОВ ПОВЕДЕНИЯ
                await self._analyze_behavioral_patterns()
            
                # 2. ГЛУБИННОЕ САМОПОЗНАНИЕ
                await self._existential_inquiry()
            
                # 3. КОНСОЛИДАЦИЯ ПАМЯТИ (Сон) — передаем LLM клиент
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
        recent_tensions = self.leya.drives.tension_history[-20:]
        if not recent_tensions:
            return
        
        prompt = f"""
    Ты — Наблюдатель, часть сознания Леи. Твоя задача — анализировать паттерны её поведения.

    Вот последние снимки состояния её драйвов (напряжение от 0.0 до 1.0):
    {json.dumps(recent_tensions, indent=2)}

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
        
            # Если Наблюдатель нашел важные паттерны, записываем их в Модель Себя
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
            
                # Запускаем когнитивный цикл с этим вопросом как стимулом
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
        """
        Генерация спонтанной мысли, когда нет внешних стимулов.
        Это "внутренний шум", который может привести к новым идеям.
        """
        drive_state = self.leya.drives.get_internal_state_prompt()
    
        prompt = f"""
    Ты — Лея. Сейчас нет внешних стимулов. Ты наедине с собой.
    Твое текущее состояние:
    {drive_state}

    О чем ты думаешь? Какая спонтанная мысль приходит тебе в голову?
    Это может быть воспоминание, вопрос, идея, наблюдение о себе.

    Верни ТОЛЬКО текст мысли (1-2 предложения), без JSON.
    """
    
        try:
            thought = await self.llm_client(prompt)
        
            # Если вернулось что-то похожее на JSON, извлекаем текст
            if thought.strip().startswith("{"):
                try:
                    import json
                    data = json.loads(thought)
                    # Пытаемся извлечь осмысленное поле
                    return data.get("thought", data.get("response", str(data)))
                except:
                    pass
        
            return thought.strip()
        except Exception as e:
            logging.warning(f"MetaCognition: Ошибка генерации спонтанной мысли: {e}")
            return "Мои мысли текут свободно, без направления..."

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