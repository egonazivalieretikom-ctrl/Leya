import re
import random
from typing import List, Dict, Any, Optional
from langdetect import detect, LangDetectException
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Cognition.llm_client import LLMClient


class DefaultModeNetwork:
    """
    Сеть пассивного режима с жестким языковым фильтром.
    Использует langdetect для программного отброса не-русских инсайтов.
    """
    
    def __init__(self, state: LeyaState, memory: Optional[Dict[str, Any]] = None):
        self.state = state
        self.memory = memory or {}
        self.llm = LLMClient(model="ollama/qwen2.5:14b")
        log.info("🧠 Default Mode Network initialized (with langdetect)")
    
    async def reflect(self) -> Optional[str]:
        if "long_term" not in self.memory:
            return None
        
        try:
            all_memories = self.memory["long_term"].collection.get(limit=50)
            if not all_memories or not all_memories.get('documents'):
                return None
            
            docs = all_memories['documents']
            sample_size = min(3, len(docs))
            sample = random.sample(docs, sample_size)
            memories_text = "\n".join([f"- {m}" for m in sample])
            
            prompt = (
                "Ты — Leya. Сейчас ты в состоянии покоя.\n"
                "Размышляй над воспоминаниями:\n\n"
                f"{memories_text}\n\n"
                "Найди неочевидную связь или инсайт о Владиславе или о себе.\n"
                "Ответь ОДНИМ коротким предложением."
            )
            
            insight = await self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": "Ты — Leya. Отвечай ТОЛЬКО на русском языке."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=100
            )
            
            cleaned = insight.strip()
            
            # 🛡️ ПРОГРАММНЫЙ ФИЛЬТР ЯЗЫКА (не промпт!)
            if len(cleaned) < 10:
                log.debug("DMN insight too short, discarding")
                return None
            
            try:
                detected_lang = detect(cleaned)
                if detected_lang != 'ru':
                    log.warning(f"DMN generated non-Russian text ({detected_lang}), discarding")
                    return None
            except LangDetectException:
                log.warning("DMN language detection failed, discarding")
                return None
            
            # 🛡️ Regex-фильтр китайских символов (дополнительная защита)
            if re.search(r'[\u4e00-\u9fff]', cleaned):
                log.warning("DMN generated Chinese characters, discarding")
                return None
            
            log.info("💡 DMN Insight generated", insight=cleaned[:100])
            
            self.memory["long_term"].store(
                text=f"[ИНСАЙТ] {cleaned}",
                metadata={"type": "insight", "source": "dmn"}
            )
            
            await event_bus.publish("dmn_insight", {"text": cleaned})
            return cleaned
            
        except Exception as e:
            log.error("DMN reflection failed", error=str(e))
            return None