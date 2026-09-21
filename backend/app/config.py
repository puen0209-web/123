import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Cowrie Log Path (supports cowrie.json.log or cowrie.json)
COWRIE_LOG_PATH = os.getenv("COWRIE_LOG_PATH", "/app/cowrie_logs/cowrie.json.log")

# SQLite Database Path
DB_PATH = os.getenv("DB_PATH", "/app/data/honeypot.db")

# GeoIP Database Path (Local MMDB optional)
GEOIP_DB_PATH = os.getenv("GEOIP_DB_PATH", "/app/geoip/GeoLite2-City.mmdb")

# Virtual Probe Name & Honeypot Coordinates (Target on Cyber Threat Map)
SERVER_NAME = os.getenv("SERVER_NAME", "Honeypot-Node-01")
SERVER_LAT = float(os.getenv("SERVER_LAT", "1.3521"))      # Default: Singapore
SERVER_LON = float(os.getenv("SERVER_LON", "103.8198"))
SERVER_CITY = os.getenv("SERVER_CITY", "Singapore")
SERVER_COUNTRY = os.getenv("SERVER_COUNTRY", "SG")

# Data Security & Desensitization
HOST_REAL_IP = os.getenv("HOST_REAL_IP", "").strip()

# Disk & Database Retention (Days to keep in 10GB limited disk)
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "7"))

# Demo / Simulation Mode
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")

# Limits
MAX_RECENT_EVENTS = int(os.getenv("MAX_RECENT_EVENTS", "100"))
MAX_HISTORY_LOAD = int(os.getenv("MAX_HISTORY_LOAD", "10000"))
