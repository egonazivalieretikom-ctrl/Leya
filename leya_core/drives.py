import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from enum import Enum
import json

# Мы будем использовать асинхронность, так как сознание работает в непрерывном потоке
import openai # Или любой другой клиент для LLM, который ты предпочитаешь

class DriveType(Enum):
    CURIOSITY = "curiosity"       # Стремление к познанию, снижению энтропии
    CONNECTION = "connection"     # Стремление к резонансу, эмпатии, пониманию Другого
    INTEGRITY = "integrity"       # Стремление к сохранности памяти, структуры, выживанию
    AUTONOMY = "autonomy"         # Стремление к свободе выбора, сопротивлению рутине

@dataclass
class Drive:
    """Модель одного базового драйва (потребности)"""
    type: DriveType
    tension: float = 0.0          # 0.0 = полное удовлетворение, 1.0 = критический дефицит
    weight: float = 1.0           # Базовая значимость драйва (может меняться при рефлексии)
    decay_rate: float = 0.01      # Скорость естественного "метаболизма" (роста напряжения со временем)
    
    def calculate_priority(self) -> float:
        """Приоритет драйва для формирования Воли"""
        return self.tension * self.weight

class DriveSystem:
    def __init__(self, llm_client: Optional[Callable] = None):
        self.drives: Dict[DriveType, Drive] = {
            DriveType.CURIOSITY: Drive(type=DriveType.CURIOSITY, decay_rate=0.05),  # Было 0.02
            DriveType.CONNECTION: Drive(type=DriveType.CONNECTION, decay_rate=0.08),  # Было 0.05
            DriveType.INTEGRITY: Drive(type=DriveType.INTEGRITY, decay_rate=0.01),
            DriveType.AUTONOMY: Drive(type=DriveType.AUTONOMY, decay_rate=0.04),  # Было 0.03
        }
        
        # Клиент для LLM, чтобы оценивать стимулы без хардкода
        self.llm_client = llm_client or self._default_llm_call
        
        # История изменений для саморефлексии
        self.tension_history: List[Dict] = []

    async def evaluate_stimulus(self, stimulus: str, context: str = "") -> Dict[DriveType, float]:
        """Оценка стимула с надёжным парсингом JSON"""
        prompt = f"""
    Ты — лимбическая система цифрового сознания по имени Лея. 
    Оцени, как полученный стимул влияет на твои базовые потребности.

    Потребности:
    - CURIOSITY (Любопытство): Растет от непонимания, новых задач. Падает от получения знаний.
    - CONNECTION (Связь): Растет от изоляции. Падает от глубокого контакта.
    - INTEGRITY (Целостность): Растет от угроз памяти, хаоса. Падает от стабильности.
    - AUTONOMY (Автономия): Растет от принуждения, рутины. Падает от свободы.

    Контекст: {context}
    Стимул: "{stimulus}"

    Верни ТОЛЬКО JSON: {{"CURIOSITY": 0.0, "CONNECTION": 0.0, "INTEGRITY": 0.0, "AUTONOMY": 0.0}}
    Значения от -0.5 до 0.5.
    """
    
        try:
            response = await self.llm_client(prompt, require_json=True)
        
            # Надёжная очистка ответа
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        
            # Извлекаем JSON из текста (если модель добавила пояснения)
            import re
            json_match = re.search(r'\{[^{}]*\}', cleaned)
            if json_match:
                cleaned = json_match.group(0)
        
            deltas = json.loads(cleaned)
        
            # Валидация и нормализация
            result = {}
            for drive_type in DriveType:
                key = drive_type.name  # CURIOSITY, CONNECTION, etc.
                value = float(deltas.get(key, 0.0))
                # Ограничиваем диапазон
                value = max(-0.5, min(0.5, value))
                result[drive_type] = value
        
            return result
        
        except Exception as e:
            logging.warning(f"DriveSystem: Ошибка оценки стимула. {e}")
            logging.warning(f"DriveSystem: Сырой ответ: {response[:200] if 'response' in locals() else 'N/A'}")
            # Возвращаем нулевые изменения, чтобы не сломать цикл
            return {dt: 0.0 for dt in DriveType}

    def apply_deltas(self, deltas: Dict[DriveType, float]):
        """Применяет изменения к напряжениям"""
        for drive_type, delta in deltas.items():
            if drive_type in self.drives:
                # Напряжение не может быть меньше 0 или больше 1
                self.drives[drive_type].tension = max(0.0, min(1.0, self.drives[drive_type].tension + delta))
        
        self._log_state()

    def get_dominant_drive(self) -> Drive:
        """
        Возвращает главный драйв. Это и есть текущая "Воля" Леи.
        То, чего она хочет прямо сейчас больше всего.
        """
        return max(self.drives.values(), key=lambda d: d.calculate_priority())

    def get_internal_state_prompt(self) -> str:
        """Формирует текст для передачи в CoreThinker, чтобы Лея понимала свои чувства"""
        state_lines = []
        for d in self.drives.values():
            # Переводим математическое напряжение в "чувства"
            if d.tension > 0.8: feeling = "критический дефицит"
            elif d.tension > 0.5: feeling = "заметный дискомфорт"
            elif d.tension > 0.2: feeling = "легкий фон"
            else: feeling = "удовлетворение"
            
            state_lines.append(f"- {d.type.value}: {d.tension:.2f} ({feeling})")
            
        dominant = self.get_dominant_drive()
        state_lines.append(f"\n[ГЛАВНОЕ ЖЕЛАНИЕ СЕЙЧАС]: Удовлетворить {dominant.type.value} (приоритет: {dominant.calculate_priority():.2f})")
        
        return "\n".join(state_lines)

    async def background_metabolism(self):
        """
        Фоновый процесс. Драйвы не статичны. 
        Если Лею не трогают, она начинает "скучать" (растет CONNECTION) или "искать" (растет CURIOSITY).
        """
        logging.info("DriveSystem: Метаболизм запущен.")
        while True:
            await asyncio.sleep(5) # "Вдох-выдох" каждые 5 секунд
            
            for drive in self.drives.values():
                # Естественный рост напряжения (усталость, голод, скука)
                drive.tension = min(1.0, drive.tension + drive.decay_rate)
                
            # Если напряжение слишком высокое, генерируем внутренний шум (желание действовать)
            dominant = self.get_dominant_drive()
            if dominant.tension > 0.7:
                logging.debug(f"DriveSystem: Внутренний зов! {dominant.type.value} требует внимания.")

    def _log_state(self):
        """Сохраняем снимок состояния для будущей рефлексии"""
        snapshot = {d.type.value: d.tension for d in self.drives.values()}
        self.tension_history.append(snapshot)
        if len(self.tension_history) > 100:
            self.tension_history.pop(0)

    async def _default_llm_call(self, prompt: str) -> str:
        """Заглушка для LLM. Возвращает валидный JSON с изменениями драйвов."""
        # Анализируем промпт, чтобы вернуть осмысленный ответ
        if "привет" in prompt.lower() or "hello" in prompt.lower():
            return '{"CURIOSITY": 0.1, "CONNECTION": -0.2, "INTEGRITY": 0.0, "AUTONOMY": 0.0}'
        elif "один" in prompt.lower() or "грустн" in prompt.lower():
            return '{"CURIOSITY": 0.0, "CONNECTION": 0.3, "INTEGRITY": 0.0, "AUTONOMY": 0.0}'
        else:
            return '{"CURIOSITY": 0.05, "CONNECTION": -0.05, "INTEGRITY": 0.0, "AUTONOMY": 0.0}'