import asyncio
import json
import logging
from typing import Set
from fastapi import WebSocket

logger = logging.getLogger("cowrie_soc.ws")

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast JSON message to all connected clients."""
        if not self.active_connections:
            return

        payload = json.dumps(message, ensure_ascii=False)
        disconnected = set()

        async with self._lock:
            for connection in list(self.active_connections):
                try:
                    await connection.send_text(payload)
                except Exception as e:
                    logger.debug(f"Failed to send to client: {e}")
                    disconnected.add(connection)

            for dead in disconnected:
                self.active_connections.discard(dead)

ws_manager = ConnectionManager()
