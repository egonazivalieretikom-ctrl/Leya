"""
WebEnvironment — веб-интерфейс для Леи через FastAPI + WebSocket.
Альтернатива CLIEnvironment.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from fastapi import WebSocket

from leya_core.environment import Environment

logger = logging.getLogger("WebEnvironment")

class WebEnvironment(Environment):
    """
    Веб-интерфейс для Леи.
    Принимает сообщения через WebSocket, отправляет обновления в реальном времени.
    """

    def __init__(self, leya_os):
        super().__init__(leya_os)
        self.message_queue = asyncio.Queue()
        self.input_queue = self.message_queue
        self.connected_clients: Set[WebSocket] = set()
        self.message_history: List[Dict] = []
        self.max_history = 100

    async def connect(self, websocket: WebSocket):
        """Подключение нового клиента"""
        await websocket.accept()
        self.connected_clients.add(websocket)
        logger.info(f"WebEnvironment: Клиент подключен. Всего: {len(self.connected_clients)}")

        # Отправляем историю сообщений новому клиенту
        for msg in self.message_history[-20:]:
            await websocket.send_json(msg)

    def disconnect(self, websocket: WebSocket):
        """Отключение клиента"""
        self.connected_clients.discard(websocket)
        logger.info(f"WebEnvironment: Клиент отключен. Всего: {len(self.connected_clients)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Отправка сообщения всем подключенным клиентам"""
        # Сохраняем в историю
        message["timestamp"] = datetime.now().timestamp()
        self.message_history.append(message)
        if len(self.message_history) > self.max_history:
            self.message_history.pop(0)

        # Отправляем всем клиентам
        disconnected = set()
        for client in self.connected_clients:
            try:
                await client.send_json(message)
            except Exception as e:
                logger.warning(f"WebEnvironment: Ошибка отправки клиенту: {e}")
                disconnected.add(client)

        # Удаляем отключившихся
        for client in disconnected:
            self.connected_clients.discard(client)

    async def listen(self) -> Optional[Dict[str, Any]]:
        """Получает следующее сообщение из очереди"""
        try:
            return self.message_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def send_message(self, message: str):
        """Отправляет сообщение всем клиентам"""
        await self.broadcast({
            "type": "leya_response",
            "content": message
        })

    async def handle_user_message(self, content: str):
        """Обрабатывает входящее сообщение от пользователя"""
        await self.message_queue.put({
            "type": "user_message",
            "content": content,
            "source": "web",
            "timestamp": datetime.now().timestamp()
        })

        # Логируем в историю
        await self.broadcast({
            "type": "user_message",
            "content": content
        })

    async def update_drives(self, drive_state: Dict[str, float]):
        """Отправляет обновления драйвов клиентам"""
        await self.broadcast({
            "type": "drives_update",
            "data": drive_state
        })

    async def update_memory(self, memory_info: Dict):
        """Отправляет обновления памяти"""
        await self.broadcast({
            "type": "memory_update",
            "data": memory_info
        })

    async def update_self_model(self, self_model: str):
        """Отправляет обновления Модели Себя"""
        await self.broadcast({
            "type": "self_model_update",
            "data": self_model
        })

    async def broadcast_thought(self, thought_type: str, content: str):
        """Отправляет мысли Леи (внутренний монолог, спонтанные мысли)"""
        await self.broadcast({
            "type": "thought",
            "thought_type": thought_type,  # "internal", "spontaneous", "reflection"
            "content": content
        })

    async def broadcast_state(self, state: str):
        """Отправляет состояние Леи (awake, sleeping, reflecting)"""
        await self.broadcast({
            "type": "state_update",
            "data": state
        })

    async def update_state(self, state: str):
        """Обновляет состояние Леи (awake, sleeping, reflecting)"""
        await self.broadcast_state(state)

    async def broadcast_soul_update(self, soul_files: Dict[str, str]):
        """Отправляет содержимое души"""
        await self.broadcast({
            "type": "soul_update",
            "data": soul_files
        })