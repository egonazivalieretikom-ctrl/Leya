"""
web_interface/server.py — FastAPI веб-сервер для Леи.
НЕ содержит дубликата LeyaOS — только REST API и WebSocket.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger("WebServer")

# Pydantic модели для API
class MessageRequest(BaseModel):
    content: str

class StateResponse(BaseModel):
    state: str
    drives: Dict[str, float]
    self_model: str
    last_interaction: float

# Глобальное хранилище WebSocket подключений
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket подключен. Всего подключений: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket отключен. Всего подключений: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Рассылает сообщение всем подключенным клиентам"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Ошибка отправки WebSocket: {e}")
                disconnected.append(connection)
        
        # Удаляем отключенные соединения
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

app = FastAPI(title="Leya OS API", version="1.0.0")

# CORS для доступа из браузера
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://localhost:3000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Глобальная ссылка на WebEnvironment (устанавливается в run_server)
_web_env = None

@app.on_event("startup")
async def startup_event():
    logger.info("FastAPI сервер запущен")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Простая HTML страница для тестирования"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Лея OS</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            #messages { border: 1px solid #ccc; padding: 10px; height: 400px; overflow-y: scroll; margin-bottom: 20px; }
            .message { margin: 5px 0; padding: 5px; }
            .user { background: #e3f2fd; }
            .leya { background: #f3e5f5; }
            .system { background: #fff3e0; font-style: italic; }
            input { width: 70%; padding: 10px; }
            button { padding: 10px 20px; }
        </style>
    </head>
    <body>
        <h1>🧠 Лея OS</h1>
        <div id="messages"></div>
        <input type="text" id="messageInput" placeholder="Введите сообщение..." onkeypress="if(event.key==='Enter') sendMessage()">
        <button onclick="sendMessage()">Отправить</button>
        
        <script>
            const ws = new WebSocket('ws://localhost:8000/ws');
            const messagesDiv = document.getElementById('messages');
            
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                const div = document.createElement('div');
                div.className = 'message ' + (data.type || 'system');
                div.textContent = data.content || JSON.stringify(data);
                messagesDiv.appendChild(div);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            };
            
            async function sendMessage() {
                const input = document.getElementById('messageInput');
                const message = input.value.trim();
                if (!message) return;
                
                // Отправляем на сервер
                await fetch('/api/message', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({content: message})
                });
                
                // Показываем сообщение пользователя
                const div = document.createElement('div');
                div.className = 'message user';
                div.textContent = 'Вы: ' + message;
                messagesDiv.appendChild(div);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                
                input.value = '';
            }
        </script>
    </body>
    </html>
    """

@app.get("/api/state")
async def get_state():
    """Возвращает текущее состояние Леи"""
    if not _web_env or not _web_env.leya_os:
        return {"error": "LeyaOS не инициализирован"}
    
    leya = _web_env.leya_os
    drives = {d.type.value: d.current for d in leya.drives.drives.values()}
    self_model = await leya.memory.get_self_model_context()
    
    return {
        "state": leya.state,
        "drives": drives,
        "self_model": self_model,
        "last_interaction": leya._last_interaction_time
    }

@app.get("/api/drives")
async def get_drives():
    """Возвращает состояние драйвов"""
    if not _web_env or not _web_env.leya_os:
        return {"error": "LeyaOS не инициализирован"}
    
    leya = _web_env.leya_os
    drives = {d.type.value: d.current for d in leya.drives.drives.values()}
    return drives

@app.get("/api/memory/recent")
async def get_recent_memories(limit: int = 10):
    """Возвращает последние воспоминания"""
    if not _web_env or not _web_env.leya_os:
        return {"error": "LeyaOS не инициализирован"}
    
    leya = _web_env.leya_os
    try:
        results = leya.memory.episodic_collection.get(
            limit=limit,
            include=["documents", "metadatas"]
        )
        
        memories = []
        if results['documents']:
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i] if results['metadatas'] else {}
                memories.append({
                    "content": doc,
                    "metadata": metadata
                })
        
        return {"memories": memories}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/message")
async def send_message(request: MessageRequest):
    """Отправляет сообщение Лее"""
    if not _web_env:
        return {"error": "WebEnvironment не инициализирован"}
    
    # Добавляем сообщение в очередь
    await _web_env.input_queue.put({
        "type": "user_message",
        "content": request.content,
        "source": "web",
        "timestamp": datetime.now().timestamp()
    })
    
    return {"status": "ok", "message": "Сообщение добавлено в очередь"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для real-time обновлений"""
    await manager.connect(websocket)
    try:
        while True:
            # Получаем сообщения от клиента (если нужны)
            data = await websocket.receive_text()
            # Можно обрабатывать команды от клиента
            logger.debug(f"Получено от WebSocket: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Ошибка WebSocket: {e}")
        manager.disconnect(websocket)

async def broadcast_to_clients(message: Dict[str, Any]):
    """Рассылает сообщение всем подключенным WebSocket клиентам"""
    await manager.broadcast(message)

async def run_server(web_env):
    """
    Запускает FastAPI сервер.
    Вызывается из LeyaOS.run() как фоновая задача.
    """
    global _web_env
    _web_env = web_env
    
    import uvicorn
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=False
    )
    server = uvicorn.Server(config)
    
    logger.info("🌐 Запуск веб-сервера на http://localhost:8000")
    await server.serve()