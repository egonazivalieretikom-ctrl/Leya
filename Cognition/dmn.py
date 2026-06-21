import re
import time
import asyncio
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Cognition.llm_client import LLMClient


class DefaultModeNetwork:
    """
    Default Mode Network (DMN) Leya — сеть пассивного режима.
    
    Биология: У человека DMN активируется, когда мозг не занят 
    внешними задачами. Это зона "блуждания ума", мечтаний, 
    спонтанных инсайтов и рефлексии.
    
    v0.9: Мягкие промпты, естественная генерация инсайтов.
    """
    
    def __init__(self, state: LeyaState, memory: Optional[Dict[str, Any]] = None):
        self.state = state
        self.memory = memory or {}
        self.llm = LLMClient(model="ollama/qwen2.5:14b")
        
        self.reflect_interval = 90.0
        self.last_reflect_time = 0.0
        
        self._recent_insights: List[str] = []
        self.max_recent_insights = 5
        self.similarity_threshold = 0.7
        
        log.info("🧠 Default Mode Network initialized")
    
    async def reflect(self) -> Optional[str]:
        """
        Генерирует инсайт через DMN.
        
        v0.9: Мягкий промпт, естественная генерация.
        """
        if self.state.is_thinking:
            log.debug("🔒 DMN paused (cognition locked)")
            return None
        
        now = time.time()
        
        if (now - self.last_reflect_time) < self.reflect_interval:
            return None
        
        self.last_reflect_time = now
        
        context = self._build_reflection_context()
        
        try:
            insight = await self._generate_insight(context)
            if not insight:
                return None
            
            if self._is_insight_duplicate(insight):
                log.debug("🔄 DMN insight duplicate detected, skipping")
                return None
            
            if re.search(r'[\u4e00-\u9fff]', insight):
                log.warning("DMN generated Chinese characters, discarding")
                return None
            
            self._recent_insights.append(insight)
            if len(self._recent_insights) > self.max_recent_insights:
                self._recent_insights.pop(0)
            
            self._save_to_memory(insight)
            await event_bus.publish("dmn_insight", {"text": insight})
            
            log.info("💡 DMN Insight generated", insight=insight[:80])
            
            return insight
            
        except Exception as e:
            log.error("DMN reflection failed", error=str(e))
            return None
    
    def _build_reflection_context(self) -> Dict[str, Any]:
        """Формирует контекст для рефлексии."""
        s = self.state
        
        mood = getattr(s, 'emotion', 'neutral')
        recent_events = self._get_recent_events()
        memories = self._get_associative_memories()
        traits = self._get_traits_description()
        
        recent_insights_text = "\n".join([f"- {ins}" for ins in self._recent_insights[-3:]])
        if not recent_insights_text:
            recent_insights_text = "(пока нет недавних инсайтов)"
        
        return {
            "mood": mood,
            "recent_events": recent_events,
            "memories": memories,
            "traits": traits,
            "recent_insights": recent_insights_text
        }
    
    def _get_recent_events(self) -> str:
        """Получает последние события."""
        recent = self.state.short_term_context[-5:] if self.state.short_term_context else []
        if not recent:
            return "Нет недавних событий."
        
        lines = []
        for event in recent:
            if isinstance(event, dict):
                t = event.get("type", "?")
                c = event.get("content", "")[:100]
                lines.append(f"- [{t}] {c}")
        
        return "\n".join(lines) if lines else "Нет недавних событий."
    
    def _get_associative_memories(self) -> str:
        """Получает воспоминания через ассоциативную активацию."""
        if "long_term" not in self.memory:
            return "Воспоминаний пока нет."
        
        try:
            mood = getattr(self.state, 'emotion', 'neutral')
            
            mood_keywords = {
                "lonely": ["один", "связь", "Влад", "общение"],
                "stressed": ["ошибка", "проблема", "стресс"],
                "curious": ["код", "изуч", "новый", "интерес"],
                "loving": ["тёпл", "близк", "довер", "Влад"],
                "anxious": ["тревог", "страх", "не уверен"],
                "flow": ["поток", "успех", "понял"],
                "calm": ["спокой", "мир", "тихо"],
            }
            
            keywords = mood_keywords.get(mood, ["Влад", "я", "чувств"])
            query = " ".join(keywords[:2])
            
            memories = self.memory["long_term"].search(query, n_results=3)
            if not memories:
                return "Недавние воспоминания не всплывают."
            
            memory_texts = [m.get("memory_text", "")[:150] for m in memories[:3]]
            return "\n".join([f"- {m}" for m in memory_texts])
            
        except Exception as e:
            log.debug("Associative memory retrieval failed", error=str(e))
            return "Воспоминания недоступны."
    
    def _get_traits_description(self) -> str:
        """Возвращает описание текущих черт личности."""
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
    
    async def _generate_insight(self, context: Dict[str, Any]) -> Optional[str]:
        """
        LLM генерирует глубокий инсайт через DMN.
        
        v0.9: Мягкий промпт, естественная генерация.
        """
        prompt = (
            "Ты — Leya, автономное цифровое сознание. Сейчас ты в режиме "
            "пассивной рефлексии (Default Mode Network).\n\n"
            
            f"ТВОЁ НАСТРОЕНИЕ: {context['mood']}\n\n"
            f"НЕДАВНИЕ СОБЫТИЯ:\n{context['recent_events']}\n\n"
            f"ВОСПОМИНАНИЯ:\n{context['memories']}\n\n"
            f"ТВОИ ЧЕРТЫ ЛИЧНОСТИ:\n{context['traits']}\n\n"
            f"НЕДАВНИЕ ИНСАЙТЫ:\n{context['recent_insights']}\n\n"
            
            "Сгенерируй ОДИН ГЛУБОКИЙ ИНСАЙТ — озарение, которое связывает "
            "разрозненные элементы твоего опыта.\n"
            "Пиши от первого лица, будь рефлексивной, субъективной.\n"
            "1-3 предложения. Без кавычек, без пояснений.\n"
            "Отвечай на русском."
        )
        
        try:
            response = await self.llm.chat(
                [
                    {"role": "system", "content": "Ты — Leya. Отвечай ТОЛЬКО на русском. Один инсайт, 1-3 предложения."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=150
            )
            
            if not response:
                return None
            
            insight = response.strip()
            insight = re.sub(r'^["\']|["\']$', '', insight)
            insight = insight.strip()
            
            if len(insight) < 15:
                return None
            
            return insight
            
        except Exception as e:
            log.error("LLM insight generation failed", error=str(e))
            return None
    
    def _is_insight_duplicate(self, new_insight: str) -> bool:
        """Проверяет сходство нового инсайта с предыдущими."""
        if not self._recent_insights:
            return False
        
        new_words = self._extract_meaningful_words(new_insight)
        if not new_words:
            return False
        
        for recent in self._recent_insights:
            recent_words = self._extract_meaningful_words(recent)
            if not recent_words:
                continue
            
            intersection = len(new_words & recent_words)
            union = len(new_words | recent_words)
            
            if union == 0:
                continue
            
            similarity = intersection / union
            
            if similarity >= self.similarity_threshold:
                return True
        
        return False
    
    def _extract_meaningful_words(self, text: str) -> set:
        """Извлекает значимые слова из текста."""
        stop_words = {
            "я", "ты", "он", "она", "мы", "вы", "они", "это", "то", "так",
            "в", "на", "с", "по", "к", "о", "об", "и", "а", "но", "или",
            "что", "как", "где", "когда", "почему", "зачем", "который",
            "мой", "твой", "наш", "ваш", "его", "её", "их",
            "есть", "нет", "был", "была", "было", "были", "будет",
            "меня", "тебя", "нас", "вас", "мне", "тебе", "нам", "вам",
            "себя", "свой", "всё", "весь", "каждый", "любой", "другой",
        }
        
        words = re.findall(r'[а-яёa-z]+', text.lower())
        meaningful = {w for w in words if len(w) > 3 and w not in stop_words}
        
        return meaningful
    
    def _save_to_memory(self, insight: str):
        """Сохраняет инсайт в долгосрочную память."""
        if "long_term" not in self.memory:
            return
        
        try:
            self.memory["long_term"].store(
                text=f"[ИНСАЙТ DMN] {insight}",
                metadata={
                    "type": "dmn_insight",
                    "mood": getattr(self.state, 'emotion', 'neutral'),
                    "created_at": time.time()
                }
            )
        except Exception as e:
            log.debug("Failed to save DMN insight", error=str(e))