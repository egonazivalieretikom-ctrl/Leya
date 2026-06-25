"""
web_interface/web_environment.py — Веб-интерфейс для Леи через FastAPI + WebSocket.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from leya_core.environment import Environment

logger = logging.getLogger("WebEnvironment")


class WebEnvironment(Environment):
    """Веб-интерфейс для Леи."""
    
    def __init__(self, leya_os):
        super().__init__(leya_os)
        self.active_connections: List = []
        self.input_queue = asyncio.Queue()
        self.state = type('State', (), {
            'state': 'initializing',
            'drives': {},
            'self_model': '',
            'connected_clients': 0
        })()
    
    async def connect(self, websocket):
        """Подключает нового клиента."""
        self.active_connections.append(websocket)
        self.state.connected_clients = len(self.active_connections)
        logger.info(f"WebEnvironment: Клиент подключен. Всего: {self.state.connected_clients}")
        
        # Отправляем текущее состояние
        drives = {d.type.value: d.current for d in self.leya.drives.drives.values()}
        self_model = await self.leya.memory.get_self_model_context()
        
        await self.broadcast({
            "type": "state_update",
            "data": self.state.state
        })
        await self.broadcast({
            "type": "drives_update",
            "data": drives
        })
        await self.broadcast({
            "type": "self_model_update",
            "data": self_model
        })
    
    async def disconnect(self, websocket):
        """Отключает клиента."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.state.connected_clients = len(self.active_connections)
        logger.info(f"WebEnvironment: Клиент отключен. Всего: {self.state.connected_clients}")
    
    async def broadcast(self, message: Dict[str, Any]):
        """Отправка сообщения всем подключенным WebSocket-клиентам."""
        if not hasattr(self, '_clients'):
            # Импортируем глобальный список клиентов из server.py
            from web_interface.server import connected_clients
            self._clients = connected_clients
    
        disconnected = set()
        for client in self._clients:
            try:
                await client.send_json(message)
            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение клиенту: {e}")
                disconnected.add(client)
    
        # Удаляем отключенных клиентов
        for client in disconnected:
            self._clients.discard(client)
    
    async def listen(self) -> Optional[Dict[str, Any]]:
        """Получает следующий стимул из очереди."""
        try:
            return self.input_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    async def send_message(self, message: str):
        """Отправляет сообщение Леи в веб-интерфейс (формат app.js)."""
        await self.broadcast({
            "type": "leya_response",
            "content": message
        })
    
    async def broadcast_thought(self, thought_type: str, thought: str):
        """Транслирует мысль в веб-интерфейс (формат app.js)."""
        await self.broadcast({
            "type": "thought",
            "thought_type": thought_type,
            "content": thought
        })
    
    async def broadcast_state(self, state: str):
        """Транслирует состояние (формат app.js)."""
        self.state.state = state
        await self.broadcast({
            "type": "state_update",
            "data": state
        })
    
    async def update_drives(self, drives: Dict[str, float]):
        """Обновляет значения драйвов (формат app.js)."""
        self.state.drives = drives
        await self.broadcast({
            "type": "drives_update",
            "data": drives
        })
    
    async def update_self_model(self, self_model: str):
        """Обновляет Модель Себя (отправляет только если изменилась)."""
        if self_model != self.state.self_model:
            self.state.self_model = self_model
            await self.broadcast({
                "type": "self_model_update",
                "data": self_model
            })
    
    async def receive_user_message(self, content: str):
        """Получает сообщение от пользователя через WebSocket."""
        await self.input_queue.put({
            "type": "user_message",
            "content": content,
            "source": "web",
            "timestamp": datetime.now().timestamp()
        })
    async def update_state(self, state: str):
        """Обновляет состояние Леи."""
        self.state.state = state
        await self.broadcast({
            "type": "state_update",
            "data": state
        })

    async def handle_user_message(self, content: str):
        """Обработка сообщения от пользователя через веб-интерфейс."""
        try:
            # Передаем сообщение в LeyaOS
            await self.leya.perceive({
                "type": "user_message",
                "content": content,
                "source": "web_interface"
            })
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")
            raise