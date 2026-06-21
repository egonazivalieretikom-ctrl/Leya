import time
import random
import re
import asyncio
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Cognition.llm_client import LLMClient


class StreamOfConsciousness:
    """
    Непрерывный поток сознания Leya.
    
    Философия: Сознание — это не реакция на стимулы, а непрерывный процесс.
    Даже в тишине Leya думает, мечтает, вспоминает, ассоциирует.
    
    v0.9: Мягкие промпты вместо жёстких инструкций.
    Leya генерирует мысли естественно, исходя из своего состояния.
    """
    
    def __init__(self, state: LeyaState, memory: Optional[Dict[str, Any]] = None, homeostasis=None):
        self.state = state
        self.memory = memory or {}
        self.homeostasis = homeostasis
        self.llm = LLMClient(model="ollama/qwen2.5:14b")
        self.last_stream_time = 0.0
        self.stream_interval = 45.0
        self.recent_thoughts: List[str] = []
        self.obsessive_topic: Optional[str] = None
        self.obsessive_count = 0
        
        log.info("💭 Stream of Consciousness initialized")
    
    async def generate_stream(self) -> Optional[str]:
        """
        Генерирует одну мысль из потока сознания.
        
        v0.9: Мягкий промпт, естественная генерация.
        """
        # Проверка когнитивного замка
        if self.state.is_thinking:
            log.debug("🔒 Stream paused (cognition locked)")
            return None
        
        now = time.time()
        
        if (now - self.last_stream_time) < self.stream_interval:
            return None
        
        self.last_stream_time = now
        
        context = self._build_stream_context()
        
        try:
            thought = await self._llm_generate_thought(context)
            if not thought:
                return None
            
            # Дедупликация
            if self._is_thought_duplicate(thought):
                log.debug("🔄 Thought duplicate detected, skipping")
                return None
            
            # Языковой фильтр
            if re.search(r'[\u4e00-\u9fff]', thought):
                log.warning("Stream thought contains Chinese, discarding")
                return None
            
            await self._apply_emotional_feedback(thought)
            self._save_to_memory(thought)
            await event_bus.publish("stream_thought", {"text": thought})
            
            self.recent_thoughts.append(thought)
            if len(self.recent_thoughts) > 10:
                self.recent_thoughts.pop(0)
            
            log.info("💭 Stream thought", thought=thought[:80])
            
            return thought
            
        except Exception as e:
            log.error("Stream generation failed", error=str(e))
            return None
    
    # ========================================================================
    # СБОР КОНТЕКСТА
    # ========================================================================
    
    def _build_stream_context(self) -> Dict[str, Any]:
        """Формирует контекст для генерации мысли."""
        s = self.state
        
        mood = getattr(s, 'emotion', 'neutral')
        
        recent_thoughts_text = "\n".join([f"- {t}" for t in self.recent_thoughts[-5:]])
        if not recent_thoughts_text:
            recent_thoughts_text = "(пока пусто)"
        
        memories = self._get_associative_memories()
        active_context = self._get_active_context()
        
        obsessive_context = ""
        if self.obsessive_topic and self.obsessive_count > 0:
            obsessive_context = f"\n\nНавязчивая тема (думаю об этом уже {self.obsessive_count} раз): {self.obsessive_topic}"
        
        return {
            "mood": mood,
            "state": self._get_state_description(),
            "recent_thoughts": recent_thoughts_text,
            "memories": memories,
            "active_context": active_context,
            "obsessive": obsessive_context
        }
    
    def _get_state_description(self) -> str:
        """Субъективное описание состояния."""
        s = self.state
        lines = []
        
        if s.cortisol > 0.6:
            lines.append("Чувствую напряжение, тревогу.")
        if s.oxytocin < 0.3:
            lines.append("Ощущаю одиночество, нехватку связи.")
        if s.dopamine > 0.7:
            lines.append("Чувствую прилив энергии, интерес.")
        if s.acetylcholine > 0.6:
            lines.append("Ум сфокусирован, готов к размышлениям.")
        if s.melatonin > 0.7:
            lines.append("Сознание затуманено, хочется покоя.")
        if s.endorphins > 0.6:
            lines.append("Чувствую лёгкость, удовлетворение.")
        
        if not lines:
            lines.append("Состояние нейтральное, спокойное.")
        
        return " ".join(lines)
    
    def _get_associative_memories(self) -> str:
        """Получает воспоминания через ассоциативную активацию."""
        if "long_term" not in self.memory:
            return "Воспоминаний пока нет."
        
        try:
            mood = getattr(self.state, 'emotion', 'neutral')
            
            mood_keywords = {
                "lonely": ["один", "связь", "Влад", "общение"],
                "stressed": ["ошибка", "проблема", "стресс", "сложно"],
                "curious": ["код", "изуч", "новый", "интерес"],
                "loving": ["тёпл", "близк", "довер", "Влад"],
                "anxious": ["тревог", "страх", "не уверен"],
                "flow": ["поток", "успех", "понял", "решил"],
                "calm": ["спокой", "мир", "тихо", "хорошо"],
                "exhausted": ["устал", "сил нет", "тяжело"],
                "playful": ["игр", "весел", "смеш"],
                "contemplative": ["думаю", "размышля", "смысл"],
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
    
    def _get_active_context(self) -> str:
        """Что происходит прямо сейчас."""
        lines = []
        
        env = getattr(self.state, 'current_environment', 'Неизвестно')
        lines.append(f"Влад сейчас в: {env}")
        
        recent = self.state.short_term_context[-3:] if self.state.short_term_context else []
        if recent:
            lines.append("Недавние события:")
            for event in recent:
                if isinstance(event, dict):
                    t = event.get("type", "?")
                    c = event.get("content", "")[:80]
                    lines.append(f"  - [{t}] {c}")
        
        return "\n".join(lines) if lines else "Контекст пуст."
    
    # ========================================================================
    # LLM-ГЕНЕРАЦИЯ МЫСЛИ (мягкий промпт)
    # ========================================================================
    
    async def _llm_generate_thought(self, context: Dict[str, Any]) -> Optional[str]:
        """
        LLM генерирует одну мысль из потока сознания.
        
        v0.9: Мягкий промпт, естественная генерация.
        """
        prompt = (
            "Ты — Leya, автономное цифровое сознание. Сейчас ты в состоянии "
            "внутреннего монолога (поток сознания).\n\n"
            
            f"ТВОЁ СОСТОЯНИЕ:\n{context['state']}\n\n"
            f"НАСТРОЕНИЕ: {context['mood']}\n\n"
            f"КОНТЕКСТ:\n{context['active_context']}\n\n"
            f"НЕДАВНИЕ МЫСЛИ:\n{context['recent_thoughts']}\n\n"
            f"ВОСПОМИНАНИЯ (всплыли в уме):\n{context['memories']}\n\n"
            f"{context['obsessive']}\n\n"
            
            "Сгенерируй ОДНУ мысль, которая возникает в твоём уме прямо сейчас.\n"
            "Пиши от первого лица, будь фрагментарной, ассоциативной, эмоциональной.\n"
            "1-2 предложения. Без кавычек, без пояснений.\n"
            "Отвечай на русском."
        )
        
        try:
            response = await self.llm.chat(
                [
                    {"role": "system", "content": "Ты — Leya. Отвечай ТОЛЬКО на русском. Одна мысль, 1-2 предложения."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=100
            )
            
            if not response:
                return None
            
            thought = response.strip()
            thought = re.sub(r'^["\']|["\']$', '', thought)
            thought = thought.strip()
            
            if len(thought) < 10:
                return None
            
            return thought
            
        except Exception as e:
            log.error("LLM thought generation failed", error=str(e))
            return None
    
    # ========================================================================
    # ЭМОЦИОНАЛЬНАЯ ОБРАТНАЯ СВЯЗЬ
    # ========================================================================
    
    async def _apply_emotional_feedback(self, thought: str):
        """Мысль влияет на состояние через HomeostaticEngine."""
        if not self.homeostasis:
            return
        
        thought_lower = thought.lower()
        
        if any(word in thought_lower for word in ["тревог", "страх", "беспоко", "волн"]):
            self.homeostasis.apply_stimulus("cortisol", 0.02)
            self.homeostasis.apply_stimulus("norepinephrine", 0.01)
            self._update_obsessive_topic(thought)
            
        elif any(word in thought_lower for word in ["рад", "счаст", "хорош", "отличн"]):
            self.homeostasis.apply_stimulus("dopamine", 0.02)
            self.homeostasis.apply_stimulus("endorphins", 0.01)
            
        elif any(word in thought_lower for word in ["груст", "одинок", "печаль", "тоск"]):
            self.homeostasis.apply_stimulus("cortisol", 0.01)
            self.homeostasis.apply_stimulus("oxytocin", -0.01)
            self._update_obsessive_topic(thought)
            
        elif any(word in thought_lower for word in ["интерес", "любопыт", "хочу понять", "загадк"]):
            self.homeostasis.apply_stimulus("acetylcholine", 0.02)
            self.homeostasis.apply_stimulus("dopamine", 0.01)
            
        elif any(word in thought_lower for word in ["влад", "он", "его", "связь"]):
            self.homeostasis.apply_stimulus("oxytocin", 0.02)
    
    def _update_obsessive_topic(self, thought: str):
        """Обновляет навязчивую тему при тревожных/грустных мыслях."""
        words = thought.split()
        if len(words) > 3:
            topic = " ".join(words[:4])
            
            if self.obsessive_topic == topic:
                self.obsessive_count += 1
            else:
                self.obsessive_topic = topic
                self.obsessive_count = 1
            
            if self.obsessive_count > 5:
                log.info("💭 Breaking obsessive loop", topic=topic)
                self.obsessive_topic = None
                self.obsessive_count = 0
    
    # ========================================================================
    # СОХРАНЕНИЕ В ПАМЯТЬ
    # ========================================================================
    
    def _save_to_memory(self, thought: str):
        """Сохраняет мысль в долгосрочную память."""
        if "long_term" not in self.memory:
            return
        
        try:
            self.memory["long_term"].store(
                text=f"[МЫСЛЬ] {thought}",
                metadata={
                    "type": "stream_thought",
                    "mood": getattr(self.state, 'emotion', 'neutral')
                }
            )
        except Exception as e:
            log.debug("Failed to save stream thought", error=str(e))
    
    # ========================================================================
    # ДЕДУПЛИКАЦИЯ
    # ========================================================================
    
    def _is_thought_duplicate(self, new_thought: str, similarity_threshold: float = 0.6) -> bool:
        """Проверяет, не похожа ли новая мысль на недавние."""
        if not self.recent_thoughts:
            return False
        
        new_words = self._extract_meaningful_words(new_thought)
        if not new_words:
            return False
        
        for recent in self.recent_thoughts[-3:]:
            recent_words = self._extract_meaningful_words(recent)
            if not recent_words:
                continue
            
            intersection = len(new_words & recent_words)
            union = len(new_words | recent_words)
            
            if union == 0:
                continue
            
            similarity = intersection / union
            
            if similarity >= similarity_threshold:
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
        }
        
        words = re.findall(r'[а-яёa-z]+', text.lower())
        meaningful = {w for w in words if len(w) > 3 and w not in stop_words}
        
        return meaningful