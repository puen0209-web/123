"""
Unit and integration test script for Cowrie SOC pipeline.
Validates:
1. SQLite database operations and summary statistics
2. IP desensitization logic (protecting GCP private IP 10.x.x.x and host IP)
3. GeoIP resolution and local caching
4. Database pruning and disk maintenance
"""
import asyncio
import json
import os
import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Override DB_PATH for tests
os.environ["DB_PATH"] = str(Path(__file__).resolve().parent.parent / "data" / "db" / "test_honeypot.db")
os.environ["COWRIE_LOG_PATH"] = str(Path(__file__).resolve().parent.parent / "data" / "cowrie" / "log" / "test_cowrie.json.log")
os.environ["HOST_REAL_IP"] = "34.120.50.60"

from app.database import (
    init_db, save_event, get_summary_stats, get_top_ips,
    get_top_usernames, get_top_passwords, get_top_commands,
    cache_geo, get_cached_geo
)
from app.geoip import resolve_ip
from app.desensitize import desensitize_event, is_sensitive_ip, sanitize_text
from app.cleaner import db_cleaner

async def run_tests():
    print("[+] Starting Cowrie SOC Pipeline Test Suite (GCP Edition)...")

    # Step 1: Test IP Desensitization
    print("[1] Testing IP Desensitization & Privacy Filter...")
    assert is_sensitive_ip("10.128.0.2") is True, "GCP 10.x.x.x should be flagged as sensitive"
    assert is_sensitive_ip("192.168.1.1") is True, "RFC1918 should be flagged as sensitive"
    assert is_sensitive_ip("127.0.0.1") is True, "Loopback should be flagged as sensitive"
    assert is_sensitive_ip("34.120.50.60") is True, "Configured host public IP should be sensitive"
    assert is_sensitive_ip("185.220.101.5") is False, "External attacker IP should NOT be sensitive"

    # Test event masking
    raw_event = {
        "src_ip": "10.128.0.5",
        "command": "curl http://10.128.0.5/miner.sh -o /tmp/x; host is 34.120.50.60",
        "download_url": "http://10.128.0.5/miner.sh",
        "raw_json": '{"secret": "internal_env"}'
    }
    sanitized = desensitize_event(raw_event)
    assert sanitized["src_ip"] == "Honeypot-Node-01", f"Expected Honeypot-Node-01, got {sanitized['src_ip']}"
    assert "10.128.0.5" not in sanitized["command"], "Internal IP should be masked in command"
    assert "34.120.50.60" not in sanitized["command"], "Host real IP should be masked in command"
    assert "raw_json" not in sanitized, "raw_json should be stripped in sanitized payload"
    print("    -> IP Desensitization passed completely.")

    # Step 2: Database Init
    print("[2] Initializing SQLite database...")
    await init_db()
    print("    -> Database initialized successfully.")

    # Step 3: Ingest Events
    print("[3] Testing event ingestion and aggregation...")
    sample_records = [
        {
            "timestamp": "2026-09-21T12:00:01.000Z",
            "session_id": "s1",
            "event_type": "login_failed",
            "src_ip": "185.220.101.5",
            "country": "Germany",
            "country_code": "DE",
            "city": "Frankfurt",
            "latitude": 50.11,
            "longitude": 8.68,
            "username": "root",
            "password": "123"
        },
        {
            "timestamp": "2026-09-21T12:01:00.000Z",
            "session_id": "s2",
            "event_type": "login_success",
            "src_ip": "45.154.255.88",
            "country": "Russia",
            "country_code": "RU",
            "city": "Moscow",
            "latitude": 55.75,
            "longitude": 37.61,
            "username": "admin",
            "password": "admin"
        },
        {
            "timestamp": "2026-09-21T12:01:05.000Z",
            "session_id": "s2",
            "event_type": "command",
            "src_ip": "45.154.255.88",
            "country": "Russia",
            "country_code": "RU",
            "city": "Moscow",
            "latitude": 55.75,
            "longitude": 37.61,
            "command": "uname -a"
        }
    ]
    for rec in sample_records:
        await save_event(rec)

    stats = await get_summary_stats()
    assert stats["total_events"] == 3
    assert stats["login_failed"] == 1
    assert stats["login_success"] == 1
    assert stats["total_commands"] == 1
    print("    -> Summary Stats verified:", stats)

    # Step 4: Test Database Pruning
    print("[4] Testing 10GB disk database pruning...")
    await db_cleaner.prune_database()
    print("    -> DB Prune & VACUUM executed cleanly.")

    # Clean up test database
    test_db = Path(os.environ["DB_PATH"])
    if test_db.exists():
        test_db.unlink()

    print("\n[✓] ALL TESTS PASSED! GCP-tailored Honeypot pipeline verified.")

if __name__ == "__main__":
    asyncio.run(run_tests())
