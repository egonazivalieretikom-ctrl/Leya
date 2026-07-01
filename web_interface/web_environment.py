"""
WebEnvironment — веб-интерфейс для Леи через FastAPI + WebSocket.
Альтернатива CLIEnvironment.

Шаг 1+2: Унифицированный WebSocket (единственный источник connected_clients),
heartbeat для обнаружения мёртвых соединений, явная обработка LeyaBroadcastError.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from leya_core.environment import Environment
from leya_core.exceptions import LeyaBroadcastError

logger = logging.getLogger("WebEnvironment")

# =========================================================================
# Pydantic модели для валидации broadcast сообщений (Шаг 4)
# =========================================================================


class BaseBroadcastMessage(BaseModel):
    """Базовая модель broadcast сообщения."""

    type: str
    timestamp: float | None = None


class ThoughtMessage(BaseBroadcastMessage):
    """Модель сообщения мысли."""

    type: Literal["thought"]
    thought_type: str  # "internal", "spontaneous", "reflection", "workspace"
    content: str


class DrivesUpdateMessage(BaseBroadcastMessage):
    """Модель обновления драйвов."""

    type: Literal["drives_update"]
    data: dict[str, float]


class SelfModelUpdateMessage(BaseBroadcastMessage):
    """Модель обновления само-модели."""

    type: Literal["self_model_update"]
    data: str


class MemoryUpdateMessage(BaseBroadcastMessage):
    """Модель обновления памяти."""

    type: Literal["memory_update"]
    data: dict[str, Any]


class StateUpdateMessage(BaseBroadcastMessage):
    """Модель обновления состояния."""

    type: Literal["state_update"]
    data: str


class SoulUpdateMessage(BaseBroadcastMessage):
    """Модель обновления души."""

    type: Literal["soul_update"]
    data: dict[str, str]


class LeyaResponseMessage(BaseBroadcastMessage):
    """Модель ответа Леи."""

    type: Literal["leya_response"]
    content: str


class UserMessageBroadcast(BaseBroadcastMessage):
    """Модель сообщения пользователя (broadcast)."""

    type: Literal["user_message"]
    content: str


class WebEnvironment(Environment):
    """
    Веб-интерфейс для Леи.
    Принимает сообщения через WebSocket, отправляет обновления в реальном времени.
    Единственный источник connected_clients (ConnectionManager удалён из server.py).
    """

    HEARTBEAT_INTERVAL = 30  # секунд

    def __init__(self, leya_os):
        super().__init__(leya_os)
        self.message_queue = asyncio.Queue()
        self.input_queue = self.message_queue
        self.connected_clients: set[WebSocket] = set()
        self._broadcast_lock = asyncio.Lock()
        self.message_history: list[dict] = []
        self.max_history = 100
        self._heartbeat_tasks: dict[WebSocket, asyncio.Task] = {}

        # ✅ ИСПРАВЛЕНО: проброс soul_manager из LeyaOS через публичный атрибут.
        # WebEnvironment не создаёт SoulCryptoManager сам — это нарушало бы
        # single source of truth. LeyaOS владеет менеджером, web получает ссылку.
        # Это соответствует ISoulManager Protocol (load_all / update_file).
        self.soul_manager = None
        if hasattr(leya_os, "soul_crypto_manager") and leya_os.soul_crypto_manager is not None:
            self.soul_manager = leya_os.soul_crypto_manager
            logger.info(
                "WebEnvironment: soul_manager проброшен из LeyaOS "
                "(тип=%s)",
                type(self.soul_manager).__name__,
            )
        else:
            logger.warning(
                "WebEnvironment: soul_crypto_manager недоступен в LeyaOS, "
                "эндпоинты /api/soul будут возвращать пустой ответ"
            )

    async def connect(self, websocket: WebSocket):
        """Подключение нового клиента. Единственный способ подключения."""
        await websocket.accept()
        self.connected_clients.add(websocket)
        logger.info(f"WebEnvironment: Клиент подключен. Всего: {len(self.connected_clients)}")

        # Отправляем историю сообщений новому клиенту
        for msg in self.message_history[-20:]:
            try:
                await websocket.send_json(msg)
            except Exception:
                break

        # Запускаем heartbeat для этого соединения
        self._heartbeat_tasks[websocket] = asyncio.create_task(self._heartbeat_loop(websocket))

    async def _heartbeat_loop(self, websocket: WebSocket):
        """Отправляет ping каждые HEARTBEAT_INTERVAL секунд для поддержания соединения."""
        try:
            while True:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                try:
                    await websocket.send_json(
                        {"type": "ping", "timestamp": datetime.now().timestamp()}
                    )
                except (WebSocketDisconnect, RuntimeError, Exception):
                    # Соединение мертво — выходим, disconnect обработается в websocket_endpoint
                    break
        except asyncio.CancelledError:
            pass

    def disconnect(self, websocket: WebSocket):
        """Отключение клиента. Единственный способ отключения."""
        self.connected_clients.discard(websocket)
        # Отменяем heartbeat задачу
        task = self._heartbeat_tasks.pop(websocket, None)
        if task and not task.done():
            task.cancel()
        logger.info(f"WebEnvironment: Клиент отключен. Всего: {len(self.connected_clients)}")

    async def broadcast(self, message: dict[str, Any]):
        """
        Отправка сообщения всем подключенным клиентам.

        ИСПРАВЛЕНИЕ ШАГ 4: Валидирует структуру сообщения через Pydantic модели.
        Явно обрабатывает LeyaBroadcastError и очищает отключившихся.
        """
        # Валидация структуры сообщения
        msg_type = message.get("type")
        if not msg_type:
            logger.error(f"WebEnvironment: Сообщение без type: {message}")
            raise LeyaBroadcastError("Сообщение broadcast должно содержать 'type'")

        # Попытка валидации через Pydantic модель
        try:
            model_map = {
                "thought": ThoughtMessage,
                "drives_update": DrivesUpdateMessage,
                "self_model_update": SelfModelUpdateMessage,
                "memory_update": MemoryUpdateMessage,
                "state_update": StateUpdateMessage,
                "soul_update": SoulUpdateMessage,
                "leya_response": LeyaResponseMessage,
                "user_message": UserMessageBroadcast,
            }

            if msg_type in model_map:
                # Валидируем через Pydantic
                validated = model_map[msg_type](**message)
                # Конвертируем обратно в dict для JSON serialization
                message = validated.model_dump(exclude_none=True)
            else:
                logger.warning(f"WebEnvironment: Неизвестный тип сообщения: {msg_type}")
        except ValidationError as exc:
            logger.error(f"WebEnvironment: Ошибка валидации сообщения типа {msg_type}: {exc}")
            raise LeyaBroadcastError(
                f"Невалидная структура сообщения типа {msg_type}",
                context={"validation_error": str(exc)},
            ) from exc

        # Сохраняем в историю
        message["timestamp"] = datetime.now().timestamp()
        self.message_history.append(message)
        if len(self.message_history) > self.max_history:
            self.message_history.pop(0)

        # Отправляем всем клиентам
        disconnected: set[WebSocket] = set()
        for client in list(self.connected_clients):
            try:
                await client.send_json(message)
            except WebSocketDisconnect:
                logger.debug("WebEnvironment: Клиент отключился во время broadcast")
                disconnected.add(client)
            except RuntimeError as e:
                logger.debug(f"WebEnvironment: WebSocket закрыт: {e}")
                disconnected.add(client)
            except Exception as e:
                logger.warning(f"WebEnvironment: Ошибка отправки клиенту: {e}")
                disconnected.add(client)

        # Удаляем отключившихся
        for client in disconnected:
            self.disconnect(client)

    async def listen(self) -> dict[str, Any] | None:
        """Получает следующее сообщение из очереди"""
        try:
            return self.message_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def send_message(self, message: str):
        """Отправляет сообщение всем клиентам"""
        await self.broadcast({"type": "leya_response", "content": message})

    async def handle_user_message(self, content: str):
        """Обрабатывает входящее сообщение от пользователя"""
        await self.message_queue.put(
            {
                "type": "user_message",
                "content": content,
                "source": "web",
                "timestamp": datetime.now().timestamp(),
            }
        )

        # Логируем в историю
        await self.broadcast({"type": "user_message", "content": content})

    async def update_drives(self, drive_state: dict[str, float]):
        """Отправляет обновления драйвов клиентам"""
        await self.broadcast({"type": "drives_update", "data": drive_state})

    async def update_memory(self, memory_info: dict):
        """Отправляет обновления памяти"""
        await self.broadcast({"type": "memory_update", "data": memory_info})

    async def update_self_model(self, self_model: str):
        """Отправляет обновления Модели Себя"""
        await self.broadcast({"type": "self_model_update", "data": self_model})

    async def broadcast_thought(self, thought_type: str, content: str):
        """Отправляет мысли Леи (внутренний монолог, спонтанные мысли)"""
        await self.broadcast(
            {
                "type": "thought",
                "thought_type": thought_type,  # "internal", "spontaneous", "reflection"
                "content": content,
            }
        )

    async def broadcast_state(self, state: str):
        """Отправляет состояние Леи (awake, sleeping, reflecting)"""
        await self.broadcast({"type": "state_update", "data": state})

    async def update_state(self, state: str):
        """Обновляет состояние Леи (awake, sleeping, reflecting)"""
        await self.broadcast_state(state)

    async def broadcast_soul_update(self, soul_files: dict[str, str]):
        """Отправляет содержимое души"""
        await self.broadcast({"type": "soul_update", "data": soul_files})

    async def shutdown(self):
        """Graceful shutdown: закрыть все соединения и отменить heartbeat."""
        for task in self._heartbeat_tasks.values():
            if not task.done():
                task.cancel()
        self._heartbeat_tasks.clear()

        # Закрываем все WebSocket соединения
        for client in list(self.connected_clients):
            try:
                await client.close()
            except Exception:
                pass
        self.connected_clients.clear()
        logger.info("WebEnvironment: Все соединения закрыты")
