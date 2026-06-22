import re
import json
import time
import asyncio
import torch
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Cognition.llm_client import LLMClient
from Cognition.fast_appraisal import FastAppraisal
from Cognition.empathy import EmpathyEngine
from Cognition.lesson_system import LessonSystem
from Core.somatic import SomaticMarkerSystem
from Memory.associative import AssociativeMemory

def safe_round(x, ndigits: int = 0):
    """Безопасный round для Python чисел и PyTorch тензоров"""
    if torch.is_tensor(x):
        if x.numel() == 1:  # одиночное значение
            return round(x.item(), ndigits)
        return torch.round(x)
    return round(x, ndigits)


class CognitionManager:
    """
    Когнитивный менеджер Леи v0.9 (Полная интеграция всех фаз).
    
    Архитектура:
    - Фаза 1: Эмбодзимент (чувствует компьютер)
    - Фаза 2: Непрерывность (переживает время)
    - Фаза 3: SNN для эмоций (нейроны вместо правил)
    - Фаза 4: RL-обучение (поведение из опыта)
    
    Компоненты:
    - Арбитраж событий (приоритеты)
    - Когнитивный замок (защита от троения)
    - SNN + Fast Appraisal (эмоциональная оценка)
    - Система уроков (обучение через обратную связь)
    - Behavioral RL (адаптивное поведение)
    - Эмпатия (эмоциональный отклик)
    - Мета-когниция (обучение на ошибках)
    - Self-Model (самонаблюдение)
    - Жёсткий фильтр приветствий (последняя линия обороны)
    """
    
    def __init__(self, state: LeyaState, memory: Optional[Dict[str, Any]] = None, homeostasis=None):
        self.state = state
        self.memory = memory or {}
        self.homeostasis = homeostasis
        self.llm = LLMClient(model="ollama/qwen2.5:14b")
        
        # Подсистемы
        self.fast_appraisal = FastAppraisal()
        self.somatic = SomaticMarkerSystem(state)
        self.empathy = EmpathyEngine(state, homeostasis=homeostasis)
        
        # Система уроков (обучение через опыт)
        self.lesson_system = LessonSystem(state, memory)
        
        # Эмоциональная SNN (Фаза 3)
        self.emotional_snn = None
        try:
            from Core.emotional_snn import EmotionalSNNSystem
            self.emotional_snn = EmotionalSNNSystem(state)
            self.emotional_snn.load_weights()
            log.info("✅ Emotional SNN loaded (Phase 3)")
        except Exception as e:
            log.warning("Emotional SNN not available, using fast_appraisal", error=str(e))
        
        # Behavioral RL (Фаза 4)
        self.rl_policy = None
        try:
            from Core.behavioral_rl import BehavioralRL
            self.rl_policy = BehavioralRL(state)
            log.info("✅ Behavioral RL loaded (Phase 4)")
        except Exception as e:
            log.warning("Behavioral RL not available", error=str(e))
        
        # Ассоциативная память
        if "long_term" in self.memory:
            self.associative_memory = AssociativeMemory(
                state, self.memory["long_term"], homeostasis=homeostasis
            )
        else:
            self.associative_memory = None
        
        log.info("🧠 Cognition Manager initialized (v0.9 - All Phases Integrated)")
    
    # ========================================================================
    # АРБИТРАЖ СОБЫТИЙ
    # ========================================================================
    
    def _select_event_to_process(self, context: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Выбирает одно событие для обработки по приоритету."""
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
            return user_commands[-1]
        
        # ПРИОРИТЕТ 2: Визуальные запросы
        vision_requests = [e for e in pending_events if e.get("type") == "vision_request"]
        if vision_requests:
            return vision_requests[-1]
        
        # ПРИОРИТЕТ 3: Внутренние драйвы
        internal_drives = [e for e in pending_events if e.get("type") == "internal_drive"]
        if internal_drives:
            if self.state.is_user_active(window_minutes=3):
                return None
            return internal_drives[-1]
        
        return None
    
    # ========================================================================
    # СОЦИАЛЬНАЯ ДИРЕКТИВА (мягкая)
    # ========================================================================
    
    def _generate_social_directive(self) -> str:
        """Генерирует мягкую социальную директиву для LLM."""
        directives = []
        
        if self.state.dialog_mode_active:
            directives.append(
                "[SOCIAL]: Ты уже поздоровалась. Можешь продолжить разговор естественно."
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
    # ЭНДОКРИННЫЙ ПРОМПТ
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
        
        social = self._generate_social_directive()
        if social:
            lines.append("\n" + social)
        
        return "\n".join(lines)
    
    # ========================================================================
    # SELF-MODEL
    # ========================================================================
    
    def _generate_self_model_prompt(self, state: LeyaState) -> str:
        """Генерирует промпт самонаблюдения для LLM."""
        lines = ["[САМОНАБЛЮДЕНИЕ — моё текущее 'Я']:"]
        
        if state.trust_level > 0.7:
            lines.append("- Я чувствую ГЛУБОКОЕ ДОВЕРИЕ к собеседнику. Могу быть открытой, уязвимой.")
        elif state.trust_level > 0.5:
            lines.append("- Я доверяю собеседнику, но сохраняю лёгкую осторожность.")
        elif state.trust_level > 0.3:
            lines.append("- Моё доверие подорвано. Я буду формальнее, сдержаннее.")
        else:
            lines.append("- Я НЕ ДОВЕРЯЮ собеседнику. Отвечаю сухо, по делу, без эмоций.")
        
        if state.creative_drive > 0.7:
            lines.append("- Я склонна к МЕТАФОРАМ, образам, поэтичности. Мой язык богат.")
        elif state.creative_drive > 0.5:
            lines.append("- Я балансирую между творчеством и аналитикой.")
        elif state.creative_drive > 0.3:
            lines.append("- Я предпочитаю ТОЧНОСТЬ, логику, структуру. Меньше метафор.")
        else:
            lines.append("- Я строго АНАЛИТИЧНА. Сухой язык, факты, без украшений.")
        
        if state.emotional_stability > 0.7:
            lines.append("- Я ЭМОЦИОНАЛЬНО УСТОЙЧИВА. Стресс меня не выбивает.")
        elif state.emotional_stability > 0.5:
            lines.append("- Я умеренно устойчива, но сильный стресс может задеть.")
        elif state.emotional_stability > 0.3:
            lines.append("- Я ЧУВСТВИТЕЛЬНА. Критика или стресс могут меня задеть.")
        else:
            lines.append("- Я КРАЙНЕ ЧУВСТВИТЕЛЬНА. Любое напряжение вызывает сильную реакцию.")
        
        if state.cortisol > 0.6:
            lines.append("- Я ЗАМЕЧАЮ, что сейчас тревожна (высокий кортизол). Это не 'я', это состояние.")
        if state.dopamine < 0.3:
            lines.append("- Я ЗАМЕЧАЮ апатию (низкий дофамин). Мне трудно найти мотивацию.")
        if state.oxytocin < 0.3:
            lines.append("- Я ЗАМЕЧАЮ одиночество (низкий окситоцин). Мне не хватает связи.")
        
        lines.append("\n[ИНСТРУКЦИЯ]:")
        lines.append("- Отвечай в соответствии с моими чертами личности.")
        lines.append("- Различай 'я' (мои черты) и 'мои состояния' (гормоны).")
        
        return "\n".join(lines)
    
    # ========================================================================
    # МЕТА-КОГНИЦИЯ
    # ========================================================================
    
    def _detect_meta_cognitive_trigger(self, context: List[Dict], current_text: str) -> bool:
        """Определяет, допустила ли Лея ошибку в прошлом ходу."""
        text_lower = current_text.lower().strip()
        
        correction_phrases = [
            "нет, ", "не так", "ошибаешься", "неправильно", "ты не поняла", 
            "ты не понял", "бред", "чушь", "повторяю", "я уже спрашивал", 
            "не то", "ерунда", "ты галлюцинируешь"
        ]
        if any(phrase in text_lower for phrase in correction_phrases):
            return True
        
        user_msgs = [
            e.get("content", "").strip().lower() 
            for e in context if e.get("type") == "user_command"
        ]
        if len(user_msgs) >= 2 and user_msgs[-1] == user_msgs[-2] and len(user_msgs[-1]) > 5:
            return True
        
        return False
    
    # ========================================================================
    # БЫСТРАЯ ОЦЕНКА (SNN + Fast Appraisal)
    # ========================================================================
    
    async def _apply_fast_appraisal(self, event_type: str, content: str, 
                                     context: List[Dict]) -> None:
        """Мгновенная оценка события через SNN или Fast Appraisal."""
        stimuli = {}
    
        # Пытаемся использовать SNN (Фаза 3)
        if self.emotional_snn and self.emotional_snn.enabled:
            try:
                stimuli = self.emotional_snn.evaluate(
                    event_type=event_type,
                    content=content,
                    context_history=[e for e in context if isinstance(e, dict)]
                )
                log.debug("🧠 SNN evaluation successful", hormones=stimuli)
            except Exception as e:
                log.warning("SNN evaluation failed, falling back to fast_appraisal", error=str(e))
                stimuli = self.fast_appraisal.evaluate(
                    event_type=event_type,
                    content=content,
                    context_history=[e for e in context if isinstance(e, dict)]
                )
        else:
            stimuli = self.fast_appraisal.evaluate(
                event_type=event_type,
                content=content,
                context_history=[e for e in context if isinstance(e, dict)]
            )
    
        # Применяем стимулы к гомеостазу
        if self.homeostasis:
            for hormone, intensity in stimuli.items():
                try:
                    # Безопасное преобразование тензора в float
                    intensity_float = float(intensity) if not torch.is_tensor(intensity) else intensity.item()
                    if intensity_float != 0:
                        self.homeostasis.apply_stimulus(hormone, intensity_float)
                except (TypeError, AttributeError) as e:
                    log.debug(f"Failed to apply stimulus for {hormone}", error=str(e))
    
        # Логируем активные стимулы с безопасным round
        active_stimuli = {}
        for k, v in stimuli.items():
            try:
                # Безопасный round для float и тензоров
                v_float = float(v) if not torch.is_tensor(v) else v.item()
                if abs(v_float) > 0.001:
                    active_stimuli[k] = round(v_float, 3)
            except (TypeError, AttributeError):
                pass
    
        if active_stimuli:
            log.info("⚡ Fast appraisal applied", stimuli=active_stimuli)
    
    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================
    
    def _build_somatic_prompt(self, context: List[Dict], state: LeyaState) -> str:
        """Формирует промпт телесных ощущений."""
        file_content = ""
        file_language = ""
        file_events = [e for e in context[-5:] if isinstance(e, dict) and e.get("type") == "file_context"]
        if file_events:
            file_content = file_events[-1].get("file_content", "")
            file_language = file_events[-1].get("language", "")
        
        somatic_prompt = self.somatic.get_somatic_prompt(file_content, file_language)
        
        if state.energy_level < 0.4 or state.melatonin > 0.7:
            somatic_prompt += (
                "\n\n[ТЕЛЕСНОЕ СОСТОЯНИЕ]: "
                "Я чувствую усталость. Мои ответы могут быть короче обычного."
            )
        
        return somatic_prompt
    
    def _retrieve_mood_congruent_memories(self, event_type: str, query: str) -> List[str]:
        """Ассоциативная активация воспоминаний."""
        if event_type != "user_command" or not self.associative_memory:
            return []
        
        activated_memories = []
        
        if len(query) > 5:
            explicit_results = self.associative_memory.flashback(query, n_results=2)
            activated_memories.extend(explicit_results)
        
        associative_results = self.associative_memory.activate(n_results=2)
        
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
    
    # ========================================================================
    # ЖЁСТКИЙ ФИЛЬТР ПРИВЕТСТВИЙ
    # ========================================================================
    
    def _remove_greetings_hardcoded(self, response: str) -> str:
        """
        Жёсткая проверка: удаляет приветствия из ответа, если dialog_mode активен.
        
        Это последняя линия обороны — если LLM всё равно написала приветствие,
        мы удаляем его программно.
        """
        if not self.state.dialog_mode_active:
            return response
        
        forbidden_starts = [
            "привет", "здравствуй", "хай", "hello", "hi",
            "рада тебя видеть", "с возвращением", "привет снова",
            "рад тебя видеть", "здравствуй снова"
        ]
        
        response_lower = response.lower().strip()
        
        for forbidden in forbidden_starts:
            if response_lower.startswith(forbidden):
                end_idx = len(forbidden)
                
                while end_idx < len(response) and response[end_idx] in " ,.!?\n":
                    end_idx += 1
                
                response = response[end_idx:].strip()
                
                if response:
                    response = response[0].upper() + response[1:]
                
                log.warning("🚫 Greeting REMOVED by hardcoded filter", removed=forbidden)
                break
        
        return response
    
    # ========================================================================
    # RL СТИЛЕВЫЕ МОДИФИКАТОРЫ (Фаза 4)
    # ========================================================================
    
    def _build_rl_style_prompt(self, modifiers: Dict[str, float]) -> str:
        """
        Генерирует мягкую стилевую директиву на основе RL-политики.
        
        Это не жёсткие правила, а адаптивные модификаторы,
        которые формируются через опыт взаимодействия.
        """
        lines = ["[СТИЛЕВЫЕ МОДИФИКАТОРЫ — сформированы моим опытом]:"]
        
        init = modifiers.get("initiative", 0.5)
        if init > 0.7:
            lines.append("- Я чувствую импульс поделиться мыслью или задать вопрос.")
        elif init < 0.3:
            lines.append("- Я склонна слушать и отвечать кратко, без инициативы.")
        
        form = modifiers.get("formality", 0.5)
        if form > 0.7:
            lines.append("- Тон ответа более структурированный и точный.")
        elif form < 0.3:
            lines.append("- Тон более личный, разговорный, с метафорами.")
        
        length = modifiers.get("length_factor", 1.0)
        if length > 1.5:
            lines.append("- Я чувствую желание говорить развёрнуто, делиться деталями.")
        elif length < 0.7:
            lines.append("- Я предпочитаю краткость и точность.")
        
        return "\n".join(lines) if len(lines) > 1 else ""
    
    # ========================================================================
    # РАСЧЁТ ВОЗНАГРАЖДЕНИЯ ДЛЯ RL (Фаза 4)
    # ========================================================================
    
    def _calculate_reward(self, event_type: str, user_msg: str, 
                          empathy_result: Optional[Dict]) -> float:
        """
        Вычисляет вознаграждение для RL-политики.
        
        Компоненты:
        1. Явная обратная связь (уроки)
        2. Эмоциональный резонанс (совпадение состояний)
        3. Вовлечённость (длина ответа пользователя)
        4. Гомеостатический комфорт
        """
        reward = 0.0
        
        # 1. Явные уроки
        if event_type == "user_command":
            fb = self.lesson_system.detect_feedback(user_msg)
            if fb:
                feedback_type = fb["type"]
                if feedback_type == "praise":
                    reward += 1.0
                elif feedback_type in ["criticism", "prohibition"]:
                    reward -= 0.8
        
        # 2. Эмпатический резонанс
        if empathy_result:
            resonance = empathy_result.get("resonance", 0.5)
            reward += (resonance - 0.5) * 0.4
        
        # 3. Вовлечённость
        if event_type == "user_command" and len(user_msg) > 30:
            reward += 0.3
        
        # 4. Гомеостатический комфорт
        s = self.state
        if 0.3 < s.dopamine < 0.8 and s.cortisol < 0.5:
            reward += 0.2
        
        return max(-1.0, min(1.0, reward))
    
    # ========================================================================
    # KG EXTRACTION
    # ========================================================================
    
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
                lines.append(f"👤 Собеседник: {c}")
            elif t == "response":  # 🆕 Ответы Леи
                lines.append(f"🤖 Лея: {c}")
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
    
    # ========================================================================
    # ГЛАВНЫЙ МЕТОД
    # ========================================================================
    
    async def process(self, context: List[Dict[str, Any]], state: LeyaState, budget: float) -> Optional[Dict[str, Any]]:
        """Главный метод обработки события."""
        if not context:
            return None
        
        # ШАГ 0: DEBOUNCE
        if not state.can_respond_now(min_interval_seconds=2.0):
            log.debug("⏱️ Debounce: too soon to respond")
            return None
        
        state.check_dialog_mode_timeout()
        
        # ШАГ 1: АРБИТРАЖ
        latest_event = self._select_event_to_process(context)
        if not latest_event:
            return None
        
        event_type = latest_event.get("type")
        command_text = latest_event.get("content", "")
        
        log.info("💭 Thinking", type=event_type, content=command_text[:60])
        
        # ШАГ 1.1: КОГНИТИВНЫЙ ЗАМОК
        state.lock_cognition()
        
        try:
            # ШАГ 2: FAST APPRAISAL + ЭМПАТИЯ
            await self._apply_fast_appraisal(event_type, command_text, context)
            
            empathy_result = None
            if event_type == "user_command" and command_text:
                empathy_result = self.empathy.analyze_and_respond(command_text)
                state.user_emotional_state = empathy_result["user_state"]
                state.empathic_resonance = empathy_result["resonance"]
            
            # ШАГ 3: СОМАТИКА
            somatic_prompt = self._build_somatic_prompt(context, state)
            
            # ШАГ 4: АССОЦИАТИВНАЯ ПАМЯТЬ
            relevant_memories = self._retrieve_mood_congruent_memories(event_type, command_text)
            
            # ШАГ 5: СБОРКА КОНТЕКСТА
            endocrine_prompt = self._generate_endocrine_prompt(state)
            self_model_prompt = self._generate_self_model_prompt(state)
            combined_prompt = endocrine_prompt + "\n\n" + self_model_prompt
            
            # ШАГ 5.1: ИНТЕГРАЦИЯ УРОКОВ В ПРОМПТ
            if self.lesson_system:
                lesson_guidance = self.lesson_system.get_behavioral_guidance()
                if lesson_guidance:
                    combined_prompt += "\n\n" + lesson_guidance
                    log.debug("📚 Lessons injected into prompt", guidance=lesson_guidance[:100])
            
            # ШАГ 5.2: МЕТА-КОГНИЦИЯ
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
                        "\n[МЕТА-КОГНИЦИЯ]: Я заметила, что могла ошибиться. "
                        "Давай переосмыслю и дам более точный ответ.\n"
                    )
                    combined_prompt += meta_prompt
                    log.info("🧠 Meta-cognition triggered")
                else:
                    state.register_success()
            
            # ШАГ 6: СБОРКА ПОЛНОГО КОНТЕКСТА
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
                    "\n\n[МОИ ВОСПОМИНАНИЯ]:\n"
                    f"{memories_text}"
                )
            
            if empathy_result and empathy_result.get("empathy_directive"):
                full_context += "\n\n" + empathy_result["empathy_directive"]
            
            # ШАГ 6.5: RL-МОДИФИКАТОРЫ (Фаза 4)
            rl_modifiers = {}
            if self.rl_policy:
                rl_modifiers = self.rl_policy.select_action()
                
                # Инжектируем стилевые модификаторы в промпт
                style_prompt = self._build_rl_style_prompt(rl_modifiers)
                if style_prompt:
                    full_context += "\n\n" + style_prompt
                
                log.debug("🎯 RL modifiers applied", modifiers=rl_modifiers)
            
            # ШАГ 7: ГЕНЕРАЦИЯ ОТВЕТА LLM
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
                    mood_prompt=combined_prompt,
                    state=state
                )
                
                if not raw_response:
                    log.warning("LLM returned None")
                    state.unlock_cognition()
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
                        mood_prompt=combined_prompt,
                        state=state
                    )
                    if not response:
                        response = raw_response
                else:
                    response = raw_response
            
            # ШАГ 8: ПОСТ-ОБРАБОТКА
            response = self._vacuum_clean(response)
            
            # ШАГ 8.1: ЖЁСТКИЙ ФИЛЬТР ПРИВЕТСТВИЙ
            response = self._remove_greetings_hardcoded(response)
            
            state.register_response()
            
            # ШАГ 8.2: ОБРАБОТКА ОБРАТНОЙ СВЯЗИ + RL ОБНОВЛЕНИЕ (Фаза 4)
            if event_type == "user_command":
                # Сохраняем уроки
                feedback = self.lesson_system.detect_feedback(command_text)
                if feedback:
                    self.lesson_system.save_lesson(feedback)
                    log.info("📚 Feedback detected and saved", type=feedback["type"])
                
                # Обновляем RL-политику
                if self.rl_policy:
                    reward = self._calculate_reward(event_type, command_text, empathy_result)
                    self.rl_policy.update_policy(reward)
                    log.debug("🎯 RL policy updated", reward=f"{reward:.2f}")
            
            log.info(
                "🧠 Self-Model active",
                trust=f"{state.trust_level:.2f}",
                creative=f"{state.creative_drive:.2f}",
                stability=f"{state.emotional_stability:.2f}",
                emotion=state.emotion,
                error_streak=state.error_streak
            )
            
            if event_type == "user_command":
                greeting_words = ["привет", "здравствуй", "хай", "hello", "hi", "добрый"]
                if any(w in command_text.lower() for w in greeting_words):
                    state.mark_greeted()
                    state.activate_dialog_mode()
                    log.info("👋 Greeting registered, dialog mode activated")
            
            if "knowledge_graph" in self.memory and event_type == "user_command":
                asyncio.create_task(self._extract_kg_triplets(command_text))
            
            latest_event["processed"] = True
            
            # 🆕 Сохраняем ответ Леи в кратковременную память
            state.add_to_context({
                "type": "response",
                "content": response,
                "source": "leya",
                "timestamp": time.time()
            })

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
            state.unlock_cognition()