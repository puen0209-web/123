import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

from app.config import COWRIE_LOG_PATH
from app.database import save_event
from app.geoip import resolve_ip
from app.desensitize import desensitize_event
from app.websocket_manager import ws_manager

logger = logging.getLogger("cowrie_soc.watcher")

class CowrieLogWatcher:
    def __init__(self, default_log_path: str = COWRIE_LOG_PATH):
        self.default_log_path = default_log_path
        self.active_log_path: Optional[str] = None
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.last_inode = None
        self.last_pos = 0

    def start(self):
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._watch_loop())
            logger.info(f"Cowrie log watcher started. Target log path: {self.default_log_path}")

    def stop(self):
        if self.is_running:
            self.is_running = False
            if self._task:
                self._task.cancel()
            logger.info("Cowrie log watcher stopped.")

    def _discover_log_file(self) -> Optional[Path]:
        """
        Check for cowrie.json.log or cowrie.json in the configured log directory.
        Seamlessly handles both naming conventions across Cowrie versions.
        """
        candidates = [
            Path(self.default_log_path),
            Path(self.default_log_path).parent / "cowrie.json.log",
            Path(self.default_log_path).parent / "cowrie.json",
        ]
        for path in candidates:
            if path.exists() and path.is_file():
                return path
        return None

    async def _watch_loop(self):
        """Asynchronous tailing loop with file rotation detection."""
        while self.is_running:
            try:
                target_path = self._discover_log_file()
                if not target_path:
                    # Wait for Cowrie to produce log file
                    await asyncio.sleep(2.0)
                    continue

                self.active_log_path = str(target_path)

                # Check inode to detect rotation
                current_stat = os.stat(self.active_log_path)
                current_inode = current_stat.st_ino

                if self.last_inode != current_inode:
                    logger.info(f"Tracking log file: {self.active_log_path} (inode: {current_inode})")
                    self.last_inode = current_inode
                    self.last_pos = 0

                # Open and process new lines
                with open(self.active_log_path, "r", encoding="utf-8", errors="ignore") as f:
                    # If file size shrank (truncated), reset pos
                    if current_stat.st_size < self.last_pos:
                        self.last_pos = 0

                    f.seek(self.last_pos)
                    lines = f.readlines()
                    self.last_pos = f.tell()

                if lines:
                    for line in lines:
                        line = line.strip()
                        if line:
                            await self._parse_and_handle_line(line)

                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in log watcher loop: {e}", exc_info=True)
                await asyncio.sleep(2.0)

    async def _parse_and_handle_line(self, line: str):
        """Parse raw Cowrie JSON log line and dispatch events."""
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            return

        eventid = raw.get("eventid", "")
        src_ip = raw.get("src_ip")
        if not src_ip:
            return

        timestamp = raw.get("timestamp", "")
        session_id = raw.get("session", "")
        src_port = raw.get("src_port")

        event_type = None
        username = None
        password = None
        command = None
        download_url = None
        download_hash = None

        if eventid == "cowrie.login.failed":
            event_type = "login_failed"
            username = raw.get("username", "")
            password = raw.get("password", "")
        elif eventid == "cowrie.login.success":
            event_type = "login_success"
            username = raw.get("username", "")
            password = raw.get("password", "")
        elif eventid in ("cowrie.command.input", "cowrie.command.failed"):
            event_type = "command"
            command = raw.get("input", "")
        elif eventid == "cowrie.session.file_download":
            event_type = "file_download"
            download_url = raw.get("url", "")
            download_hash = raw.get("shasum") or raw.get("outfile", "")
        elif eventid == "cowrie.session.connect":
            event_type = "connect"
        elif eventid == "cowrie.session.closed":
            event_type = "closed"
        else:
            return

        # Resolve GeoIP coordinates
        geo = await resolve_ip(src_ip)

        raw_record = {
            "timestamp": timestamp,
            "session_id": session_id,
            "event_type": event_type,
            "src_ip": src_ip,
            "src_port": src_port,
            "country": geo.get("country", "Unknown"),
            "country_code": geo.get("country_code", "XX"),
            "city": geo.get("city", "Unknown"),
            "latitude": geo.get("latitude", 0.0),
            "longitude": geo.get("longitude", 0.0),
            "username": username,
            "password": password,
            "command": command,
            "download_url": download_url,
            "download_hash": download_hash,
            "raw_json": line
        }

        # Apply data security & desensitization (protects host public/private IP)
        sanitized_record = desensitize_event(raw_record)

        # Store in SQLite
        row_id = await save_event(sanitized_record)
        sanitized_record["id"] = row_id

        # Real-time WebSocket notification with sanitized payload
        await ws_manager.broadcast({
            "type": "new_event",
            "data": sanitized_record
        })

log_watcher = CowrieLogWatcher()
