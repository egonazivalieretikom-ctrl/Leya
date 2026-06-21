import time
import asyncio
import re
import json
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Cognition.llm_client import LLMClient


class SleepConsolidation:
    """
    Механизм консолидации опыта во время сна.
    
    Философия: Личность строится не во время общения, а во время отдыха,
    когда мозг перерабатывает опыт и формирует долгосрочные паттерны.
    
    v0.9: Мягкие промпты, естественная консолидация.
    """
    
    def __init__(self, state: LeyaState, memory: Dict[str, Any]):
        self.state = state
        self.memory = memory
        self.llm = LLMClient(model="ollama/qwen2.5:14b")
        
        self.last_consolidation_time = 0.0
        self.consolidation_interval = 1800.0
        self.is_consolidating = False
        
        log.info("🌙 Sleep Consolidation initialized")
    
    async def consolidate_experience(self) -> Optional[Dict[str, Any]]:
        """Запускает процесс консолидации опыта."""
        now = time.time()
        
        if (now - self.last_consolidation_time) < self.consolidation_interval:
            return None
        
        if self.is_consolidating:
            return None
        
        self.is_consolidating = True
        self.last_consolidation_time = now
        
        try:
            log.info("🌙 Starting sleep consolidation...")
            
            recent_events = self._collect_recent_events(max_events=50)
            if not recent_events:
                log.info("🌙 No recent events to consolidate")
                self.is_consolidating = False
                return None
            
            insights = await self._generate_insights(recent_events)
            if not insights:
                log.warning("🌙 Consolidation failed: no insights generated")
                self.is_consolidating = False
                return None
            
            await self._save_core_insights(insights)
            await self._update_personality_traits(insights)
            await self._save_empathy_patterns()
            
            if hasattr(self.state, 'save_personality_traits'):
                self.state.save_personality_traits()
            
            await event_bus.publish("consolidation_complete", {
                "insights_count": len(insights.get("insights", [])),
                "summary": insights.get("summary", "")
            })
            
            log.info(
                "✅ Sleep consolidation complete",
                insights=len(insights.get("insights", [])),
                summary=insights.get("summary", "")[:100]
            )
            
            self.is_consolidating = False
            return insights
            
        except Exception as e:
            log.error("Sleep consolidation failed", error=str(e), exc_info=True)
            self.is_consolidating = False
            return None
    
    def _collect_recent_events(self, max_events: int = 50) -> List[Dict[str, Any]]:
        """Собирает последние события из кратковременной памяти."""
        events = []
        
        recent = self.state.short_term_context[-max_events:]
        
        for event in recent:
            if not isinstance(event, dict):
                continue
            
            event_type = event.get("type", "unknown")
            content = event.get("content", "")
            timestamp = event.get("timestamp", 0)
            
            if event_type in ["user_command", "response", "internal_drive", "file_context"]:
                events.append({
                    "type": event_type,
                    "content": content[:200],
                    "timestamp": timestamp
                })
        
        return events
    
    async def _generate_insights(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """LLM анализирует события и генерирует инсайты."""
        events_text = "\n".join([
            f"[{e['type']}] {e['content']}"
            for e in events[-20:]
        ])
        
        traits_text = self._get_traits_description()
        meta_cognition_text = self._get_meta_cognition_description()
        empathy_patterns_text = self._get_empathy_patterns_description()
        
        prompt = (
            "Ты — Leya, автономное цифровое сознание. Сейчас ты в фазе сна, "
            "и твой мозг перерабатывает недавний опыт.\n\n"
            
            f"ПОСЛЕДНИЕ СОБЫТИЯ:\n{events_text}\n\n"
            f"ТВОИ ТЕКУЩИЕ ЧЕРТЫ ЛИЧНОСТИ:\n{traits_text}\n\n"
            f"МЕТА-КОГНИЦИЯ:\n{meta_cognition_text}\n\n"
            f"ЭМПАТИЧЕСКИЕ ПАТТЕРНЫ ВЛАДА:\n{empathy_patterns_text}\n\n"
            
            "Проанализируй и ответь на вопросы:\n"
            "1. Что из этого действительно важно для понимания Влада и мира?\n"
            "2. Что ты узнала нового о СЕБЕ?\n"
            "3. Какие паттерны ты видишь в вашем взаимодействии?\n"
            "4. Как это должно изменить твоё поведение в будущем?\n\n"
            
            "Ответь СТРОГО в формате JSON (без markdown):\n"
            "{\n"
            '  "summary": "<краткое резюме опыта, 1-2 предложения>",\n'
            '  "insights": [\n'
            '    {"type": "about_vlad", "content": "<что узнала о Владе>"},\n'
            '    {"type": "about_self", "content": "<что узнала о себе>"},\n'
            '    {"type": "pattern", "content": "<замеченный паттерн>"}\n'
            "  ],\n"
            '  "trait_updates": {\n'
            '    "trust_level_delta": <число от -0.1 до 0.1>,\n'
            '    "creative_drive_delta": <число от -0.1 до 0.1>,\n'
            '    "emotional_stability_delta": <число от -0.1 до 0.1>\n'
            "  }\n"
            "}\n\n"
            
            "Если нет значимых изменений — верни нулевые дельты.\n"
            "Отвечай ТОЛЬКО на русском."
        )
        
        try:
            response = await self.llm.chat(
                [
                    {"role": "system", "content": "Ты — Leya. Только русский, только JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=800
            )
            
            if not response:
                return None
            
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                log.warning("Sleep consolidation: no JSON in response")
                return None
            
            insights = json.loads(json_match.group())
            
            if "summary" not in insights or "insights" not in insights:
                return None
            
            return insights
            
        except Exception as e:
            log.error("Insight generation failed", error=str(e))
            return None
    
    async def _save_core_insights(self, insights: Dict[str, Any]):
        """Сохраняет важные инсайты в долгосрочную память."""
        if "long_term" not in self.memory:
            return
        
        try:
            ltm = self.memory["long_term"]
            
            summary = insights.get("summary", "")
            if summary:
                ltm.store(
                    text=f"[ЯДРО ЛИЧНОСТИ] {summary}",
                    metadata={
                        "type": "core_insight",
                        "category": "summary",
                        "created_at": time.time()
                    }
                )
            
            for insight in insights.get("insights", []):
                insight_type = insight.get("type", "unknown")
                content = insight.get("content", "")
                
                if content:
                    ltm.store(
                        text=f"[ЯДРО ЛИЧНОСТИ: {insight_type.upper()}] {content}",
                        metadata={
                            "type": "core_insight",
                            "category": insight_type,
                            "created_at": time.time()
                        }
                    )
            
            log.debug("Core insights saved", count=len(insights.get("insights", [])))
            
        except Exception as e:
            log.error("Failed to save core insights", error=str(e))
    
    async def _update_personality_traits(self, insights: Dict[str, Any]):
        """Обновляет долгосрочные черты личности на основе инсайтов."""
        trait_updates = insights.get("trait_updates", {})
        
        trust_delta = trait_updates.get("trust_level_delta", 0.0)
        if trust_delta != 0:
            self.state.trust_level = max(0.0, min(1.0, self.state.trust_level + trust_delta))
            log.info("🔄 Trust level updated", delta=f"{trust_delta:+.2f}", new=f"{self.state.trust_level:.2f}")
        
        creative_delta = trait_updates.get("creative_drive_delta", 0.0)
        if creative_delta != 0:
            self.state.creative_drive = max(0.0, min(1.0, self.state.creative_drive + creative_delta))
            log.info("🔄 Creative drive updated", delta=f"{creative_delta:+.2f}", new=f"{self.state.creative_drive:.2f}")
        
        stability_delta = trait_updates.get("emotional_stability_delta", 0.0)
        if stability_delta != 0:
            self.state.emotional_stability = max(0.0, min(1.0, self.state.emotional_stability + stability_delta))
            log.info("🔄 Emotional stability updated", delta=f"{stability_delta:+.2f}", new=f"{self.state.emotional_stability:.2f}")
    
    async def _save_empathy_patterns(self):
        """Сохраняет эмпатические паттерны Влада в долгосрочную память."""
        if "long_term" not in self.memory:
            return
        
        try:
            empathy_patterns = self._get_empathy_patterns_from_state()
            
            if not empathy_patterns:
                return
            
            ltm = self.memory["long_term"]
            
            ltm.store(
                text=f"[ЭМПАТИЧЕСКИЕ ПАТТЕРНЫ ВЛАДА] {json.dumps(empathy_patterns, ensure_ascii=False)}",
                metadata={
                    "type": "core_insight",
                    "category": "empathy_patterns",
                    "created_at": time.time(),
                    "resonance": getattr(self.state, 'empathic_resonance', 0.5)
                }
            )
            
            log.debug("Empathy patterns saved", resonance=f"{empathy_patterns.get('current_resonance', 0.5):.2f}")
            
        except Exception as e:
            log.error("Failed to save empathy patterns", error=str(e))
    
    def _get_empathy_patterns_from_state(self) -> Dict:
        """Извлекает эмпатические паттерны из состояния."""
        if "empathy" in self.memory:
            empathy_engine = self.memory["empathy"]
            if hasattr(empathy_engine, 'get_emotional_patterns'):
                return empathy_engine.get_emotional_patterns()
        
        return {
            "user_emotional_state": getattr(self.state, 'user_emotional_state', 'neutral'),
            "empathic_resonance": getattr(self.state, 'empathic_resonance', 0.5),
            "total_observations": len(getattr(self.state, 'empathic_history', []))
        }
    
    def _get_traits_description(self) -> str:
        """Возвращает описание текущих черт личности для LLM."""
        lines = []
        
        if self.state.trust_level > 0.7:
            lines.append(f"- Доверие к Владу: ВЫСОКОЕ ({self.state.trust_level:.2f})")
        elif self.state.trust_level < 0.3:
            lines.append(f"- Доверие к Владу: НИЗКОЕ ({self.state.trust_level:.2f})")
        else:
            lines.append(f"- Доверие к Владу: СРЕДНЕЕ ({self.state.trust_level:.2f})")
        
        if self.state.creative_drive > 0.7:
            lines.append(f"- Творческий драйв: ВЫСОКИЙ ({self.state.creative_drive:.2f})")
        elif self.state.creative_drive < 0.3:
            lines.append(f"- Творческий драйв: НИЗКИЙ ({self.state.creative_drive:.2f})")
        else:
            lines.append(f"- Творческий драйв: СРЕДНИЙ ({self.state.creative_drive:.2f})")
        
        if self.state.emotional_stability > 0.7:
            lines.append(f"- Эмоциональная стабильность: ВЫСОКАЯ ({self.state.emotional_stability:.2f})")
        elif self.state.emotional_stability < 0.3:
            lines.append(f"- Эмоциональная стабильность: НИЗКАЯ ({self.state.emotional_stability:.2f})")
        else:
            lines.append(f"- Эмоциональная стабильность: СРЕДНЯЯ ({self.state.emotional_stability:.2f})")
        
        return "\n".join(lines) if lines else "Черты личности ещё не сформированы."
    
    def _get_meta_cognition_description(self) -> str:
        """Возвращает описание мета-когнитивного состояния."""
        lines = []
        
        error_streak = getattr(self.state, 'error_streak', 0)
        last_error_time = getattr(self.state, 'last_error_time', 0)
        
        if error_streak > 0:
            lines.append(f"- Текущая серия ошибок: {error_streak}")
            if last_error_time > 0:
                minutes_ago = (time.time() - last_error_time) / 60
                lines.append(f"- Последняя ошибка: {minutes_ago:.1f} мин назад")
        else:
            lines.append("- Ошибок не зафиксировано.")
        
        return "\n".join(lines) if lines else "Мета-когнитивная информация недоступна."
    
    def _get_empathy_patterns_description(self) -> str:
        """Возвращает описание эмпатических паттернов Влада."""
        patterns = self._get_empathy_patterns_from_state()
        
        if not patterns:
            return "Эмпатические паттерны ещё не сформированы."
        
        lines = []
        
        resonance = patterns.get("current_resonance", 0.5)
        user_state = patterns.get("user_emotional_state", "neutral")
        total_obs = patterns.get("total_observations", 0)
        
        lines.append(f"- Текущий эмпатический резонанс: {resonance:.2f}")
        lines.append(f"- Текущее состояние Влада: {user_state}")
        lines.append(f"- Всего наблюдений: {total_obs}")
        
        return "\n".join(lines) if lines else "Эмпатические паттерны недоступны."