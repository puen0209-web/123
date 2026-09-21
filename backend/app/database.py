import os
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import DB_PATH

async def get_db_connection() -> aiosqlite.Connection:
    """Ensure parent directory exists and return an aiosqlite connection."""
    db_file = Path(DB_PATH)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    return conn

async def init_db():
    """Initialize SQLite database tables and indices."""
    async with await get_db_connection() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT,
                event_type TEXT NOT NULL,
                src_ip TEXT NOT NULL,
                src_port INTEGER,
                country TEXT,
                country_code TEXT,
                city TEXT,
                latitude REAL,
                longitude REAL,
                username TEXT,
                password TEXT,
                command TEXT,
                download_url TEXT,
                download_hash TEXT,
                raw_json TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ip_geo_cache (
                ip TEXT PRIMARY KEY,
                country TEXT,
                country_code TEXT,
                city TEXT,
                latitude REAL,
                longitude REAL,
                updated_at TEXT
            )
        """)

        # Performance Indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_ip ON events(src_ip)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_user ON events(username)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_cmd ON events(command)")

        await db.commit()

async def get_cached_geo(ip: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached IP geolocation information."""
    async with await get_db_connection() as db:
        async with db.execute(
            "SELECT country, country_code, city, latitude, longitude FROM ip_geo_cache WHERE ip = ?",
            (ip,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "country": row["country"] or "Unknown",
                    "country_code": row["country_code"] or "XX",
                    "city": row["city"] or "Unknown",
                    "latitude": row["latitude"] or 0.0,
                    "longitude": row["longitude"] or 0.0
                }
    return None

async def cache_geo(ip: str, geo: Dict[str, Any]):
    """Store IP geolocation into cache table."""
    now_iso = datetime.now(timezone.utc).isoformat()
    async with await get_db_connection() as db:
        await db.execute("""
            INSERT OR REPLACE INTO ip_geo_cache (ip, country, country_code, city, latitude, longitude, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            ip,
            geo.get("country", "Unknown"),
            geo.get("country_code", "XX"),
            geo.get("city", "Unknown"),
            geo.get("latitude", 0.0),
            geo.get("longitude", 0.0),
            now_iso
        ))
        await db.commit()

async def save_event(event: Dict[str, Any]) -> int:
    """Save parsed honeypot event to database."""
    async with await get_db_connection() as db:
        cursor = await db.execute("""
            INSERT INTO events (
                timestamp, session_id, event_type, src_ip, src_port,
                country, country_code, city, latitude, longitude,
                username, password, command, download_url, download_hash, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.get("timestamp"),
            event.get("session_id"),
            event.get("event_type"),
            event.get("src_ip"),
            event.get("src_port"),
            event.get("country"),
            event.get("country_code"),
            event.get("city"),
            event.get("latitude"),
            event.get("longitude"),
            event.get("username"),
            event.get("password"),
            event.get("command"),
            event.get("download_url"),
            event.get("download_hash"),
            event.get("raw_json", "")
        ))
        await db.commit()
        return cursor.lastrowid

async def get_summary_stats() -> Dict[str, Any]:
    """Calculate overall security intelligence metrics."""
    async with await get_db_connection() as db:
        # Total attacks / events
        async with db.execute("SELECT COUNT(*) FROM events") as cur:
            total_events = (await cur.fetchone())[0]

        # Distinct attack source IPs
        async with db.execute("SELECT COUNT(DISTINCT src_ip) FROM events") as cur:
            unique_ips = (await cur.fetchone())[0]

        # Failed vs Successful logins
        async with db.execute("SELECT COUNT(*) FROM events WHERE event_type = 'login_failed'") as cur:
            login_failed = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM events WHERE event_type = 'login_success'") as cur:
            login_success = (await cur.fetchone())[0]

        # Commands executed
        async with db.execute("SELECT COUNT(*) FROM events WHERE event_type = 'command'") as cur:
            total_commands = (await cur.fetchone())[0]

        # Malicious downloads
        async with db.execute("SELECT COUNT(*) FROM events WHERE event_type = 'file_download'") as cur:
            total_downloads = (await cur.fetchone())[0]

        # Recent 24-hour attack count
        async with db.execute("""
            SELECT COUNT(*) FROM events 
            WHERE timestamp >= datetime('now', '-1 day')
        """) as cur:
            attacks_24h = (await cur.fetchone())[0]

        return {
            "total_events": total_events,
            "attacks_24h": attacks_24h,
            "unique_ips": unique_ips,
            "login_failed": login_failed,
            "login_success": login_success,
            "total_commands": total_commands,
            "total_downloads": total_downloads,
        }

async def get_top_ips(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve top attacking IPs with country and count."""
    async with await get_db_connection() as db:
        async with db.execute("""
            SELECT src_ip, country, country_code, city, COUNT(*) as hit_count
            FROM events
            WHERE src_ip IS NOT NULL AND src_ip != ''
            GROUP BY src_ip
            ORDER BY hit_count DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def get_top_usernames(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve top attacked usernames."""
    async with await get_db_connection() as db:
        async with db.execute("""
            SELECT username, COUNT(*) as count
            FROM events
            WHERE username IS NOT NULL AND username != ''
            GROUP BY username
            ORDER BY count DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def get_top_passwords(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve top attacked passwords."""
    async with await get_db_connection() as db:
        async with db.execute("""
            SELECT password, COUNT(*) as count
            FROM events
            WHERE password IS NOT NULL AND password != ''
            GROUP BY password
            ORDER BY count DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def get_top_commands(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve top attacker shell commands."""
    async with await get_db_connection() as db:
        async with db.execute("""
            SELECT command, COUNT(*) as count
            FROM events
            WHERE command IS NOT NULL AND command != ''
            GROUP BY command
            ORDER BY count DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def get_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve most recent events for the terminal waterfall."""
    async with await get_db_connection() as db:
        async with db.execute("""
            SELECT id, timestamp, session_id, event_type, src_ip, src_port,
                   country, country_code, city, latitude, longitude,
                   username, password, command, download_url, download_hash
            FROM events
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def get_recent_payloads(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve commands and downloaded files."""
    async with await get_db_connection() as db:
        async with db.execute("""
            SELECT id, timestamp, session_id, event_type, src_ip,
                   country, country_code, city, command, download_url, download_hash
            FROM events
            WHERE event_type IN ('command', 'file_download')
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def get_geo_stats(limit: int = 150) -> List[Dict[str, Any]]:
    """Aggregate attack origin coordinates for ECharts threat map."""
    async with await get_db_connection() as db:
        async with db.execute("""
            SELECT country, country_code, city, latitude, longitude, COUNT(*) as attack_count
            FROM events
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL 
              AND (latitude != 0.0 OR longitude != 0.0)
            GROUP BY latitude, longitude, country, city
            ORDER BY attack_count DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]
