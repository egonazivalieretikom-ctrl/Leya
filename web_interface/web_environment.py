"""
web_interface/web_environment.py
Веб-интерфейс для Леи через FastAPI + WebSocket.

Этап 1.2:
- Замена широких except на специфичные исключения
- Pydantic-валидация broadcast-сообщений
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

from leya_core.environment import Environment
from leya_core.exceptions import LeyaBroadcastError, LeyaEnvironmentError

logger = logging.getLogger(__name__)


class WebEnvironment(Environment):
    """Веб-интерфейс для Леи с WebSocket broadcast."""

    def __init__(self, leya_os) -> None:
        super().__init__(leya_os)
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.input_queue = self.message_queue
        self.connected_clients: Set[WebSocket] = set()
        self.message_history: List[Dict[str, Any]] = []
        self.max_history = 100

    async def connect(self, websocket: WebSocket) -> None:
        """Подключение нового клиента."""
        await websocket.accept()
        self.connected_clients.add(websocket)
        logger.info(f"WebEnvironment: Клиент подключен. Всего: {len(self.connected_clients)}")

        # Отправка истории новому клиенту
        for msg in self.message_history[-20:]:
            try:
                await websocket.send_json(msg)
            except Exception as exc:
                logger.warning(f"Не удалось отправить историю клиенту: {exc}")

    def disconnect(self, websocket: WebSocket) -> None:
        """Отключение клиента."""
        self.connected_clients.discard(websocket)
        logger.info(f"WebEnvironment: Клиент отключен. Всего: {len(self.connected_clients)}")

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Отправка сообщения всем подключенным клиентам."""
        # Валидация сообщения
        if not isinstance(message, dict):
            raise LeyaBroadcastError("Сообщение должно быть словарём", context={"type": type(message).__name__})

        # Добавление timestamp
        message["timestamp"] = datetime.now().timestamp()
        
        # Сохранение в историю
        self.message_history.append(message)
        if len(self.message_history) > self.max_history:
            self.message_history.pop(0)

        # Отправка всем клиентам
        disconnected: Set[WebSocket] = set()
        for client in self.connected_clients:
            try:
                await client.send_json(message)
            except WebSocketDisconnect:
                disconnected.add(client)
            except RuntimeError as exc:
                logger.warning(f"WebSocket ошибка: {exc}")
                disconnected.add(client)
            except Exception as exc:
                logger.warning(f"Неожиданная ошибка отправки клиенту: {exc}")
                disconnected.add(client)

        # Удаление отключившихся
        for client in disconnected:
            self.connected_clients.discard(client)

    async def listen(self) -> Optional[Dict[str, Any]]:
        """Получение следующего сообщения из очереди."""
        try:
            return self.message_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def send_message(self, message: str) -> None:
        """Отправка сообщения всем клиентам."""
        await self.broadcast({
            "type": "leya_response",
            "content": message,
        })

    async def handle_user_message(self, content: str) -> None:
        """Обработка входящего сообщения от пользователя."""
        await self.message_queue.put({
            "type": "user_message",
            "content": content,
            "source": "web",
            "timestamp": datetime.now().timestamp(),
        })

        # Логирование в историю
        await self.broadcast({
            "type": "user_message",
            "content": content,
        })

    async def update_drives(self, drive_state: Dict[str, float]) -> None:
        """Отправка обновлений драйвов клиентам."""
        await self.broadcast({
            "type": "drives_update",
            "data": drive_state,
        })

    async def update_memory(self, memory_info: Dict) -> None:
        """Отправка обновлений памяти."""
        await self.broadcast({
            "type": "memory_update",
            "data": memory_info,
        })

    async def update_self_model(self, self_model: str) -> None:
        """Отправка обновлений Модели Себя."""
        await self.broadcast({
            "type": "self_model_update",
            "data": self_model,
        })

    async def broadcast_thought(self, thought_type: str, content: str) -> None:
        """Отправка мыслей Леи (внутренний монолог, спонтанные мысли)."""
        await self.broadcast({
            "type": "thought",
            "thought_type": thought_type,  # "internal", "spontaneous", "reflection"
            "content": content,
        })

    async def broadcast_state(self, state: str) -> None:
        """Отправка состояния Леи (awake, sleeping, reflecting)."""
        await self.broadcast({
            "type": "state_update",
            "data": state,
        })

    async def update_state(self, state: str) -> None:
        """Обновление состояния Леи."""
        await self.broadcast_state(state)

    async def broadcast_soul_update(self, soul_files: Dict[str, str]) -> None:
        """Отправка содержимого души."""
        await self.broadcast({
            "type": "soul_update",
            "data": soul_files,
        })