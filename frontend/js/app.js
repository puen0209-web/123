/**
 * SSH Honeypot SOC Dashboard Frontend Core Application
 */

const API_BASE = window.location.origin;
let audioEnabled = false;
let audioCtx = null;
let currentFilter = 'all';
let isTerminalPaused = false;
let demoModeActive = false;

// Audio Synthesizer (Web Audio API)
function playRadarBlip() {
    if (!audioEnabled) return;
    try {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, audioCtx.currentTime); // A5
        osc.frequency.exponentialRampToValueAtTime(440, audioCtx.currentTime + 0.12);

        gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.12);

        osc.connect(gain);
        gain.connect(audioCtx.destination);

        osc.start();
        osc.stop(audioCtx.currentTime + 0.12);
    } catch (e) {
        console.warn("Audio playback error:", e);
    }
}

// Format timestamps
function formatTime(isoStr) {
    if (!isoStr) return "--:--:--";
    try {
        const d = new Date(isoStr);
        return d.toTimeString().split(' ')[0] + '.' + String(d.getMilliseconds()).padStart(3, '0').slice(0, 2);
    } catch (e) {
        return isoStr;
    }
}

// Animate numeric counters
function animateNumber(elementId, targetVal) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const currentVal = parseInt(el.innerText.replace(/,/g, '')) || 0;
    if (currentVal === targetVal) return;

    let start = currentVal;
    const diff = targetVal - start;
    const duration = 600;
    const startTime = performance.now();

    function step(now) {
        const progress = Math.min((now - startTime) / duration, 1);
        const value = Math.floor(start + diff * progress);
        el.innerText = value.toLocaleString();
        if (progress < 1) {
            requestAnimationFrame(step);
        } else {
            el.innerText = targetVal.toLocaleString();
        }
    }
    requestAnimationFrame(step);
}

// Update HUD summary
function updateHUDMetrics(data) {
    if (!data) return;
    animateNumber("stat-total", data.total_events || 0);
    animateNumber("stat-24h", data.attacks_24h || 0);
    animateNumber("stat-ips", data.unique_ips || 0);
    animateNumber("stat-logins", data.login_success || 0);
    animateNumber("stat-cmds", data.total_commands || 0);
    animateNumber("stat-dls", data.total_downloads || 0);
}

// Append event to Terminal Waterfall Feed
function appendEventToTerminal(ev, isNew = true) {
    const stream = document.getElementById("terminal-stream");
    if (!stream) return;

    let typeBadge = '';
    let detailText = '';

    if (ev.event_type === 'login_failed') {
        typeBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold badge-fail">FAIL</span>`;
        detailText = `<span class="text-slate-400">auth:</span> <span class="text-rose-400 font-semibold">${escapeHtml(ev.username || '-')}:${escapeHtml(ev.password || '-')}</span>`;
    } else if (ev.event_type === 'login_success') {
        typeBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold badge-success animate-pulse">SUCCESS</span>`;
        detailText = `<span class="text-amber-300 font-bold">TRAPPED!</span> <span class="text-amber-400">${escapeHtml(ev.username || '-')}:${escapeHtml(ev.password || '-')}</span>`;
    } else if (ev.event_type === 'command') {
        typeBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold badge-cmd">CMD</span>`;
        detailText = `<code class="text-cyan-300 bg-cyan-950/60 px-1 py-0.5 rounded">$ ${escapeHtml(ev.command || '')}</code>`;
    } else if (ev.event_type === 'file_download') {
        typeBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold badge-dl">DROPPER</span>`;
        detailText = `<span class="text-purple-300 font-mono text-[11px] truncate block max-w-xs" title="${escapeHtml(ev.download_url)}">${escapeHtml(ev.download_url || '')}</span>`;
    } else {
        typeBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">${escapeHtml(ev.event_type)}</span>`;
        detailText = `<span class="text-slate-500">${escapeHtml(ev.src_ip)}</span>`;
    }

    const countryCode = ev.country_code && ev.country_code !== 'XX' ? ev.country_code.toLowerCase() : 'un';
    const flagHtml = `<span class="text-xs mr-1 font-bold text-slate-300">[${ev.country_code || '??'}]</span>`;

    const row = document.createElement("div");
    row.className = `event-row flex items-start gap-2 py-1.5 px-2 border-b border-cyan-950/40 text-xs font-mono ${isNew ? 'flash-new' : ''}`;
    row.setAttribute("data-type", ev.event_type);

    if (currentFilter !== 'all' && currentFilter !== ev.event_type) {
        row.style.display = 'none';
    }

    row.innerHTML = `
        <span class="text-slate-500 text-[11px] whitespace-nowrap">${formatTime(ev.timestamp)}</span>
        <div>${typeBadge}</div>
        <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1.5 flex-wrap">
                ${flagHtml}
                <span class="text-cyan-400 font-bold">${escapeHtml(ev.src_ip || '0.0.0.0')}</span>
                <span class="text-slate-600 text-[10px]">(${escapeHtml(ev.city || ev.country || 'Unknown')})</span>
            </div>
            <div class="mt-0.5 break-all">${detailText}</div>
        </div>
    `;

    if (isNew) {
        stream.insertBefore(row, stream.firstChild);
        // Trim stream length to 100 max
        if (stream.children.length > 120) {
            stream.removeChild(stream.lastChild);
        }
    } else {
        stream.appendChild(row);
    }
}

