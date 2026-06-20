from Core.logger import log
from Core.state import LeyaState

class ActionExecutor:
    """
    Исполнитель действий. Сейчас это заглушка для фазы ACT, 
    но в будущем здесь будет выполнение кода, управление файлами и API.
    """
    def __init__(self, state: LeyaState):
        self.state = state
        log.info("⚡ Action Executor initialized")

    async def execute(self, budget: float) -> float:
        """
        Выполняет действия в фазе ACT.
        Возвращает количество потраченной энергии.
        """
        # Пока что фаза ACT просто "переваривает" опыт.
        # Реальные действия (поиск, калькулятор) мы перехватываем прямо в Cognition (ReAct).
        return 0.01 # Тратим немного энергии на поддержание систем