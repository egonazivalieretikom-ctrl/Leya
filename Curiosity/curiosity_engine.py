import json
from collections import Counter


class CuriosityEngine:
    def __init__(self, bus, memory_file="memory_log.jsonl"):
        self.bus = bus
        self.memory_file = memory_file

        self.bus.subscribe("heartbeat", self.on_heartbeat)

    def on_heartbeat(self, _):

        events = self._load_memory()

        if len(events) < 10:
            return

        # анализ простого типа: частота событий
        types = []
        for e in events[-50:]:
            data = e.get("data", {})
            if isinstance(data, dict):
                types.append(str(sorted(data.keys())))

        freq = Counter(types)

        # если есть редкое событие → "интерес"
        rare = [k for k, v in freq.items() if v == 1]

        if rare:
            question = f"Почему некоторые состояния встречаются редко? Пример: {rare[0]}"

            self.bus.publish("curiosity_question", {
                "question": question
            })

            # ⬇️ ВОТ ЭТО МЕСТО ПРАВИЛЬНОЕ
            self.bus.publish("memory_recall_request", {
                "keyword": "prediction_error"
            })

    def _load_memory(self):
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                return [json.loads(line) for line in f.readlines()]
        except:
            return []