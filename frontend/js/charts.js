/**
 * Threat Map and Intelligence Visualizations powered by Apache ECharts
 */

let threatMapChart = null;
let credChart = null;
let serverCoord = [103.8198, 1.3521]; // Default [lon, lat]
let activeLines = [];
let activePoints = [];
const MAX_LINES = 35;

/**
 * Initialize ECharts World Threat Map
 */
async function initThreatMap(containerId, serverInfo, geoPoints = []) {
    const dom = document.getElementById(containerId);
    if (!dom) return;

    threatMapChart = echarts.init(dom, 'dark');

    if (serverInfo && serverInfo.lon && serverInfo.lat) {
        serverCoord = [parseFloat(serverInfo.lon), parseFloat(serverInfo.lat)];
    }

    // Try to load offline world.json, fallback to CDN if needed
    try {
        let worldData;
        try {
            const res = await fetch('js/world.json');
            if (!res.ok) throw new Error("Local map not loaded");
            worldData = await res.json();
        } catch (e) {
            console.warn("Falling back to CDN for world.json");
            const res = await fetch('https://cdn.jsdelivr.net/npm/echarts-map@3.0.1/json/world.json');
            worldData = await res.json();
        }
        echarts.registerMap('world', worldData);
    } catch (err) {
        console.error("Failed to load world GeoJSON:", err);
        return;
    }

    // Prepare initial threat sources and flight lines
    activePoints = [];
    activeLines = [];

    if (Array.isArray(geoPoints)) {
        geoPoints.forEach(pt => {
            if (pt.longitude && pt.latitude && (pt.longitude !== 0 || pt.latitude !== 0)) {
                const coord = [pt.longitude, pt.latitude];
                activePoints.push({
                    name: `${pt.city || pt.country} (${pt.attack_count || 1})`,
                    value: [...coord, pt.attack_count || 1],
                    country: pt.country
                });

                activeLines.push({
                    fromName: pt.country,
                    toName: serverInfo ? serverInfo.name : "Honeypot",
                    coords: [coord, serverCoord]
                });
            }
        });
    }

    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'item',
            backgroundColor: 'rgba(8, 15, 30, 0.92)',
            borderColor: 'rgba(0, 240, 255, 0.4)',
            borderWidth: 1,
            textStyle: {
                color: '#e2e8f0',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: 12
            },
            formatter: function (params) {
                if (params.seriesType === 'lines') {
                    return `<strong>Threat Trajectory</strong><br/>Origin: ${params.data.fromName}<br/>Target: ${params.data.toName}`;
                } else if (params.seriesType === 'effectScatter') {
                    return `<strong>${params.name}</strong>`;
                }
                return params.name;
            }
        },
        geo: {
            map: 'world',
            roam: true,
            zoom: 1.18,
            center: [15, 20],
            silent: false,
            label: {
                show: false
            },
            itemStyle: {
                areaColor: '#0b1326',
                borderColor: '#1e293b',
                borderWidth: 0.8
            },
            emphasis: {
                areaColor: '#132140',
                label: {
                    show: false
                }
            }
        },
        series: [
            // 1. Attack flight lines
            {
                name: 'Attack Lines',
                type: 'lines',
                zlevel: 1,
                effect: {
                    show: true,
                    period: 3.5,
                    trailLength: 0.35,
                    color: '#00f0ff',
                    symbol: 'arrow',
                    symbolSize: 5
                },
                lineStyle: {
                    color: 'rgba(0, 240, 255, 0.3)',
                    width: 1.2,
                    curveness: 0.25
                },
                data: activeLines.slice(-MAX_LINES)
            },
            // 2. Attack origin hotspots
            {
                name: 'Attacker Origins',
                type: 'effectScatter',
                coordinateSystem: 'geo',
                zlevel: 2,
                rippleEffect: {
                    brushType: 'stroke',
                    scale: 3,
                    period: 4
                },
                label: {
                    show: false
                },
                symbolSize: function (val) {
                    const count = val[2] || 1;
                    return Math.min(6 + Math.log2(count + 1) * 2.5, 18);
                },
                itemStyle: {
                    color: '#ff0055',
                    shadowBlur: 10,
                    shadowColor: '#ff0055'
                },
                data: activePoints
            },
            // 3. Honeypot server beacon (Target)
            {
                name: 'Honeypot Node',
                type: 'effectScatter',
                coordinateSystem: 'geo',
                zlevel: 3,
                rippleEffect: {
                    brushType: 'fill',
                    scale: 5,
                    period: 2.5
                },
                label: {
                    show: true,
                    formatter: `{b}`,
                    position: 'bottom',
                    color: '#00ff88',
                    fontFamily: 'JetBrains Mono',
                    fontWeight: 'bold',
                    fontSize: 11
                },
                symbol: 'diamond',
                symbolSize: 14,
                itemStyle: {
                    color: '#00ff88',
                    shadowBlur: 15,
                    shadowColor: '#00ff88'
                },
                data: [{
                    name: `HONEYPOT [${serverInfo?.name || 'NODE-01'}]`,
                    value: [...serverCoord, 9999]
                }]
            }
        ]
    };

    threatMapChart.setOption(option);
    window.addEventListener('resize', () => threatMapChart.resize());
}

