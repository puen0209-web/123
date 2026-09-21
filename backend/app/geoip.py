import ipaddress
import logging
from typing import Dict, Any, Optional
import httpx
from pathlib import Path

from app.config import GEOIP_DB_PATH, SERVER_LAT, SERVER_LON
from app.database import get_cached_geo, cache_geo

logger = logging.getLogger("cowrie_soc.geoip")

# Reader handle for local MMDB if present
_mmdb_reader = None

def get_mmdb_reader():
    global _mmdb_reader
    if _mmdb_reader is not None:
        return _mmdb_reader

    mmdb_path = Path(GEOIP_DB_PATH)
    if mmdb_path.exists():
        try:
            import geoip2.database
            _mmdb_reader = geoip2.database.Reader(str(mmdb_path))
            logger.info(f"Loaded local GeoIP database from {mmdb_path}")
            return _mmdb_reader
        except Exception as e:
            logger.warning(f"Failed to load GeoIP MMDB at {mmdb_path}: {e}")
    return None

def is_private_ip(ip: str) -> bool:
    """Check if the given IP address is private, loopback, or reserved."""
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_multicast
    except ValueError:
        return False

async def resolve_ip(ip: str) -> Dict[str, Any]:
    """
    Resolve IP to geographic coordinates and country info.
    Order:
      1. Private IP check
      2. SQLite Cache check
      3. Local MMDB check (if present)
      4. Lightweight API fallback
      5. Safe defaults
    """
    if not ip or ip == "127.0.0.1":
        return {
            "country": "Localhost",
            "country_code": "LOC",
            "city": "Internal Lab",
            "latitude": SERVER_LAT,
            "longitude": SERVER_LON
        }

    if is_private_ip(ip):
        return {
            "country": "Private Network",
            "country_code": "LAN",
            "city": "Intranet",
            "latitude": SERVER_LAT,
            "longitude": SERVER_LON
        }

    # 1. Check local cache
    cached = await get_cached_geo(ip)
    if cached:
        return cached

    geo_result = None

    # 2. Check local MMDB
    reader = get_mmdb_reader()
    if reader:
        try:
            response = reader.city(ip)
            country = response.country.name or "Unknown"
            country_code = response.country.iso_code or "XX"
            city = response.city.name or country
            lat = response.location.latitude or 0.0
            lon = response.location.longitude or 0.0
            geo_result = {
                "country": country,
                "country_code": country_code,
                "city": city,
                "latitude": round(lat, 4),
                "longitude": round(lon, 4)
            }
        except Exception:
            pass

    # 3. Fallback to free IP lookup API if MMDB did not resolve
    if not geo_result:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(
                    f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,lat,lon"
                )
                if res.status_code == 200:
                    data = res.json()
                    if data.get("status") == "success":
                        geo_result = {
                            "country": data.get("country", "Unknown"),
                            "country_code": data.get("countryCode", "XX"),
                            "city": data.get("city", data.get("country", "Unknown")),
                            "latitude": round(float(data.get("lat", 0.0)), 4),
                            "longitude": round(float(data.get("lon", 0.0)), 4)
                        }
        except Exception as e:
            logger.debug(f"IP-API lookup failed for {ip}: {e}")

    # 4. Default fallback if all fail
    if not geo_result:
        geo_result = {
            "country": "External Attacker",
            "country_code": "XX",
            "city": "Unknown Location",
            "latitude": 0.0,
            "longitude": 0.0
        }

    # Save to SQLite cache so we never query again
    try:
        await cache_geo(ip, geo_result)
    except Exception as e:
        logger.error(f"Error caching geo for {ip}: {e}")

    return geo_result