// Render Top 10 IP List
function renderTopIPs(ips = []) {
    const container = document.getElementById("top-ips-list");
    if (!container) return;

    if (!ips.length) {
        container.innerHTML = `<div class="text-slate-500 text-xs py-4 text-center">No attack records yet</div>`;
        return;
    }

    const maxCount = ips[0]?.hit_count || 1;
    let html = '';

    ips.forEach((item, idx) => {
        const pct = Math.round((item.hit_count / maxCount) * 100);
        const rankColor = idx === 0 ? 'text-rose-400 font-bold' : idx < 3 ? 'text-amber-400 font-semibold' : 'text-slate-400';
        
        html += `
            <div class="py-1.5 border-b border-slate-800/60 text-xs">
                <div class="flex items-center justify-between mb-1">
                    <div class="flex items-center gap-1.5">
                        <span class="w-4 ${rankColor}">#${idx + 1}</span>
                        <span class="font-mono text-cyan-300 font-semibold">${escapeHtml(item.src_ip)}</span>
                        <span class="text-[10px] text-slate-500">[${escapeHtml(item.country || 'Unknown')}]</span>
                    </div>
                    <span class="font-mono text-rose-400 font-bold">${item.hit_count} hits</span>
                </div>
                <div class="w-full bg-slate-900 rounded-full h-1 overflow-hidden">
                    <div class="bg-gradient-to-r from-cyan-500 to-rose-500 h-1 rounded-full" style="width: ${pct}%"></div>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

// Render Top Passwords Leaderboard
function renderTopPasswords(passwords = []) {
    const container = document.getElementById("top-passwords-list");
    if (!container) return;

    if (!passwords.length) {
        container.innerHTML = `<div class="text-slate-500 text-xs py-4 text-center">No password data yet</div>`;
        return;
    }

    let html = '';
    passwords.forEach((item, idx) => {
        html += `
            <div class="flex items-center justify-between py-1 border-b border-slate-800/40 text-xs font-mono">
                <span class="text-slate-400 truncate max-w-[120px]" title="${escapeHtml(item.password)}">
                    <span class="text-slate-600 mr-1.5">#${idx + 1}</span>${escapeHtml(item.password)}
                </span>
                <span class="text-amber-400 font-bold">${item.count}</span>
            </div>
        `;
    });
    container.innerHTML = html;
}

// Render Command Audit Table
function renderPayloadAudit(payloads = []) {
    const tbody = document.getElementById("payload-audit-table");
    if (!tbody) return;

    if (!payloads.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-6 text-slate-500 text-xs">No interactive payload activities recorded yet</td></tr>`;
        return;
    }

    let html = '';
    payloads.slice(0, 30).forEach(p => {
        const isDownload = p.event_type === 'file_download';
        const typeBadge = isDownload
            ? `<span class="badge-dl text-[10px] px-1.5 py-0.5 rounded font-bold">DROPPER</span>`
            : `<span class="badge-cmd text-[10px] px-1.5 py-0.5 rounded font-bold">SHELL</span>`;

        const content = isDownload
            ? `<div class="flex flex-col">
                 <span class="text-purple-400 font-mono text-xs">${escapeHtml(p.download_url)}</span>
                 <span class="text-slate-500 text-[10px] font-mono">SHA256: ${escapeHtml(p.download_hash || 'N/A')}</span>
               </div>`
            : `<code class="text-cyan-300 font-mono text-xs">$ ${escapeHtml(p.command)}</code>`;

        html += `
            <tr class="border-b border-slate-800/50 hover:bg-cyan-950/20 text-xs transition">
                <td class="py-2 px-3 text-slate-400 whitespace-nowrap font-mono">${formatTime(p.timestamp)}</td>
                <td class="py-2 px-3">${typeBadge}</td>
                <td class="py-2 px-3 text-cyan-400 font-mono font-semibold">${escapeHtml(p.src_ip)}</td>
                <td class="py-2 px-3 text-slate-400">${escapeHtml(p.city || p.country || 'Unknown')}</td>
                <td class="py-2 px-3">${content}</td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

// Helper to sanitize HTML
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// WebSocket Manager with auto-reconnect
function connectWebSocket() {
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${window.location.host}/ws/live`;
    const wsStatusDot = document.getElementById("ws-status-dot");
    const wsStatusText = document.getElementById("ws-status-text");

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        if (wsStatusDot) wsStatusDot.className = "live-dot";
        if (wsStatusText) wsStatusText.innerText = "STREAM: LIVE";
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === "new_event") {
                const ev = msg.data;
                appendEventToTerminal(ev, true);
                if (ev.longitude && ev.latitude) {
                    recordAttackOnMap(ev);
                }
                playRadarBlip();

                // Increment stat counter locally
                const totalEl = document.getElementById("stat-total");
                if (totalEl) {
                    const cur = parseInt(totalEl.innerText.replace(/,/g, '')) || 0;
                    totalEl.innerText = (cur + 1).toLocaleString();
                }

                // If command/download, prepend to payload table
                if (ev.event_type === 'command' || ev.event_type === 'file_download') {
                    refreshPayloads();
                }
            }
        } catch (e) {
            console.error("WS parse error:", e);
        }
    };

    ws.onclose = () => {
        if (wsStatusDot) wsStatusDot.className = "danger-dot";
        if (wsStatusText) wsStatusText.innerText = "STREAM: RECONNECTING";
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = () => {
        ws.close();
    };

    // Heartbeat ping
    setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
        }
    }, 25000);
}

