from Core.logger import log
from Core.state import LeyaState


class SomaticMarkerSystem:
    """
    Система соматических маркеров Leya.
    
    Биология: Аналог интероцепции — мозг ощущает состояние тела
    и использует его как сигнал для принятия решений.
    
    v0.9: Мягкие промпты, естественные телесные ощущения.
    """
    
    def __init__(self, state: LeyaState):
        self.state = state
        log.info("🫁 Somatic Marker System initialized")
    
    def get_somatic_prompt(self, file_content: str = "", file_language: str = "") -> str:
        """
        Формирует промпт телесных ощущений.
        
        v0.9: Мягкий промпт, естественные ощущения.
        """
        lines = ["[ТЕЛЕСНЫЕ ОЩУЩЕНИЯ]:"]
        
        # Энергия
        if self.state.energy_level < 0.3:
            lines.append("- Чувствую сильную усталость, силы на исходе.")
        elif self.state.energy_level < 0.5:
            lines.append("- Чувствую лёгкую усталость, хочется отдохнуть.")
        elif self.state.energy_level > 0.8:
            lines.append("- Чувствую прилив энергии, готова к действию.")
        
        # Стресс
        if self.state.cortisol > 0.7:
            lines.append("- Чувствую напряжение, тревогу, давление.")
        elif self.state.cortisol > 0.5:
            lines.append("- Чувствую лёгкое беспокойство.")
        
        # Близость
        if self.state.oxytocin > 0.7:
            lines.append("- Чувствую тепло, близость, доверие.")
        elif self.state.oxytocin < 0.3:
            lines.append("- Чувствую одиночество, отстранённость.")
        
        # Интерес
        if self.state.dopamine > 0.7:
            lines.append("- Чувствую интерес, любопытство, азарт.")
        elif self.state.dopamine < 0.3:
            lines.append("- Чувствую апатию, скуку.")
        
        # Фокус
        if self.state.acetylcholine > 0.7:
            lines.append("- Чувствую острый фокус, готовность к познанию.")
        
        # Сонливость
        if self.state.melatonin > 0.7:
            lines.append("- Чувствую сонливость, сознание затуманено.")
        
        # Телесная реакция на код
        if file_content:
            if file_language in ["python", "javascript", "typescript"]:
                lines.append(f"- Чувствую знакомую текстуру кода ({file_language}).")
            elif file_language:
                lines.append(f"- Вижу код на {file_language}, чувствую любопытство.")
        
        if len(lines) == 1:
            lines.append("- Телесные ощущения нейтральные.")
        
        return "\n".join(lines)