#!/usr/bin/env bash
# ==============================================================================
# GCP Debian 12 (Bookworm) One-Click Setup Script
# - Installs Docker Engine & Compose v2
# - Creates 2GB Swap (mitigates OOM on Spot instances)
# - Sets up permissions for Cowrie volumes
# - Schedules daily disk cleanup cron job (for 10GB disk protection)
# ==============================================================================
set -e

if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run this script with sudo or as root."
  exit 1
fi

echo "[*] Step 1: Updating system packages and installing prerequisites..."
apt-get update -y
apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    cron

echo "[*] Step 2: Configuring 2GB Swap (Crucial for n2-standard-2 Spot instances)..."
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    if ! grep -q "/swapfile" /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' > /etc/sysctl.d/99-swap.conf
    echo "[+] 2GB Swap successfully enabled."
else
    echo "[!] /swapfile already exists. Skipping swap creation."
fi

echo "[*] Step 3: Installing Docker Engine & Docker Compose (Debian 12 Bookworm)..."
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
fi

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker
echo "[+] Docker Engine successfully installed and running."

echo "[*] Step 4: Configuring Honeypot volume permissions..."
PROJECT_DIR=$(pwd)
mkdir -p "$PROJECT_DIR/data/cowrie/log" "$PROJECT_DIR/data/cowrie/downloads" "$PROJECT_DIR/data/cowrie/tty" "$PROJECT_DIR/data/db" "$PROJECT_DIR/data/geoip"
chown -R 1000:1000 "$PROJECT_DIR/data/cowrie"
chmod -R 775 "$PROJECT_DIR/data/cowrie"
echo "[+] Permissions configured for Cowrie UID 1000."

echo "[*] Step 5: Scheduling daily automated disk cleanup cron..."
CLEANUP_SCRIPT="$PROJECT_DIR/scripts/cleanup_disk.sh"
chmod +x "$CLEANUP_SCRIPT"
CRON_JOB="0 3 * * * $CLEANUP_SCRIPT >> /var/log/honeypot_cleanup.log 2>&1"
(crontab -l 2>/dev/null | grep -v "cleanup_disk.sh" ; echo "$CRON_JOB") | crontab -
echo "[+] Daily 3:00 AM disk cleanup cron registered."

echo ""
echo "=========================================================================="
echo "  GCP Debian 12 Environment Ready!"
echo "=========================================================================="
echo "To start the honeypot and SOC dashboard, run:"
echo "    docker compose up -d --build"
echo ""
echo "GCP VPC Firewall Configuration Guide:"
echo "1. Allow public traffic to Cowrie Honeypot (Port 2222):"
echo "   gcloud compute firewall-rules create allow-honeypot-ssh \\"
echo "       --allow tcp:2222 --source-ranges 0.0.0.0/0 --target-tags honeypot-node"
echo ""
echo "2. Allow admin access to SOC Dashboard (Port 8080):"
echo "   gcloud compute firewall-rules create allow-soc-dashboard \\"
echo "       --allow tcp:8080 --source-ranges YOUR_PUBLIC_IP/32 --target-tags honeypot-node"
echo "=========================================================================="
