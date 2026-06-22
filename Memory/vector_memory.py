import chromadb
from typing import List, Dict
from Core.state import LeyaState
from Core.event_bus import EventBus, LeyaEvent

class VectorMemory:
    def __init__(self, state: LeyaState, event_bus: EventBus, path="./leya_memory_db"):
        self.state = state
        self.event_bus = event_bus
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection("long_term_memory")

    async def initialize(self):
        await self.event_bus.subscribe("thought_generated", self.store_thought)
        await self.event_bus.subscribe("user_message_processed", self.store_interaction)

    async def store_thought(self, event: LeyaEvent):
        thought = event.data.get("thought", "")
        if thought:
            self.collection.add(
                documents=[thought],
                metadatas=[{"type": "thought", "mood": self.state.mood, "time": self.state.subjective_time}],
                ids=[f"thought_{self.state.cycle_count}"]
            )

    async def store_interaction(self, event: LeyaEvent):
        text = event.data.get("text", "")
        if text:
            self.collection.add(
                documents=[text],
                metadatas=[{"type": "user_message", "mood": self.state.mood}],
                ids=[f"user_{self.state.cycle_count}"]
            )

    def search(self, query: str, n_results: int = 5) -> List[Dict]:
        results = self.collection.query(query_texts=[query], n_results=n_results)
        return results.get("documents", [[]])[0]