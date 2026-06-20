class SpeechEngine:

    def __init__(self, brain):
        self.brain = brain

    def explain_state(self, event=None, decision=None, goal=None):
        state = self.brain.state

        parts = []

        # базовое состояние
        parts.append(
            f"Энергия {state.energy:.1f}, "
            f"любопытство {state.curiosity:.2f}, "
            f"возраст {state.age}"
        )

        # цель
        if goal:
            parts.append(
                f"Текущая цель: {goal.get('kind', 'unknown')}"
            )

        # событие
        if event:
            parts.append(
                f"Наблюдение: {event.get('type', 'event')}"
            )

        # решение
        if decision:
            action = decision.get("action", "none")
            parts.append(
                f"Выбрано действие: {action}"
            )

            if "goal" in decision:
                parts.append(
                    f"Причина: поддержание цели {decision['goal'].get('kind', 'unknown')}"
                )

        return " | ".join(parts)