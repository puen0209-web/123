#!/usr/bin/env bash
# Script to download free offline GeoIP MMDB into data/geoip/
set -e

DEST_DIR="./data/geoip"
mkdir -p "$DEST_DIR"

CURRENT_YEAR_MONTH=$(date +"%Y-%m")
URL="https://download.db-ip.com/free/dbip-city-lite-${CURRENT_YEAR_MONTH}.mmdb.gz"

echo "[*] Attempting to download DB-IP City Lite for ${CURRENT_YEAR_MONTH}..."
if curl -fsSL "$URL" -o "${DEST_DIR}/dbip-city.mmdb.gz"; then
    echo "[+] Extracting gzip database..."
    gzip -d -f "${DEST_DIR}/dbip-city.mmdb.gz"
    mv -f "${DEST_DIR}/dbip-city.mmdb" "${DEST_DIR}/GeoLite2-City.mmdb"
    echo "[✓] GeoIP database installed successfully at ${DEST_DIR}/GeoLite2-City.mmdb"
else
    echo "[-] Current month archive not yet available. Trying previous month..."
    PREV_YEAR_MONTH=$(date -d "last month" +"%Y-%m" 2>/dev/null || date -v-1m +"%Y-%m")
    FALLBACK_URL="https://download.db-ip.com/free/dbip-city-lite-${PREV_YEAR_MONTH}.mmdb.gz"
    if curl -fsSL "$FALLBACK_URL" -o "${DEST_DIR}/dbip-city.mmdb.gz"; then
        gzip -d -f "${DEST_DIR}/dbip-city.mmdb.gz"
        mv -f "${DEST_DIR}/dbip-city.mmdb" "${DEST_DIR}/GeoLite2-City.mmdb"
        echo "[✓] GeoIP database installed successfully at ${DEST_DIR}/GeoLite2-City.mmdb"
    else
        echo "[!] Auto-download failed. You can manually place GeoLite2-City.mmdb into ${DEST_DIR}/"
    fi
fi
