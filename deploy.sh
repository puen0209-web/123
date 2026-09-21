#!/usr/bin/env bash
# ==============================================================================
# SSH Honeypot & SOC Dashboard - GCP Debian 12 真正的一键部署脚本
# 运行方式: sudo bash deploy.sh
# ==============================================================================
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
cat << "EOF"
  ____ ____  _   _   _   _                          _   
 / ___/ ___|| | | | | | | | ___  _ __   ___ _   _ _| |_ 
 \___ \___ \| |_| | | |_| |/ _ \| '_ \ / _ \ | | |_   _|
  ___) |__) |  _  | |  _  | (_) | | | |  __/ |_| | | |_ 
 |____/____/|_| |_| |_| |_|\___/|_| |_|\___|\__, |  \__|
                                            |___/       
        GCP Debian 12 极简轻量级一键部署工具
EOF
echo -e "${NC}"

# 1. 权限检查
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR] 请以 root 或使用 sudo 权限运行此脚本：sudo bash deploy.sh${NC}"
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo -e "${YELLOW}[1/6] 正在探测宿主机公网 IP 与 GCP 元数据...${NC}"
# 优先从 GCP 内部元数据服务器获取公网 IP，其次使用外网 API
PUBLIC_IP=$(curl -s -m 2 -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip" 2>/dev/null || true)
if [ -z "$PUBLIC_IP" ]; then
    PUBLIC_IP=$(curl -s -m 3 https://api.ipify.org 2>/dev/null || curl -s -m 3 https://ifconfig.me 2>/dev/null || echo "127.0.0.1")
fi
echo -e "${GREEN}[+] 探测到公网 IP: ${BOLD}${PUBLIC_IP}${NC}"

echo -e "${YELLOW}[2/6] 正在检查并配置系统基础依赖与 2GB Swap 分区 (防 Spot 实例 OOM)...${NC}"
apt-get update -y >/dev/null 2>&1
apt-get install -y --no-install-recommends ca-certificates curl gnupg lsb-release cron >/dev/null 2>&1

# 配置 2GB Swap
if [ ! -f /swapfile ]; then
    echo -e "${CYAN}[*] 正在创建 2GB Swapfile...${NC}"
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048 >/dev/null 2>&1
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null 2>&1
    swapon /swapfile >/dev/null 2>&1
    if ! grep -q "/swapfile" /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    sysctl vm.swappiness=10 >/dev/null 2>&1
    echo 'vm.swappiness=10' > /etc/sysctl.d/99-swap.conf
    echo -e "${GREEN}[+] 2GB Swap 分区已生效。${NC}"
else
    echo -e "${GREEN}[+] 2GB Swap 分区已存在，跳过。${NC}"
fi

echo -e "${YELLOW}[3/6] 正在检查 Docker 环境...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${CYAN}[*] 正在安装 Docker CE 与 Docker Compose Plugin (Debian 12 Bookworm)...${NC}"
    install -m 0755 -d /etc/apt/keyrings
    if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
        curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg
    fi
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y >/dev/null 2>&1
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null 2>&1
    systemctl enable docker >/dev/null 2>&1
    systemctl start docker >/dev/null 2>&1
    echo -e "${GREEN}[+] Docker CE 安装就绪。${NC}"
else
    echo -e "${GREEN}[+] Docker 环境已存在。${NC}"
fi

echo -e "${YELLOW}[4/6] 正在初始化数据卷权限与 10GB 磁盘保护定时任务...${NC}"
mkdir -p data/cowrie/log data/cowrie/downloads data/cowrie/tty data/db data/geoip
chown -R 1000:1000 data/cowrie
chmod -R 775 data/cowrie

# 自动生成 .env 配置文件
if [ ! -f .env ]; then
    cp .env.example .env
fi
# 将探测到的真实公网 IP 填入 .env 用于后端精准脱敏
sed -i "s/^HOST_REAL_IP=.*/HOST_REAL_IP=${PUBLIC_IP}/" .env

# 注册每日凌晨 3:00 自动清理任务
chmod +x scripts/cleanup_disk.sh
(crontab -l 2>/dev/null | grep -v "cleanup_disk.sh" ; echo "0 3 * * * $PROJECT_DIR/scripts/cleanup_disk.sh >> /var/log/honeypot_cleanup.log 2>&1") | crontab -
echo -e "${GREEN}[+] 权限与 10GB 磁盘每日自动维护 Cron 已配置。${NC}"

echo -e "${YELLOW}[5/6] 正在一键构建并启动容器服务 (Cowrie + FastAPI + Web SOC)...${NC}"
docker compose down >/dev/null 2>&1 || true
docker compose up -d --build

echo -e "${YELLOW}[6/6] 正在等待服务健康检查就绪...${NC}"
MAX_WAIT=20
WAIT_COUNT=0
HEALTHY=false

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if curl -s -f http://127.0.0.1:8080/api/health >/dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

echo ""
echo -e "${GREEN}========================================================================${NC}"
if [ "$HEALTHY" = true ]; then
    echo -e "${GREEN}${BOLD}🎉 一键部署成功！所有服务已在后台健康运行！${NC}"
else
    echo -e "${YELLOW}${BOLD}⚠️ 服务已拉起，正在初始化日志与数据流...${NC}"
fi
echo -e "${GREEN}========================================================================${NC}"
echo ""
echo -e " 🖥️  ${BOLD}态势感知可视化大屏访问地址：${NC}"
echo -e "    ${CYAN}${BOLD}http://${PUBLIC_IP}:8080${NC}"
echo ""
echo -e " 🍯 ${BOLD}SSH 蜜罐诱捕监听端口：${NC}"
echo -e "    ${YELLOW}${BOLD}Port 2222${NC} (测试命令: ${BOLD}ssh root@${PUBLIC_IP} -p 2222${NC})"
echo ""
echo -e " 🛡️ ${BOLD}主机原生 SSH 端口：${NC}"
echo -e "    ${GREEN}${BOLD}Port 22${NC} (保留供日常安全运维管理，完全隔离)"
echo ""
echo -e " 📌 ${BOLD}GCP 云防火墙规则提醒：${NC}"
echo -e "    请确保在 GCP 控制台已放行 ${BOLD}TCP 2222${NC} (全公网) 与 ${BOLD}TCP 8080${NC} (您的管理IP)。"
echo -e "    快捷命令行配置："
echo -e "    gcloud compute firewall-rules create allow-honeypot-ssh --allow tcp:2222 --source-ranges 0.0.0.0/0"
echo -e "    gcloud compute firewall-rules create allow-soc-dashboard --allow tcp:8080 --source-ranges <你的IP>/32"
echo ""
echo -e "${GREEN}========================================================================${NC}"
