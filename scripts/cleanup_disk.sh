#!/usr/bin/env bash
# ==============================================================================
# 10GB Limited Disk Automated Cleanup Script
# Prunes stale malware samples, TTY recordings, rotated logs & unused Docker layers
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Starting Honeypot Disk Maintenance ==="

# 1. Clean downloaded malware binaries older than 3 days
if [ -d "$BASE_DIR/data/cowrie/downloads" ]; then
    DELETED_DLS=$(find "$BASE_DIR/data/cowrie/downloads" -type f -mtime +3 -print -delete | wc -l)
    echo "[+] Cleaned $DELETED_DLS malware sample(s) older than 3 days."
fi

# 2. Clean TTY recordings older than 7 days
if [ -d "$BASE_DIR/data/cowrie/tty" ]; then
    DELETED_TTY=$(find "$BASE_DIR/data/cowrie/tty" -type f -mtime +7 -print -delete | wc -l)
    echo "[+] Cleaned $DELETED_TTY TTY session recording(s) older than 7 days."
fi

# 3. Clean rotated Cowrie logs older than 7 days
if [ -d "$BASE_DIR/data/cowrie/log" ]; then
    DELETED_LOGS=$(find "$BASE_DIR/data/cowrie/log" -type f \( -name "*.json.*" -o -name "*.log.*" \) -mtime +7 -print -delete | wc -l)
    echo "[+] Cleaned $DELETED_LOGS rotated log archive(s) older than 7 days."
fi

# 4. Check Root Disk Capacity
USAGE_PERCENT=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
echo "[*] Current Root Disk Usage: ${USAGE_PERCENT}%"

# 5. If disk usage exceeds 80%, prune unused Docker layers
if [ "$USAGE_PERCENT" -ge 80 ]; then
    echo "[!] Disk usage exceeds 80%! Pruning unused Docker containers and images..."
    docker system prune -f --filter "until=72h" || true
fi

# Report final disk status
df -h /
echo "=== Disk Maintenance Completed Successfully ==="
