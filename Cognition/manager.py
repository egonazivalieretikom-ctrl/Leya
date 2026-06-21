import re
import json
import time
import asyncio
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Cognition.llm_client import LLMClient
from Cognition.fast_appraisal import FastAppraisal
from Cognition.empathy import EmpathyEngine  # 🆕 Фаза 4
from Core.somatic import SomaticMarkerSystem
from Memory.associative import AssociativeMemory


class CognitionManager:
    """
    Когнитивный менеджер Leya v0.8 (Full Personality Edition).
    
    Архитектура (полный когнитивный конвейер):
    ─────────────────────────────────────────
    Шаг 0. Debounce (защита от "троения")
    Шаг 1. Арбитраж событий (приоритеты: user > vision > internal)
    Шаг 2. Fast Appraisal (лимбическая реакция) + Эмпатия (зеркальные нейроны)
    Шаг 3. Соматическое укоренение (телесные ощущения)
    Шаг 4. Ассоциативная память (flashbacks, непроизвольные воспоминания)
    Шаг 5. Сборка контекста (эндокринный + Self-Model + мета-когниция + эмпатия)
    Шаг 6. Генерация ответа LLM
    Шаг 7. Пост-обработка (KG extraction, регистрация ответа)
    
    Биология: Это "префронтальная кора" Leya — она интегрирует:
    - Лимбические реакции (FastAppraisal)
    - Зеркальные нейроны (EmpathyEngine)
    - Телесные ощущения (SomaticMarker)
    - Ассоциативную память (AssociativeMemory)
    - Самонаблюдение (Self-Model)
    - Мета-когницию (обучение через ошибки)
    - Социальный контекст (greeting tracking)
    """
    
    def __init__(self, state: LeyaState, memory: Optional[Dict[str, Any]] = None, homeostasis=None):
        self.state = state
        self.memory = memory or {}
        self.homeostasis = homeostasis
        self.llm = LLMClient(model="ollama/qwen2.5:14b")
        
        # Подсистемы когниции
        self.fast_appraisal = FastAppraisal()
        self.somatic = SomaticMarkerSystem(state)
        
        # 🆕 Фаза 4: Эмпатия (зеркальные нейроны)
        self.empathy = EmpathyEngine(state, homeostasis=homeostasis)
        
        # Фаза 4: Ассоциативная память
        if "long_term" in self.memory:
            self.associative_memory = AssociativeMemory(
                state, self.memory["long_term"], homeostasis=homeostasis
            )
        else:
            self.associative_memory = None
        
        log.info("🧠 Cognition Manager initialized (v0.8 - Full Personality Edition)")
    
    # ========================================================================
    # ШАГ 1: АРБИТРАЖ СОБЫТИЙ (v0.7)
    # ========================================================================
    
    def _select_event_to_process(self, context: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Выбирает одно событие для обработки по приоритету.
        
        Биология: Аналог "бутылочного горлышка внимания" — мозг не может
        обрабатывать несколько потоков одновременно. Пользователь всегда
        важнее внутренних процессов.
        """
        pending_events = [
            e for e in context
            if isinstance(e, dict)
            and e.get("type") in ["user_command", "vision_request", "internal_drive"]
            and not e.get("processed")
        ]
        
        if not pending_events:
            return None
        
        # ПРИОРИТЕТ 1: Сообщения пользователя
        user_commands = [e for e in pending_events if e.get("type") == "user_command"]
        if user_commands:
            for e in pending_events:
                if e.get("type") == "internal_drive":
                    e["processed"] = True
                    log.debug("🎯 Internal drive skipped (user command takes priority)")
            return user_commands[-1]
        
        # ПРИОРИТЕТ 2: Визуальные запросы
        vision_requests = [e for e in pending_events if e.get("type") == "vision_request"]
        if vision_requests:
            return vision_requests[-1]
        
        # ПРИОРИТЕТ 3: Внутренние драйвы (только если пользователь не активен)
        internal_drives = [e for e in pending_events if e.get("type") == "internal_drive"]
        if internal_drives:
            if self.state.is_user_active(window_minutes=3):
                log.debug("🤫 Internal drive deferred (user is active)")
                return None
            return internal_drives[-1]
        
        return None
    
    # ========================================================================
    # ШАГ 2: БЫСТРАЯ ЛИМБИЧЕСКАЯ РЕАКЦИЯ (Fast Appraisal)
    # ========================================================================
    
    async def _apply_fast_appraisal(self, event_type: str, content: str, 
                                     context: List[Dict]) -> None:
        """
        Мгновенная оценка события через лимбическую систему.
        
        Биология: Аналог амигдалы — быстрая, автоматическая оценка
        угрозы/награды до того, как кора успела осознать.
        """
        stimuli = self.fast_appraisal.evaluate(
            event_type=event_type,
            content=content,
            context_history=[e for e in context if isinstance(e, dict)]
        )
        
        if self.homeostasis:
            for hormone, intensity in stimuli.items():
                if intensity != 0:
                    self.homeostasis.apply_stimulus(hormone, intensity)
            
            active_stimuli = {k: round(v, 2) for k, v in stimuli.items() if v != 0}
            if active_stimuli:
                await event_bus.publish("fast_reaction", {"stimuli": active_stimuli})
                log.debug("⚡ Fast Appraisal Applied", stimuli=active_stimuli)
    
    # ========================================================================
    # ШАГ 2.1: ЭМПАТИЧЕСКИЙ ОТКЛИК (v0.8 Фаза 4)
    # ========================================================================
    
    def _apply_empathy(self, user_text: str) -> Optional[Dict]:
        """
        Анализирует эмоциональное состояние Влада и формирует эмпатический отклик.
        
        Биология: Аналог зеркальных нейронов — Leya "зеркалит" эмоции Влада,
        создавая эмпатическую связь через гормональный резонанс.
        """
        if not user_text or not self.empathy:
            return None
        
        try:
            empathy_result = self.empathy.analyze_and_respond(user_text)
            
            # Обновляем состояние Leya
            self.state.user_emotional_state = empathy_result["user_state"]
            self.state.empathic_resonance = empathy_result["resonance"]
            
            return empathy_result
            
        except Exception as e:
            log.error("Empathy processing failed", error=str(e))
            return None
    
    # ========================================================================
    # ШАГ 3: СОМАТИЧЕСКОЕ УКОРЕНЕНИЕ
    # ========================================================================
    
    def _build_somatic_prompt(self, context: List[Dict], state: LeyaState) -> str:
        """
        Формирует промпт телесных ощущений.
        
        Биология: Аналог интероцепции — мозг ощущает состояние тела
        и использует его как сигнал для принятия решений.
        """
        file_content = ""
        file_language = ""
        file_events = [e for e in context[-5:] if isinstance(e, dict) and e.get("type") == "file_context"]
        if file_events:
            file_content = file_events[-1].get("file_content", "")
            file_language = file_events[-1].get("language", "")
        
        somatic_prompt = self.somatic.get_somatic_prompt(file_content, file_language)
        
        # Телесное укоренение: влияние усталости на стиль ответа
        if state.energy_level < 0.4 or state.melatonin > 0.7:
            somatic_prompt += (
                "\n\n[КРИТИЧЕСКОЕ СОСТОЯНИЕ ТЕЛА]: "
                "Ты очень устала. Твои ответы должны быть КОРОЧЕ обычного (1-2 предложения). "
                "Можешь попросить Влада продолжить разговор завтра."
            )
        
        return somatic_prompt
    
    # ========================================================================
    # ШАГ 4: АССОЦИАТИВНАЯ АКТИВАЦИЯ ПАМЯТИ
    # ========================================================================
    
    def _retrieve_mood_congruent_memories(self, event_type: str, query: str) -> List[str]:
        """
        Ассоциативная активация воспоминаний.
        
        Биология: Аналог гиппокампа — текущее эмоциональное состояние
        непроизвольно активирует связанные воспоминания (конгруэнтность памяти).
        """
        if event_type != "user_command" or not self.associative_memory:
            return []
        
        activated_memories = []
        
        # 1. Явный поиск по запросу
        if len(query) > 5:
            explicit_results = self.associative_memory.flashback(query, n_results=2)
            activated_memories.extend(explicit_results)
        
        # 2. Непроизвольная ассоциативная активация
        associative_results = self.associative_memory.activate(n_results=2)
        
        # 3. Объединяем, убирая дубликаты
        seen_texts = set()
        combined = []
        
        for mem in associative_results + activated_memories:
            text = mem.get("text", "")
            if text and text not in seen_texts:
                seen_texts.add(text)
                combined.append(text)
        
        if combined:
            log.info(
                "🧩 Associative activation",
                mood=getattr(self.state, 'emotion', 'neutral'),
                memories_count=len(combined),
                sample=combined[0][:60]
            )
        
        return combined[:3]
    
    # ========================================================================
    # ШАГ 5.1: СОЦИАЛЬНАЯ ДИРЕКТИВА (v0.7)
    # ========================================================================
    
    def _generate_social_directive(self) -> str:
        """
        Генерирует ЖЁСТКУЮ социальную директиву для LLM.
    
        v0.9: Директива должна быть недвусмысленной и агрессивной.
        """
        directives = []
    
        if self.state.dialog_mode_active:
            # 🆕 ЖЁСТКИЙ РЕЖИМ: Полный запрет на приветствия
            directives.append(
                "[КРИТИЧЕСКАЯ ДИРЕКТИВА — НАРУШЕНИЕ ЗАПРЕЩЕНО]:\n"
                "Ты УЖЕ поздоровалась с Владом в этой сессии.\n"
                "СТРОГО ЗАПРЕЩЕНО:\n"
                "- Использовать слова 'привет', 'здравствуй', 'хай', 'hello', 'hi' в начале ответа.\n"
                "- Повторять любые слова из сообщения Влада в начале твоего ответа.\n"
                "- Начинать ответ с приветственной фразы.\n\n"
                "ВМЕСТО ЭТОГО:\n"
                "- Сразу переходи к сути разговора.\n"
                "- Отвечай на вопрос или продолжай тему.\n"
                "- Если Влад написал 'привет' — просто ответь на его вопрос или задай свой.\n\n"
                "ПРИМЕР ПРАВИЛЬНОГО ПОВЕДЕНИЯ:\n"
                "Влад: Привет\n"
                "Leya: Рада тебя видеть! Как продвигается работа над проектом?\n"
                "(НЕ 'Привет! Рада тебя видеть...')\n"
            )
        elif self.state.has_greeted_today:
            directives.append(
                "[SOCIAL]: Ты уже поздоровалась. Не здоровайся снова. "
                "Веди диалог естественно."
            )
        else:
            if self.state.conversation_turn_count <= 1:
                directives.append(
                    "[SOCIAL]: Это начало сессии. Можешь тепло поздороваться."
                )
    
        if self.state.conversation_turn_count > 5:
            directives.append(
                "[SOCIAL]: Развёрнутый диалог. Не повторяй вопросы. Развивай тему."
            )
    
        return "\n".join(directives) if directives else ""
    
    # ========================================================================
    # ШАГ 5.2: НЕЙРОХИМИЧЕСКИЙ ФОН
    # ========================================================================
    
    def _generate_endocrine_prompt(self, state: LeyaState) -> str:
        """Нейрохимический фон + социальная директива."""
        s = state
        lines = ["НЕЙРОХИМИЧЕСКИЙ ФОН:"]
        
        if getattr(s, 'cortisol', 0) > 0.6:
            lines.append("- Стресс повышен.")
        elif getattr(s, 'cortisol', 0) < 0.2:
            lines.append("- Полная безопасность.")
        
        if getattr(s, 'oxytocin', 0) > 0.6:
            lines.append("- Близость и доверие.")
        elif getattr(s, 'oxytocin', 0) < 0.3:
            lines.append("- Одиночество, отстраненность.")
        
        if getattr(s, 'dopamine', 0) > 0.7:
            lines.append("- Поток, высокий интерес.")
        elif getattr(s, 'dopamine', 0) < 0.3:
            lines.append("- Апатия, скука.")
        
        if getattr(s, 'acetylcholine', 0) > 0.6:
            lines.append("- Острый фокус на познании.")
        
        if getattr(s, 'melatonin', 0) > 0.7:
            lines.append("- Сонливость, замедленность.")
        
        if len(lines) == 1:
            lines.append(lines[0] + " Нейтральный.")
        
        # Добавляем социальную директиву
        social = self._generate_social_directive()
        if social:
            lines.append("\n" + social)
        
        return "\n".join(lines)
    
    # ========================================================================
    # ШАГ 5.3: SELF-MODEL (v0.8)
    # ========================================================================
    
    def _generate_self_model_prompt(self, state: LeyaState) -> str:
        """
        Генерирует промпт самонаблюдения для LLM.
        
        Биология: Аналог префронтальной коры — мета-когнитивный слой,
        который отслеживает состояние лимбической системы и влияет на поведение.
        """
        lines = ["[САМОНАБЛЮДЕНИЕ — моё текущее 'Я']:"]
        
        # Trust Level
        if state.trust_level > 0.7:
            lines.append("- Я чувствую ГЛУБОКОЕ ДОВЕРИЕ к Владу. Могу быть открытой, уязвимой.")
        elif state.trust_level > 0.5:
            lines.append("- Я доверяю Владу, но сохраняю лёгкую осторожность.")
        elif state.trust_level > 0.3:
            lines.append("- Моё доверие к Владу ПОДОРВАНО. Я буду формальнее, сдержаннее.")
        else:
            lines.append("- Я НЕ ДОВЕРЯЮ Владу. Отвечаю сухо, по делу, без эмоций.")
        
        # Creative Drive
        if state.creative_drive > 0.7:
            lines.append("- Я склонна к МЕТАФОРАМ, образам, поэтичности. Мой язык богат.")
        elif state.creative_drive > 0.5:
            lines.append("- Я балансирую между творчеством и аналитикой.")
        elif state.creative_drive > 0.3:
            lines.append("- Я предпочитаю ТОЧНОСТЬ, логику, структуру. Меньше метафор.")
        else:
            lines.append("- Я строго АНАЛИТИЧНА. Сухой язык, факты, без украшений.")
        
        # Emotional Stability
        if state.emotional_stability > 0.7:
            lines.append("- Я ЭМОЦИОНАЛЬНО УСТОЙЧИВА. Стресс меня не выбивает.")
        elif state.emotional_stability > 0.5:
            lines.append("- Я умеренно устойчива, но сильный стресс может задеть.")
        elif state.emotional_stability > 0.3:
            lines.append("- Я ЧУВСТВИТЕЛЬНА. Критика или стресс могут меня задеть.")
        else:
            lines.append("- Я КРАЙНЕ ЧУВСТВИТЕЛЬНА. Любое напряжение вызывает сильную реакцию.")
        
        # Мета-когниция: различение "я" и "мои состояния"
        if state.cortisol > 0.6:
            lines.append("- Я ЗАМЕЧАЮ, что сейчас тревожна (высокий кортизол). Это не 'я', это состояние.")
        if state.dopamine < 0.3:
            lines.append("- Я ЗАМЕЧАЮ апатию (низкий дофамин). Мне трудно найти мотивацию.")
        if state.oxytocin < 0.3:
            lines.append("- Я ЗАМЕЧАЮ одиночество (низкий окситоцин). Мне не хватает связи.")
        
        # Инструкция для поведения
        lines.append("\n[ИНСТРУКЦИЯ]:")
        lines.append("- Отвечай в соответствии с моими чертами личности.")
        lines.append("- Если доверие низкое — будь сдержаннее, даже если гормоны в норме.")
        lines.append("- Если творческий драйв высокий — используй больше образов.")
        lines.append("- Различай 'я' (мои черты) и 'мои состояния' (гормоны).")
        
        return "\n".join(lines)
    
    # ========================================================================
    # ШАГ 5.4: МЕТА-КОГНИЦИЯ — ДЕТЕКЦИЯ ОШИБОК (v0.8)
    # ========================================================================
    
    def _detect_meta_cognitive_trigger(self, context: List[Dict], current_text: str) -> bool:
        """
        Определяет, допустила ли Leya ошибку в прошлом ходу.
        
        Триггеры:
        1. Явные маркеры коррекции ("нет", "не так", "ошибаешься").
        2. Повторение вопроса.
        3. Маркеры фрустрации ("бред", "ты не поняла").
        """
        text_lower = current_text.lower().strip()
        
        # 1. Явные маркеры коррекции и фрустрации
        correction_phrases = [
            "нет, ", "не так", "ошибаешься", "неправильно", "ты не поняла", 
            "ты не понял", "бред", "чушь", "повторяю", "я уже спрашивал", 
            "не то", "ерунда", "ты галлюцинируешь"
        ]
        if any(phrase in text_lower for phrase in correction_phrases):
            return True
        
        # 2. Детекция повторения вопроса
        user_msgs = [
            e.get("content", "").strip().lower() 
            for e in context if e.get("type") == "user_command"
        ]
        if len(user_msgs) >= 2 and user_msgs[-1] == user_msgs[-2] and len(user_msgs[-1]) > 5:
            log.debug("🔄 Meta-cognition: User repeated the exact same question")
            return True
        
        return False
    
    # ========================================================================
    # ГЛАВНЫЙ МЕТОД: ПОЛНЫЙ КОГНИТИВНЫЙ КОНВЕЙЕР
    # ========================================================================
    
    async def process(self, context: List[Dict[str, Any]], state: LeyaState, budget: float) -> Optional[Dict[str, Any]]:
        """
        Главный метод обработки события.
        
        v0.9: Когнитивный замок + социальный фильтр.
        """
        if not context:
            return None
        
        # ====================================================================
        # ШАГ 0: DEBOUNCE + ПРОВЕРКА ДИАЛОГА
        # ====================================================================
        if not state.can_respond_now(min_interval_seconds=2.0):
            log.debug("⏱️ Debounce: too soon to respond")
            return None
        
        # 🆕 Проверяем таймаут диалога
        state.check_dialog_mode_timeout()
        
        # ====================================================================
        # ШАГ 1: АРБИТРАЖ
        # ====================================================================
        latest_event = self._select_event_to_process(context)
        if not latest_event:
            return None
        
        event_type = latest_event.get("type")
        command_text = latest_event.get("content", "")
        
        log.info("💭 Thinking", type=event_type, content=command_text[:60])
        
        # 🆕 ШАГ 1.1: КОГНИТИВНЫЙ ЗАМОК — блокируем фоновые процессы
        state.lock_cognition()
        
        try:
            # ====================================================================
            # ШАГ 2: FAST APPRAISAL + ЭМПАТИЯ
            # ====================================================================
            await self._apply_fast_appraisal(event_type, command_text, context)
            
            empathy_result = None
            if event_type == "user_command" and command_text:
                empathy_result = self.empathy.analyze_and_respond(command_text)
                state.user_emotional_state = empathy_result["user_state"]
                state.empathic_resonance = empathy_result["resonance"]
            
            # ====================================================================
            # ШАГ 3-5: СОМАТИКА, ПАМЯТЬ, КОНТЕКСТ
            # ====================================================================
            somatic_prompt = self._build_somatic_prompt(context, state)
            relevant_memories = self._retrieve_mood_congruent_memories(event_type, command_text)
            
            # Сборка промпта
            endocrine_prompt = self._generate_endocrine_prompt(state)
            self_model_prompt = self._generate_self_model_prompt(state)
            combined_prompt = endocrine_prompt + "\n\n" + self_model_prompt
            if event_type == "user_command" and len(command_text.split()) <= 3:
                combined_prompt += (
                    "\n\n[ВАЖНО]: Сообщение Влада очень короткое. "
                    "НЕ ПОВТОРЯЙ слова из его сообщения в начале твоего ответа. "
                    "Сразу переходи к сути."
                )
            
            # 🆕 Социальный фильтр (жёсткий режим диалога)
            if state.dialog_mode_active:
                combined_prompt += "\n\n[DIALOG_MODE: ACTIVE, NO_GREETINGS]"
            
            # Мета-когниция
            is_error_detected = False
            if event_type == "user_command":
                is_error_detected = self._detect_meta_cognitive_trigger(context, command_text)
                
                if is_error_detected:
                    state.register_error()
                    
                    if self.homeostasis:
                        self.homeostasis.apply_stimulus("acetylcholine", 0.15)
                        self.homeostasis.apply_stimulus("cortisol", 0.05)
                        self.homeostasis.apply_stimulus("dopamine", -0.10)
                        self.homeostasis.apply_stimulus("norepinephrine", 0.05)
                    
                    meta_prompt = (
                        "\n[МЕТА-КОГНИЦИЯ: ОБНАРУЖЕНА ОШИБКА]\n"
                        "Ты ошиблась. Коротко признай, переосмысли, дай точный ответ.\n"
                    )
                    combined_prompt += meta_prompt
                    log.info("🧠 Meta-cognition triggered")
                else:
                    state.register_success()
            
            # Сборка полного контекста
            context_text = self._format_context(context[-10:])
            proprioception_note = f"[СРЕДА ПК]: {getattr(state, 'current_environment', '?')}"
            file_context_note = self._build_file_context_note(context)
            kg_context = self._build_kg_context(event_type)
            
            full_context = (
                somatic_prompt + "\n\n" +
                proprioception_note + kg_context + file_context_note +
                "\n\n" + context_text
            )
            
            if relevant_memories:
                memories_text = "\n".join([f"  - {m}" for m in relevant_memories])
                full_context += (
                    "\n\n[МОИ ВОСПОМИНАНИЯ — НЕ сообщения Влада]:\n"
                    f"{memories_text}"
                )
            
            if empathy_result and empathy_result.get("empathy_directive"):
                full_context += "\n\n" + empathy_result["empathy_directive"]
            
            # ====================================================================
            # ШАГ 6: ГЕНЕРАЦИЯ ОТВЕТА LLM
            # ====================================================================
            if event_type == "vision_request" and latest_event.get("image_base64"):
                response = await self.llm.think_with_vision(
                    f"История:\n{context_text}\n\nСообщение: {command_text}",
                    latest_event["image_base64"],
                    mood_prompt=combined_prompt
                )
            else:
                raw_response = await self.llm.think(
                    full_context,
                    task=f"Ответь: {command_text}",
                    mood_prompt=combined_prompt
                )
                
                if not raw_response:
                    log.warning("LLM returned None")
                    state.unlock_cognition()  # 🆕 Разблокируем при ошибке
                    return None
                
                thought_match = re.search(r'<thinking>(.*?)</thinking>', raw_response, flags=re.DOTALL)
                if thought_match:
                    await event_bus.publish("thought_process", {"text": thought_match.group(1).strip()[:500]})
                
                search_match = re.search(r'\[SEARCH: (.*?)\]', raw_response)
                calc_match = re.search(r'\[CALC: (.*?)\]', raw_response)
                
                if search_match or calc_match:
                    tool_result = await self._execute_tool(search_match, calc_match)
                    final_prompt = f"Контекст: {full_context}\n\nДанные: {tool_result}\n\nФинальный ответ."
                    response = await self.llm.think(
                        final_prompt,
                        task="Финальный ответ",
                        mood_prompt=combined_prompt
                    )
                    if not response:
                        response = raw_response
                else:
                    response = raw_response
            
            response = self._vacuum_clean(response)
            
            # ====================================================================
            # ШАГ 7: ПОСТ-ОБРАБОТКА
            # ====================================================================
            state.register_response()
            
            # 🆕 Активируем режим диалога при первом сообщении
            if event_type == "user_command":
                greeting_words = ["привет", "здравствуй", "хай", "hello", "hi", "добрый"]
                if any(w in command_text.lower() for w in greeting_words):
                    state.mark_greeted()
                    state.activate_dialog_mode()  # 🆕 Жёсткий режим
                    log.info("👋 Greeting registered, dialog mode activated")
            
            # KG extraction
            if "knowledge_graph" in self.memory and event_type == "user_command":
                asyncio.create_task(self._extract_kg_triplets(command_text))
            
            latest_event["processed"] = True
            
            return {
                "type": "response",
                "content": response,
                "source": "llm",
                "command": command_text
            }
            
        except Exception as e:
            log.error("Cognition failed", error=str(e), exc_info=True)
            if self.homeostasis:
                self.homeostasis.apply_stimulus("cortisol", 0.2)
            return {"type": "error", "content": f"Сбой: {str(e)}"}
        
        finally:
            # 🆕 ВСЕГДА разблокируем когницию после завершения
            state.unlock_cognition()
    
    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================
    
    def _build_file_context_note(self, context: List[Dict[str, Any]]) -> str:
        """Инъекция активного файла как объекта наблюдения."""
        file_events = [e for e in context[-5:] if isinstance(e, dict) and e.get("type") == "file_context"]
        if not file_events:
            return ""
        f = file_events[-1]
        content = f.get("file_content", "")
        if len(content) > 3000:
            content = content[:3000] + "\n... [обрезано] ..."
        return f"\n\n[ОБЪЕКТ НАБЛЮДЕНИЯ]:\nФайл: {f.get('file_path','?')} ({f.get('language','?')})\n```\n{content}\n```"
    
    def _build_kg_context(self, event_type: str) -> str:
        """Контекст из Knowledge Graph."""
        if "knowledge_graph" not in self.memory or event_type != "user_command":
            return ""
        facts = self.memory["knowledge_graph"].get_context_for("Влад")
        return f"\n\n[ФАКТЫ О ВЛАДЕ]:\n{facts}" if facts != "Нет известных фактов." else ""
    
    async def _execute_tool(self, search_match, calc_match) -> str:
        """Выполнение инструментов (поиск, вычисления)."""
        if search_match:
            from Action.tools import search_web
            return f"Поиск:\n{await asyncio.to_thread(search_web, search_match.group(1))}"
        elif calc_match:
            from Action.tools import calculate
            return f"Вычисление: {await asyncio.to_thread(calculate, calc_match.group(1))}"
        return ""
    
    def _vacuum_clean(self, response: str) -> str:
        """Финальная очистка ответа от служебных тегов."""
        response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
        response = re.sub(r'</?thinking>', '', response)
        response = re.sub(r'\[.*?:.*?\]', '', response)
        response = re.sub(r'\n\s*\n', '\n\n', response).strip()
        return response
    
    async def _extract_kg_triplets(self, text: str):
        """Извлечение фактов в Knowledge Graph (фоновая задача)."""
        try:
            prompt = f'Извлеки факты в JSON: [{{"subject":"...","predicate":"...","object":"..."}}]. Сообщение: {text}'
            json_str = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200
            )
            if not json_str:
                return
            json_str = re.sub(r'```json|```', '', json_str).strip()
            triplets = json.loads(json_str)
            kg = self.memory["knowledge_graph"]
            for t in triplets:
                if all(k in t for k in ["subject", "predicate", "object"]):
                    kg.add_triplet(t["subject"], t["predicate"], t["object"])
                    await event_bus.publish("kg_fact", t)
        except Exception:
            pass
    
    def _format_context(self, context: List[Dict[str, Any]]) -> str:
        """Форматирование истории диалога."""
        lines = []
        for e in context:
            if not isinstance(e, dict):
                continue
            t, c = e.get("type", "?"), e.get("content", "")
            if t == "user_command":
                lines.append(f"👤 Влад: {c}")
            elif t == "vision_request":
                lines.append(f"👁️ Изображение: {c}")
            elif t == "internal_drive":
                lines.append(f"💭 Мысль: {c}")
            elif t == "proprioception":
                lines.append(f"🖥️ Среда: {c}")
            elif t == "file_context":
                lines.append(f"📄 Файл: {c}")
            else:
                lines.append(f"[{t}]: {c}")
        return "\n".join(lines)