from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import uvicorn
from Core.state import LeyaState
from Core.event_bus import EventBus

app = FastAPI(title="Leya OS - AGI Dashboard")

class UIServer:
    def __init__(self, state: LeyaState, event_bus: EventBus):
        self.state = state
        self.event_bus = event_bus

    async def start(self):
        @app.get("/")
        async def dashboard():
            return HTMLResponse("<h1>Leya OS v1.0 - Live Dashboard</h1><div id='status'>Connecting...</div>")

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            await self.event_bus.subscribe_global(lambda e: websocket.send_json(e.__dict__))

        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")