// Data loaders
async function refreshSummary() {
    try {
        const res = await fetch(`${API_BASE}/api/stats/summary`);
        if (res.ok) {
            const data = await res.json();
            updateHUDMetrics(data);
        }
    } catch (e) {}
}

async function refreshTopStats() {
    try {
        const res = await fetch(`${API_BASE}/api/stats/top?limit=10`);
        if (res.ok) {
            const data = await res.json();
            renderTopIPs(data.top_ips);
            renderTopPasswords(data.top_passwords);
            renderCredentialChart("chart-credentials", data.top_usernames, data.top_passwords);
        }
    } catch (e) {}
}

async function refreshPayloads() {
    try {
        const res = await fetch(`${API_BASE}/api/payloads?limit=30`);
        if (res.ok) {
            const list = await res.json();
            renderPayloadAudit(list);
        }
    } catch (e) {}
}

async function loadInitialData() {
    // 1. Config & Node info
    let serverConfig = null;
    try {
        const confRes = await fetch(`${API_BASE}/api/config`);
        if (confRes.ok) {
            serverConfig = await confRes.json();
            demoModeActive = serverConfig.demo_mode;
            updateDemoButton();
            const nodeNameEl = document.getElementById("node-name");
            if (nodeNameEl) nodeNameEl.innerText = serverConfig.server_name;
        }
    } catch (e) {}

    // 2. Summary stats
    await refreshSummary();

    // 3. Top analytics
    await refreshTopStats();

    // 4. Geo stats & Threat Map
    try {
        const geoRes = await fetch(`${API_BASE}/api/stats/geo`);
        if (geoRes.ok) {
            const geoData = await geoRes.json();
            await initThreatMap("threat-map-container", geoData.server, geoData.points);
        } else {
            await initThreatMap("threat-map-container", serverConfig, []);
        }
    } catch (e) {
        await initThreatMap("threat-map-container", serverConfig, []);
    }

    // 5. Recent events for waterfall
    try {
        const evRes = await fetch(`${API_BASE}/api/events/recent?limit=40`);
        if (evRes.ok) {
            const events = await evRes.json();
            events.reverse().forEach(ev => appendEventToTerminal(ev, false));
        }
    } catch (e) {}

    // 6. Payloads
    await refreshPayloads();
}