/**
 * Dynamically push a new attack line & origin ripple onto the live map
 */
function recordAttackOnMap(attack) {
    if (!threatMapChart) return;
    if (!attack.longitude || !attack.latitude) return;
    if (attack.longitude === 0 && attack.latitude === 0) return;

    const origin = [parseFloat(attack.longitude), parseFloat(attack.latitude)];
    const countryName = attack.country || "Unknown Origin";

    const newLine = {
        fromName: `${countryName} (${attack.src_ip})`,
        toName: "Honeypot SOC",
        coords: [origin, serverCoord]
    };

    const newPoint = {
        name: `[NEW ATTACK] ${attack.src_ip} (${countryName})`,
        value: [...origin, 10],
        country: attack.country
    };

    activeLines.push(newLine);
    if (activeLines.length > MAX_LINES) {
        activeLines.shift();
    }

    // Keep point pool fresh
    activePoints.push(newPoint);
    if (activePoints.length > 50) {
        activePoints.shift();
    }

    threatMapChart.setOption({
        series: [
            {
                name: 'Attack Lines',
                data: activeLines
            },
            {
                name: 'Attacker Origins',
                data: activePoints
            }
        ]
    });
}

/**
 * Initialize Top Credentials (Usernames & Passwords) Bar Chart
 */
function renderCredentialChart(containerId, topUsers = [], topPasses = []) {
    const dom = document.getElementById(containerId);
    if (!dom) return;

    if (!credChart) {
        credChart = echarts.init(dom, 'dark');
        window.addEventListener('resize', () => credChart.resize());
    }

    const users = [...topUsers].reverse();
    const passes = [...topPasses].reverse();

    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            backgroundColor: 'rgba(10, 15, 30, 0.95)',
            borderColor: '#00f0ff',
            textStyle: { color: '#e2e8f0', fontFamily: 'JetBrains Mono' }
        },
        grid: {
            top: '8%',
            left: '3%',
            right: '6%',
            bottom: '5%',
            containLabel: true
        },
        xAxis: {
            type: 'value',
            splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
            axisLabel: { color: '#64748b', fontFamily: 'JetBrains Mono' }
        },
        yAxis: {
            type: 'category',
            data: users.map(u => u.username || 'unknown'),
            axisLabel: {
                color: '#00f0ff',
                fontFamily: 'JetBrains Mono',
                fontWeight: 600,
                fontSize: 11
            },
            axisLine: { lineStyle: { color: 'rgba(0, 240, 255, 0.3)' } }
        },
        series: [
            {
                name: 'Brute-force Hits',
                type: 'bar',
                data: users.map(u => u.count),
                itemStyle: {
                    borderRadius: [0, 4, 4, 0],
                    color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                        { offset: 0, color: 'rgba(0, 240, 255, 0.2)' },
                        { offset: 1, color: '#00f0ff' }
                    ])
                },
                label: {
                    show: true,
                    position: 'right',
                    color: '#94a3b8',
                    fontFamily: 'JetBrains Mono',
                    fontSize: 10
                }
            }
        ]
    };

    credChart.setOption(option);
}
