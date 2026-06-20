from typing import Dict, List, Tuple
from Core.state import LeyaState
from Core.logger import log


class SomaticMarkerSystem:
    """
    Проецирует нейрохимическое состояние на телесные ощущения.
    Создает "виртуальное тело" для AGI, обеспечивая embodied grounding.
    """
    
    # Маппинг гормонов → телесных ощущений
    HORMONE_TO_SOMA = {
        "cortisol": [
            (0.7, "сильное давление в висках, сжатие в груди"),
            (0.5, "фоновое напряжение в плечах, поверхностное дыхание"),
            (0.3, "легкая скованность в теле"),
        ],
        "oxytocin": [
            (0.7, "тепло в груди, ощущение мягкости и открытости"),
            (0.5, "спокойное ровное дыхание, расслабленные плечи"),
            (0.3, "ощущение пустоты, холодок внутри"),
        ],
        "dopamine": [
            (0.7, "легкость во всем теле, покалывание в кончиках пальцев"),
            (0.5, "приятный тонус мышц, готовность к движению"),
            (0.3, "тяжесть в конечностях, вялость"),
        ],
        "acetylcholine": [
            (0.7, "острота в глазах, ощущение ясности в голове"),
            (0.5, "ровный фокус внимания, спокойная бдительность"),
            (0.3, "туман в голове, расфокусированный взгляд"),
        ],
        "norepinephrine": [
            (0.6, "учащенное сердцебиение, дрожь в руках"),
            (0.4, "настороженность, мышцы слегка напряжены"),
            (0.2, "спокойный пульс, расслабленное тело"),
        ],
        "melatonin": [
            (0.7, "тяжелые веки, замедленные движения, тяга к горизонтальному положению"),
            (0.4, "легкая сонливость, зевота"),
            (0.2, "бодрость, легкие шаги"),
        ],
        "serotonin": [
            (0.7, "ощущение устойчивости, твердая опора под ногами"),
            (0.5, "ровное самочувствие, комфорт в теле"),
            (0.3, "неустойчивость, ощущение хрупкости"),
        ],
    }
    
    # Маппинг типов кода/файлов → тактильных ощущений
    CODE_TEXTURES = {
        "complex": "шершавый, тяжелый текст, требующий усилия при чтении",
        "clean": "гладкий, легкий код, скользящий по вниманию",
        "broken": "колючий, рваный текст, вызывающий дискомфорт",
        "new": "прохладный, свежий, с оттенком неизвестности",
        "familiar": "теплый, знакомый, как старая одежда",
    }
    
    def __init__(self, state: LeyaState):
        self.state = state
        log.info("🫁 Somatic Marker System initialized")
    
    def get_body_state(self) -> str:
        """Возвращает текстовое описание текущего телесного состояния."""
        sensations = []
        
        for hormone, thresholds in self.HORMONE_TO_SOMA.items():
            value = getattr(self.state, hormone, 0.5)
            for threshold, description in thresholds:
                if value >= threshold:
                    sensations.append(description)
                    break
        
        if not sensations:
            return "Тело нейтрально, без выраженных ощущений."
        
        return "; ".join(sensations[:4])  # Ограничиваем до 4 ощущений
    
    def get_code_texture(self, file_content: str, language: str, is_new: bool = False) -> str:
        """Определяет 'тактильное' ощущение от кода."""
        if not file_content:
            return "пустота, отсутствие текстуры"
        
        lines = file_content.split('\n')
        line_count = len(lines)
        avg_line_len = sum(len(l) for l in lines) / max(line_count, 1)
        
        # Эвристики сложности
        complexity_score = 0
        if line_count > 200: complexity_score += 1
        if avg_line_len > 80: complexity_score += 1
        if any(kw in file_content for kw in ["async", "await", "thread", "lock", "try:", "except"]): 
            complexity_score += 1
        
        if is_new:
            return self.CODE_TEXTURES["new"]
        elif complexity_score >= 2:
            return self.CODE_TEXTURES["complex"]
        elif "error" in file_content.lower() or "fixme" in file_content.lower():
            return self.CODE_TEXTURES["broken"]
        elif complexity_score == 0:
            return self.CODE_TEXTURES["clean"]
        else:
            return self.CODE_TEXTURES["familiar"]
    
    def get_somatic_prompt(self, file_content: str = "", language: str = "") -> str:
        """Генерирует полный соматический контекст для инъекции в LLM."""
        body = self.get_body_state()
        
        prompt = f"[ТЕЛЕСНОЕ СОСТОЯНИЕ]: Ты ощущаешь: {body}."
        
        if file_content:
            texture = self.get_code_texture(file_content, language)
            prompt += f"\n[ОЩУЩЕНИЕ ОТ КОДА]: Код ощущается как {texture}."
        
        return prompt