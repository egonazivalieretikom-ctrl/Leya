class Planner:
    def __init__(self, bus):
        self.bus = bus

        self.bus.subscribe("curiosity_question", self.on_question)
        self.bus.subscribe("world_model_updated", self.on_world_update)
        self.bus.subscribe("action_result", self.on_result)

        self.last_world = {}
        self.pending_questions = []

        # веса стратегий
        self.strategy_weights = {
            "ask_user": 1.0,
            "observe_more": 1.0
        }

    def on_world_update(self, data):
        self.last_world = data

        stable_objects = [k for k, v in data.items() if v["is_stable"]]

        # выбор действия с учётом веса
        action = self._choose_action(len(stable_objects))

        self.bus.publish("plan_action", action)

    def on_question(self, data):
        self.pending_questions.append(data.get("question"))

        self.bus.publish("plan_action", {
            "action": "ask_user",
            "question": data.get("question")
        })

    def on_result(self, data):
        action = data.get("action")
        success = data.get("success", 0)

        # адаптация весов
        if action in self.strategy_weights:
            if success > 0.5:
                self.strategy_weights[action] *= 1.05
            else:
                self.strategy_weights[action] *= 0.95

    def _choose_action(self, stable_count):

        # базовая логика
        if stable_count < 3:
            return {
                "action": "observe_more"
            }

        # взвешенный выбор
        import random

        actions = list(self.strategy_weights.keys())
        weights = list(self.strategy_weights.values())

        chosen = random.choices(actions, weights=weights, k=1)[0]

        if chosen == "ask_user" and self.pending_questions:
            return {
                "action": "ask_user",
                "question": self.pending_questions.pop(0)
            }

        return {
            "action": chosen
        }