"""
web_interface/web_environment.py — Веб-интерфейс для Леи через FastAPI + WebSocket.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from leya_core.environment import ToolRegistry

from leya_core.environment import Environment

logger = logging.getLogger("WebEnvironment")


class WebEnvironment(Environment):
    """Веб-интерфейс для Леи."""
    
    def __init__(self, leya_os):
        super().__init__(leya_os)
        self.leya_os = leya_os
        self.tool_registry = ToolRegistry()
        self.active_connections: List = []
        self.input_queue = asyncio.Queue()
        self.state = type('State', (), {
            'state': 'initializing',
            'drives': {},
            'self_model': '',
            'connected_clients': 0
        })()
        self._register_tools()
        logger.info("WebEnvironment: Инициализация завершена")
    
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
    
    async def broadcast(self, message: dict):
        """Отправляет сообщение всем подключенным клиентам."""
        from web_interface.server import connected_clients
    
        disconnected = set()
        for client in connected_clients:
            try:
                await client.send_json(message)
            except Exception as e:
                logger.error(f"Ошибка отправки клиенту: {e}")
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
        """Обрабатывает сообщение от пользователя."""
        logger.info(f"Получено сообщение от пользователя: {content[:100]}...")
    
        # Создаем стимул
        stimulus = {
            "type": "user_message",
            "content": content,
            "source": "web_interface",
            "timestamp": datetime.now().timestamp()
        }
    
        # Передаем в основной цикл восприятия
        if self.leya_os:  # ← Проверяем напрямую, без hasattr
            await self.leya_os.perceive(stimulus)
        
            # Запускаем когнитивный цикл
            await self.leya_os._cognitive_loop(stimulus)
        else:
            logger.error("leya_os не инициализирован в WebEnvironment")