function updateDemoButton() {
    const btn = document.getElementById("btn-demo-mode");
    if (!btn) return;
    if (demoModeActive) {
        btn.classList.add("active");
        btn.innerHTML = `<span class="live-dot mr-1.5"></span> DEMO: ON`;
    } else {
        btn.classList.remove("active");
        btn.innerHTML = `<span>⚡</span> DEMO: OFF`;
    }
}

// UI Event Listeners
document.addEventListener("DOMContentLoaded", () => {
    loadInitialData();
    connectWebSocket();

    // Clock
    setInterval(() => {
        const now = new Date();
        const utcEl = document.getElementById("clock-utc");
        const locEl = document.getElementById("clock-local");
        if (utcEl) utcEl.innerText = now.toUTCString().slice(17, 25) + " UTC";
        if (locEl) locEl.innerText = now.toTimeString().slice(0, 8) + " LOCAL";
    }, 1000);

    // Periodic Refresh for Leaderboards
    setInterval(() => {
        refreshSummary();
        refreshTopStats();
    }, 15000);

    // Audio Toggle
    const audioBtn = document.getElementById("btn-audio-toggle");
    if (audioBtn) {
        audioBtn.addEventListener("click", () => {
            audioEnabled = !audioEnabled;
            if (audioEnabled) {
                playRadarBlip();
                audioBtn.classList.add("active");
                audioBtn.innerHTML = `<span>🔊</span> SOUND: ON`;
            } else {
                audioBtn.classList.remove("active");
                audioBtn.innerHTML = `<span>🔇</span> SOUND: MUTED`;
            }
        });
    }

    // Demo Mode Toggle
    const demoBtn = document.getElementById("btn-demo-mode");
    if (demoBtn) {
        demoBtn.addEventListener("click", async () => {
            try {
                const res = await fetch(`${API_BASE}/api/demo/toggle`, { method: "POST" });
                if (res.ok) {
                    const data = await res.json();
                    demoModeActive = data.demo_mode;
                    updateDemoButton();
                }
            } catch (e) {}
        });
    }

    // Trigger Single Attack Test
    const fireBtn = document.getElementById("btn-fire-test");
    if (fireBtn) {
        fireBtn.addEventListener("click", async () => {
            try {
                await fetch(`${API_BASE}/api/demo/fire`, { method: "POST" });
            } catch (e) {}
        });
    }

    // Terminal Filter Tabs
    document.querySelectorAll(".tab-filter").forEach(tab => {
        tab.addEventListener("click", (e) => {
            document.querySelectorAll(".tab-filter").forEach(t => t.classList.remove("active", "border-cyan-400", "text-cyan-400"));
            tab.classList.add("active", "border-cyan-400", "text-cyan-400");
            currentFilter = tab.getAttribute("data-filter");

            // Filter rows
            document.querySelectorAll("#terminal-stream .event-row").forEach(row => {
                const rowType = row.getAttribute("data-type");
                if (currentFilter === 'all' || currentFilter === rowType) {
                    row.style.display = 'flex';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    });
});
