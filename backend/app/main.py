import logging
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import (
    SERVER_NAME, SERVER_LAT, SERVER_LON, SERVER_CITY, SERVER_COUNTRY,
    DEMO_MODE, MAX_RECENT_EVENTS
)
from app.database import (
    init_db, get_summary_stats, get_top_ips, get_top_usernames,
    get_top_passwords, get_top_commands, get_recent_events,
    get_recent_payloads, get_geo_stats
)
from app.desensitize import desensitize_list, is_sensitive_ip
from app.websocket_manager import ws_manager
from app.log_watcher import log_watcher
from app.cleaner import db_cleaner
from app.mock_generator import mock_generator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cowrie_soc")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Cowrie SOC Dashboard Backend...")
    await init_db()
    log_watcher.start()
    db_cleaner.start()

    if DEMO_MODE:
        logger.info("DEMO_MODE is enabled. Starting attack simulator...")
        mock_generator.start()

    yield

    # Shutdown
    logger.info("Shutting down Cowrie SOC Backend...")
    log_watcher.stop()
    db_cleaner.stop()
    mock_generator.stop()

app = FastAPI(
    title="Cowrie SSH Honeypot SOC Dashboard API",
    version="1.1.0",
    lifespan=lifespan
)

# Enable CORS for external dashboard consumption if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REST Endpoints ---

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "cowrie-soc-api"
    }

@app.get("/api/config")
async def get_node_config():
    """Return honeypot node metadata and map anchor coordinates (desensitized)."""
    return {
        "server_name": SERVER_NAME,
        "server_lat": SERVER_LAT,
        "server_lon": SERVER_LON,
        "server_city": SERVER_CITY,
        "server_country": SERVER_COUNTRY,
        "demo_mode": mock_generator.is_running
    }

@app.get("/api/stats/summary")
async def get_stats_summary():
    """Overall security posture summary."""
    return await get_summary_stats()

@app.get("/api/stats/top")
async def get_stats_top(limit: int = Query(10, ge=1, le=50)):
    """Top 10 attackers, usernames, passwords, commands (desensitized)."""
    raw_top_ips = await get_top_ips(limit)
    # Ensure sensitive internal/host IPs in top_ips list are masked
    sanitized_top_ips = []
    for item in raw_top_ips:
        ip = item.get("src_ip", "")
        if is_sensitive_ip(ip):
            item["src_ip"] = SERVER_NAME
            item["country"] = "Virtual Probe"
        sanitized_top_ips.append(item)

    top_users = await get_top_usernames(limit)
    top_passes = await get_top_passwords(limit)
    top_cmds = await get_top_commands(limit)
    return {
        "top_ips": sanitized_top_ips,
        "top_usernames": top_users,
        "top_passwords": top_passes,
        "top_commands": top_cmds
    }

@app.get("/api/stats/geo")
async def get_geo_data(limit: int = Query(150, ge=10, le=500)):
    """Threat map coordinates and attack volumes."""
    points = await get_geo_stats(limit)
    return {
        "server": {
            "name": SERVER_NAME,
            "lat": SERVER_LAT,
            "lon": SERVER_LON,
            "city": SERVER_CITY,
            "country": SERVER_COUNTRY
        },
        "points": points
    }

@app.get("/api/events/recent")
async def get_recent_event_list(limit: int = Query(50, ge=1, le=200)):
    """Recent event log for waterfall feed (strictly desensitized)."""
    events = await get_recent_events(limit)
    return desensitize_list(events)

@app.get("/api/payloads")
async def get_payload_list(limit: int = Query(50, ge=1, le=200)):
    """Audit logs for executed shell commands and file downloads (strictly desensitized)."""
    payloads = await get_recent_payloads(limit)
    return desensitize_list(payloads)

@app.post("/api/demo/toggle")
async def toggle_demo_mode():
    """Dynamically toggle synthetic attack generation from UI."""
    if mock_generator.is_running:
        mock_generator.stop()
        status = False
    else:
        mock_generator.start()
        status = True
    return {"demo_mode": status}

@app.post("/api/demo/fire")
async def fire_single_mock_attack():
    """Trigger a single simulated attack event immediately."""
    await mock_generator.generate_single_attack()
    return {"status": "attack_fired"}

# --- WebSocket Endpoint ---

@app.websocket("/ws/live")
async def websocket_live_stream(websocket: WebSocket):
    """Full-duplex real-time streaming channel for attack events."""
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket client error: {e}")
        await ws_manager.disconnect(websocket)

# --- Mount Static Frontend ---
frontend_dir = Path("/app/frontend")
if not frontend_dir.exists():
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info(f"Mounted static frontend from {frontend_dir}")
else:
    logger.warning(f"Frontend directory not found at {frontend_dir}")
