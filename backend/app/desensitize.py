import ipaddress
import re
from typing import Dict, Any, List
from app.config import SERVER_NAME, HOST_REAL_IP

# Regular expression to identify internal IPv4 addresses (10.x.x.x, 192.168.x.x, 172.16-31.x.x, 127.x.x.x)
INTERNAL_IP_PATTERN = re.compile(
    r'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
    r'192\.168\.\d{1,3}\.\d{1,3}|'
    r'172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|'
    r'127\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
    r'169\.254\.\d{1,3}\.\d{1,3})\b'
)

def is_sensitive_ip(ip: str) -> bool:
    """
    Check whether an IP is the host's internal VPC IP (e.g. 10.x.x.x),
    loopback, or the configured host public IP.
    """
    if not ip:
        return False

    # Check if matches configured host public IP
    if HOST_REAL_IP and ip.strip() == HOST_REAL_IP:
        return True

    try:
        ip_obj = ipaddress.ip_address(ip.strip())
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_reserved
            or ip_obj.is_link_local
        )
    except ValueError:
        # If it's a hostname or malformed, check internal pattern
        return bool(INTERNAL_IP_PATTERN.match(ip))

def sanitize_text(text: str) -> str:
    """Mask any internal IP patterns or host public IP inside free text strings."""
    if not text:
        return ""

    sanitized = text
    if HOST_REAL_IP:
        sanitized = sanitized.replace(HOST_REAL_IP, f"[{SERVER_NAME}]")

    sanitized = INTERNAL_IP_PATTERN.sub(f"[{SERVER_NAME}]", sanitized)
    return sanitized

def desensitize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Desensitize a honeypot event record:
    - If src_ip is host internal/public IP, mask with SERVER_NAME
    - Mask internal IPs in commands or download URLs
    - Remove raw_json if it might leak container environment details
    """
    if not event:
        return {}

    sanitized = dict(event)
    src_ip = str(sanitized.get("src_ip", "")).strip()

    if is_sensitive_ip(src_ip):
        sanitized["src_ip"] = SERVER_NAME
        sanitized["country"] = "Virtual Probe"
        sanitized["country_code"] = "PRB"
        sanitized["city"] = "GCP Node"

    # Sanitize commands if present
    if sanitized.get("command"):
        sanitized["command"] = sanitize_text(sanitized["command"])

    # Sanitize URLs if present
    if sanitized.get("download_url"):
        sanitized["download_url"] = sanitize_text(sanitized["download_url"])

    # Strip raw_json to avoid leaking internal host config
    sanitized.pop("raw_json", None)

    return sanitized

def desensitize_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Desensitize a list of event dictionaries."""
    return [desensitize_event(item) for item in items]
