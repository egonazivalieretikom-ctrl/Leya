import re
import json
import asyncio
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Cognition.llm_client import LLMClient
from Cognition.fast_appraisal import FastAppraisal
from Core.somatic import SomaticMarkerSystem


class CognitionManager:
    """
    Когнитивный менеджер Фазы 3.
    Объединяет Fast Appraisal, непрерывный гомеостаз и телесное укоренение (Somatic Grounding).
    LLM интерпретирует уже готовое эмоциональное и телесное состояние.
    """
    
    def __init__(self, state: LeyaState, memory: Optional[Dict[str, Any]] = None, homeostasis=None):
        self.state = state
        self.memory = memory or {}
        self.homeostasis = homeostasis
        self.llm = LLMClient(model="ollama/qwen2.5:14b")
        self.fast_appraisal = FastAppraisal()
        self.somatic = SomaticMarkerSystem(state)
        log.info("🧠 Cognition Manager initialized (Fast Appraisal + Somatic Grounding)")
        from Core.world_model import WorldModel
        self.world_model = WorldModel()
    
    # =========================================================================
    # УПРОЩЕННЫЙ ЭНДОКРИННЫЙ ПРОМПТ
    # Детали эмоций теперь передаются через somatic_prompt
    # =========================================================================
    def _generate_endocrine_prompt(self, state: LeyaState) -> str:
        s = state
        lines = ["НЕЙРОХИМИЧЕСКИЙ ФОН:"]
        
        if getattr(s, 'cortisol', 0) > 0.6: lines.append("- Стресс повышен.")
        elif getattr(s, 'cortisol', 0) < 0.2: lines.append("- Полная безопасность.")
        
        if getattr(s, 'oxytocin', 0) > 0.6: lines.append("- Близость и доверие.")
        elif getattr(s, 'oxytocin', 0) < 0.3: lines.append("- Одиночество, отстраненность.")
        
        if getattr(s, 'dopamine', 0) > 0.7: lines.append("- Поток, высокий интерес.")
        elif getattr(s, 'dopamine', 0) < 0.3: lines.append("- Апатия, скука.")
        
        if getattr(s, 'acetylcholine', 0) > 0.6: lines.append("- Острый фокус на познании.")
        
        if getattr(s, 'melatonin', 0) > 0.7: lines.append("- Сонливость, замедленность.")
        
        if len(lines) == 1:
            return lines[0] + " Нейтральный."
        return "\n".join(lines)
    
    # =========================================================================
    # ГЛАВНЫЙ ЦИКЛ МЫШЛЕНИЯ
    # =========================================================================
    async def process(self, context: List[Dict[str, Any]], state: LeyaState, budget: float) -> Optional[Dict[str, Any]]:
        if not context:
            return None
        
        pending_events = [
            e for e in context
            if isinstance(e, dict)
            and e.get("type") in ["user_command", "vision_request", "internal_drive"]
            and not e.get("processed")
        ]
        if not pending_events:
            return None
        
        latest_event = pending_events[-1]
        event_type = latest_event.get("type")
        command_text = latest_event.get("content", "")
        
        log.info("💭 Thinking", type=event_type, content=command_text[:60])
        
        # ⚡ FAST APPRAISAL: Мгновенная лимбическая реакция (без LLM)
        stimuli = self.fast_appraisal.evaluate(
            event_type=event_type,
            content=command_text,
            context_history=[e for e in context if isinstance(e, dict)]
        )
        
        # Применяем стимулы к гомеостазу
        if self.homeostasis:
            for hormone, intensity in stimuli.items():
                if intensity != 0:
                    self.homeostasis.apply_stimulus(hormone, intensity)
            
            # Публикуем быструю реакцию в UI
            active_stimuli = {k: round(v, 2) for k, v in stimuli.items() if v != 0}
            if active_stimuli:
                await event_bus.publish("fast_reaction", {"stimuli": active_stimuli})
                log.debug("Fast Appraisal Applied", stimuli=active_stimuli)
        
        # Читаем состояние ПОСЛЕ применения стимулов
        endocrine_prompt = self._generate_endocrine_prompt(state)
        
        # Эмоционально-зависимая память
        emotional_snapshot = state.get_emotional_snapshot()
        relevant_memories = self._retrieve_mood_congruent_memories(event_type, command_text, emotional_snapshot)
        
        # Сборка контекста
        context_text = self._format_context(context[-10:])
        proprioception_note = f"[СРЕДА ПК]: Влад сейчас в окне '{getattr(state, 'current_environment', '?')}'."
        file_context_note = self._build_file_context_note(context)
        kg_context = self._build_kg_context(event_type)
        
        # 🆕 SOMATIC GROUNDING: Инъекция телесного опыта
        file_content = ""
        file_language = ""
        file_events = [e for e in context[-5:] if isinstance(e, dict) and e.get("type") == "file_context"]
        if file_events:
            file_content = file_events[-1].get("file_content", "")
            file_language = file_events[-1].get("language", "")
        
        somatic_prompt = self.somatic.get_somatic_prompt(file_content, file_language)
        
        world_context = self._build_world_context(context)

        # Финальная склейка контекста (Somatic идет первым!)
        full_context = (
            somatic_prompt + "\n\n" +
            proprioception_note + 
            kg_context + 
            file_context_note + 
            "\n\n" + context_text
        )
        if relevant_memories:
            full_context += "\n\n[Воспоминания]:\n" + "\n".join(relevant_memories)
        
        try:
            # Генерация ответа LLM с учетом УЖЕ измененного состояния и тела
            if event_type == "vision_request" and latest_event.get("image_base64"):
                response = await self.llm.think_with_vision(
                    f"История:\n{context_text}\n\nСообщение: {command_text}",
                    latest_event["image_base64"],
                    mood_prompt=endocrine_prompt
                )
            else:
                raw_response = await self.llm.think(
                    full_context, task=f"Ответь: {command_text}", mood_prompt=endocrine_prompt
                )
                
                thought_match = re.search(r'<thinking>(.*?)</thinking>', raw_response, flags=re.DOTALL)
                if thought_match:
                    await event_bus.publish("thought_process", {"text": thought_match.group(1).strip()[:500]})
                
                search_match = re.search(r'\[SEARCH: (.*?)\]', raw_response)
                calc_match = re.search(r'\[CALC: (.*?)\]', raw_response)
                
                if search_match or calc_match:
                    tool_result = await self._execute_tool(search_match, calc_match)
                    final_prompt = f"Контекст: {full_context}\n\nДанные: {tool_result}\n\nФинальный ответ."
                    response = await self.llm.think(final_prompt, task="Финальный ответ", mood_prompt=endocrine_prompt)
                else:
                    response = raw_response
            
            response = self._vacuum_clean(response)
            
            # KG extraction
            if "knowledge_graph" in self.memory and event_type == "user_command":
                asyncio.create_task(self._extract_kg_triplets(command_text))
            
            latest_event["processed"] = True
            return {"type": "response", "content": response, "source": "llm", "command": command_text}
            
        except Exception as e:
            log.error("Cognition failed", error=str(e), exc_info=True)
            if self.homeostasis:
                self.homeostasis.apply_stimulus("cortisol", 0.2)
            return {"type": "error", "content": f"Сбой: {str(e)}"}
    
    # =========================================================================
    # ЭМОЦИОНАЛЬНО-ЗАВИСИМАЯ ПАМЯТЬ
    # =========================================================================
    def _retrieve_mood_congruent_memories(self, event_type: str, query: str, snapshot: Dict) -> List[str]:
        if event_type != "user_command" or "long_term" not in self.memory:
            return []
        
        memories = self.memory["long_term"].search(query, n_results=5)
        if not memories:
            return []
        
        scored = []
        for m in memories:
            text = m.get("memory_text", "") if isinstance(m, dict) else str(m)
            score = 1.0
            
            if snapshot.get("cortisol", 0) > 0.6 and any(w in text.lower() for w in ["ошибка", "стресс", "проблем"]):
                score += 0.5
            if snapshot.get("oxytocin", 0) > 0.6 and any(w in text.lower() for w in ["тёпл", "влад", "связь", "довер"]):
                score += 0.5
            if snapshot.get("acetylcholine", 0) > 0.6 and any(w in text.lower() for w in ["код", "изуч", "архитектур"]):
                score += 0.5
            
            scored.append((score, text))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for _, text in scored[:3]]
    
    # =========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =========================================================================
    def _build_file_context_note(self, context: List[Dict[str, Any]]) -> str:
        file_events = [e for e in context[-5:] if isinstance(e, dict) and e.get("type") == "file_context"]
        if not file_events:
            return ""
        f = file_events[-1]
        content = f.get("file_content", "")
        if len(content) > 3000:
            content = content[:3000] + "\n... [обрезано] ..."
        return f"\n\n[ОБЪЕКТ НАБЛЮДЕНИЯ]:\nФайл: {f.get('file_path','?')} ({f.get('language','?')})\n```\n{content}\n```"
    
    def _build_kg_context(self, event_type: str) -> str:
        if "knowledge_graph" not in self.memory or event_type != "user_command":
            return ""
        facts = self.memory["knowledge_graph"].get_context_for("Влад")
        return f"\n\n[ФАКТЫ О ВЛАДЕ]:\n{facts}" if facts != "Нет известных фактов." else ""
    
    async def _execute_tool(self, search_match, calc_match) -> str:
        if search_match:
            from Action.tools import search_web
            return f"Поиск:\n{await asyncio.to_thread(search_web, search_match.group(1))}"
        elif calc_match:
            from Action.tools import calculate
            return f"Вычисление: {await asyncio.to_thread(calculate, calc_match.group(1))}"
        return ""
    
    def _vacuum_clean(self, response: str) -> str:
        response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
        response = re.sub(r'</?thinking>', '', response)
        response = re.sub(r'\[.*?:.*?\]', '', response)
        response = re.sub(r'\n\s*\n', '\n\n', response).strip()
        return response
    
    async def _extract_kg_triplets(self, text: str):
        try:
            prompt = f'Извлеки факты в JSON: [{{"subject":"...","predicate":"...","object":"..."}}]. Сообщение: {text}'
            json_str = await self.llm.chat([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=200)
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
        lines = []
        for e in context:
            if not isinstance(e, dict): continue
            t, c = e.get("type", "?"), e.get("content", "")
            if t == "user_command": lines.append(f"👤 Влад: {c}")
            elif t == "vision_request": lines.append(f"👁️ Изображение: {c}")
            elif t == "internal_drive": lines.append(f"💭 Мысль: {c}")
            elif t == "proprioception": lines.append(f"🖥️ Среда: {c}")
            elif t == "file_context": lines.append(f"📄 Файл: {c}")
            else: lines.append(f"[{t}]: {c}")
        return "\n".join(lines)

    def _build_world_context(self, context: List[Dict[str, Any]]) -> str:
        """Инъекция контекста World Model."""
        proprioception_events = [
            e for e in context[-5:] 
            if isinstance(e, dict) and e.get("type") == "proprioception"
        ]
        
        if not proprioception_events:
            return ""
        
        latest = proprioception_events[-1]
        window_title = latest.get("active_window", "")
        
        return self.world_model.get_context_for_llm(window_title)