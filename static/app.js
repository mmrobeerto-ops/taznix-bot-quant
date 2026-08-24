// TZANiX Quant Algorithmic Dashboard Javascript controller

function deduplicateSeriesData(data) {
    const seen = new Map();
    data.forEach(item => {
        seen.set(item.time, item.value);
    });
    const result = [];
    seen.forEach((val, key) => {
        result.push({ time: key, value: val });
    });
    result.sort((a, b) => a.time - b.time);
    return result;
}

let socket;
let chart;
let priceSeries;
let sma200Series;
let vwapSeries;
let vwapUpperSeries;
let vwapLowerSeries;

// Flags for showing/hiding indicators
let showSma200 = true;
let showVwap = true;
let showVwapBands = true;
let showOfi = true;

// Keep track of ticks for plotting and overlays
let tickDataBuffer = [];
let chartMarkers = [];

// Local config state
let configState = {
    daily_loss_limit: 500.0,
    trailing_stop_pct: 0.5,
    vwap_threshold_pct: 0.15,
    max_position_size: 1.0,
    run_autopilot: true
};

// Log Tab State
let activeLogTab = "all";

document.addEventListener("DOMContentLoaded", () => {
    try {
        initClock();
        initChart();
        initWebSocket();
        setupEventListeners();
        fetchCurrentStatus();
        startConsolePolling();
    } catch (err) {
        console.error("Dashboard Init Error:", err);
        setTimeout(() => {
            const consoleOut = document.getElementById("terminal-output");
            if (consoleOut) {
                const line = document.createElement("div");
                line.className = "terminal-line critical";
                line.innerHTML = `<span class="timestamp">[FATAL]</span> <span style="font-weight:bold;">Dashboard Init Error:</span> ${err.message}<br><pre style="margin-top:0.25rem; font-size:0.65rem; color:#f87171; white-space: pre-wrap;">${err.stack}</pre>`;
                consoleOut.appendChild(line);
            }
        }, 500);
    }
});


// 1. Clock Initialization
function initClock() {
    const clock = document.getElementById("header-clock");
    setInterval(() => {
        const now = new Date();
        clock.textContent = now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    }, 1000);
}

// 2. High-Precision 2D TradingView Lightweight Charts Initialization
function initChart() { console.log("3D engine handled by tzanix_quantum-core.js"); }

// 3. WebSocket stream client
function initWebSocket() {
    const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProto}//${window.location.host}/ws`;
    
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        updateWebSocketBadge(true);
        appendTerminalLine("info", "WebSocket channel successfully connected to TZANiX Quant Broker simulator.");
    };

    socket.onclose = () => {
        updateWebSocketBadge(false);
        appendTerminalLine("critical", "WebSocket disconnected. Reconnecting in 3 seconds...");
        setTimeout(initWebSocket, 3000);
    };

    socket.onerror = (err) => {
        console.error("WebSocket error:", err);
        updateWebSocketBadge(false);
    };

    socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        
        if (payload.type === "history") {
            handleHistoricalTicks(payload.ticks);
            updateDashboardMetrics(payload.metrics);
            updateActivePosition(payload.active_position);
        } else if (payload.type === "tick") {
            handleLiveTick(payload);
            updateDashboardMetrics(payload.metrics);
            updateActivePosition(payload.active_position);
        } else if (payload.type === "news") {
            triggerNewsAlertBanner(payload);
        }
    };
}

// Frontend Candlestick Aggregator State
let currentCandle = null;
let candleInterval = 60; // Default 1 minute candles

function handleHistoricalTicks(ticks) {
    tickDataBuffer = ticks;
    
    const candles = [];
    const sma200s = [];
    const vwaps = [];
    const vwapUppers = [];
    const vwapLowers = [];

    // Temporary map to aggregate history into 1m intervals
    const minuteMap = {};

    ticks.forEach(t => {
        if (window.updateHFTChart) {
            window.updateHFTChart(t.micro_price, t.mid_price, t.price, null, null);
        }
        const itemTime = Math.floor(t.timestamp);
        const minuteTime = Math.floor(itemTime / candleInterval) * candleInterval;
        const price = Number(t.price);
        
        if (!minuteMap[minuteTime]) {
            minuteMap[minuteTime] = { 
                time: minuteTime, 
                open: price, high: price, low: price, close: price,
                sma: null, vwap: null, vwap_upper: null, vwap_lower: null
            };
        } else {
            minuteMap[minuteTime].high = Math.max(minuteMap[minuteTime].high, price);
            minuteMap[minuteTime].low = Math.min(minuteMap[minuteTime].low, price);
            minuteMap[minuteTime].close = price;
        }
        
        // Take the latest indicator value for the minute
        if (t.sma_200 !== null && t.sma_200 !== undefined) minuteMap[minuteTime].sma = Number(t.sma_200);
        if (t.vwap !== null && t.vwap !== undefined) minuteMap[minuteTime].vwap = Number(t.vwap);
        if (t.vwap_upper !== null && t.vwap_upper !== undefined) minuteMap[minuteTime].vwap_upper = Number(t.vwap_upper);
        if (t.vwap_lower !== null && t.vwap_lower !== undefined) minuteMap[minuteTime].vwap_lower = Number(t.vwap_lower);
    });

    Object.keys(minuteMap).sort((a, b) => a - b).forEach(k => {
        const m = minuteMap[k];
        candles.push(m);
        if (m.sma !== null) sma200s.push({ time: m.time, value: m.sma });
        if (m.vwap !== null) vwaps.push({ time: m.time, value: m.vwap });
        if (m.vwap_upper !== null) vwapUppers.push({ time: m.time, value: m.vwap_upper });
        if (m.vwap_lower !== null) vwapLowers.push({ time: m.time, value: m.vwap_lower });
        currentCandle = m; // Save the last one as current
    });

    
    // if (showSma200) sma200Series.setData(sma200s);
    // if (showVwap) vwapSeries.setData(vwaps);
    if (false) {
        vwapUpperSeries.setData(vwapUppers);
        vwapLowerSeries.setData(vwapLowers);
    }
    
    // Fit content
    
    
    // Fetch historical orders to plot trade marks
    fetchOrdersAndPlotMarkers();
}

function handleLiveTick(tick) {
    tick.timestamp = Math.floor(tick.timestamp); // Normalize to integer seconds
    const itemTime = tick.timestamp;
    const minuteTime = Math.floor(itemTime / candleInterval) * candleInterval;
    const priceVal = Number(tick.price);
    
    // Candlestick Live Update
    if (!currentCandle || currentCandle.time !== minuteTime) {
        currentCandle = { time: minuteTime, open: priceVal, high: priceVal, low: priceVal, close: priceVal };
    } else {
        currentCandle.high = Math.max(currentCandle.high, priceVal);
        currentCandle.low = Math.min(currentCandle.low, priceVal);
        currentCandle.close = priceVal;
    }
    
    
    
    // Update DOM Metrics
    document.getElementById("lbl-zscore").textContent = tick.z_score ? tick.z_score.toFixed(2) : "0.00";
        
        const btcEl = document.getElementById("live-btc-price");
        if (btcEl && tick.price) {
            const currentPrice = parseFloat(tick.price);
            window.prevBtcPrice = currentPrice;
            
            btcEl.textContent = `$${currentPrice.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        }
    document.getElementById("lbl-ofi").textContent = tick.ofi ? tick.ofi.toFixed(2) : "0.00";

    // Forward to HFT chart
    if (window.updateHFTChart) {
        window.updateHFTChart(tick.micro_price, tick.mid_price, tick.price, tick.bids, tick.asks);
    }
    
    // Update traffic lights
    const lightOfi = document.getElementById("light-ofi");
    if (lightOfi) {
        lightOfi.style.backgroundColor = Math.abs(tick.ofi || 0) < 0.8 ? "#00FF66" : "#FF3333";
    }
    const lightAdx = document.getElementById("light-adx");
    if (lightAdx) {
        lightAdx.style.backgroundColor = (tick.adx_15m && tick.adx_15m >= 16.0) ? "#00FF66" : "#444";
    }
    const lightQuar = document.getElementById("light-quarantine");
    if (lightQuar) {
        const nowUtc = new Date();
        const mins = nowUtc.getUTCMinutes();
        const isQuarantined = (mins >= 57 || mins <= 2);
        lightQuar.style.backgroundColor = isQuarantined ? "#FF3333" : "#555";
    }
    
    if (false) {
        vwapSeries.update({ time: minuteTime, value: Number(tick.vwap) });
    }
    if (false) {
        vwapUpperSeries.update({ time: minuteTime, value: Number(tick.vwap_upper) });
    }
    if (false) {
        vwapLowerSeries.update({ time: minuteTime, value: Number(tick.vwap_lower) });
    }
    
    // Update DOM Metrics
    if (tick.z_score !== undefined && tick.z_score !== null) {
        document.getElementById('lbl-zscore').textContent = Number(tick.z_score).toFixed(3);
    }
    if (tick.ofi !== undefined && tick.ofi !== null) {
        document.getElementById('lbl-ofi').textContent = Number(tick.ofi).toFixed(2);
    }
    
    // Maintain a local small buffer for latest ticks
    tickDataBuffer.push(tick);
    if (tickDataBuffer.length > 200) {
        tickDataBuffer.shift();
    }
}

// Fetch SQLite trade logs to map on the 2D chart using markers
async function fetchOrdersAndPlotMarkers() {
    try {
        const res = await fetch("/api/orders?limit=100&exclude_rejected=true");
        const orders = await res.json();
        
        chartMarkers = [];
        
        orders.forEach(o => {
            if (o.status === "REJECTED") return;
                        // Plot Entry Marker
            const isGolden = o.reason && (o.reason.includes("[GOLDEN SIGNAL]") || o.reason.includes("GOLDEN FRACTAL"));
            chartMarkers.push({
                time: Math.floor(o.timestamp),
                position: o.type === "BUY" ? "belowBar" : "aboveBar",
                color: isGolden ? "#ffd700" : (o.type === "BUY" ? "#00E5FF" : "#FF4D4D"), // Cyan for Buy, Red for Sell
                shape: o.type === "BUY" ? "arrowUp" : "arrowDown",
                text: o.type === "BUY" ? "SEÑAL DE COMPRA" : "VENDA"
            });
            
            // Plot Close Marker if closed
            if (o.status === "CLOSED" && o.close_timestamp) {
                const profit = o.profit_loss || 0.0;
                chartMarkers.push({
                    time: Math.floor(o.close_timestamp),
                    position: o.type === "BUY" ? "aboveBar" : "belowBar",
                    color: profit > 0 ? "#ffd700" : "#6B1D2F", // Wine Red for loss/closed
                    shape: "circle",
                    text: `Close @ ${o.close_price} (${profit >= 0 ? '+' : ''}${profit.toFixed(2)})`
                });
            }
        });
        
        // Sort markers by time chronologically
        chartMarkers.sort((a, b) => a.time - b.time);
        
    } catch (e) {
        console.error("Error setting chart markers:", e);
    }
}

// 5. Dashboard updates
function updateDashboardMetrics(metrics) {
    // Engine State
    const stateEl = document.getElementById("lbl-engine-state");
    const badgeEngine = document.getElementById("val-engine-badge");
    const containerBadgeEngine = document.getElementById("indicator-engine");
    const btnToggle = document.getElementById("btn-toggle-autopilot");
    const lblToggle = document.getElementById("lbl-toggle-btn");
    
    stateEl.textContent = metrics.engine_status;
    badgeEngine.textContent = metrics.engine_status;
    
    // Clear old state classes
    stateEl.className = "engine-state-large";
    containerBadgeEngine.className = "status-indicator-badge";
    
    if (metrics.engine_status === "ACTIVE") {
        stateEl.classList.add("text-green");
        containerBadgeEngine.classList.add("active");
        btnToggle.disabled = false;
        btnToggle.className = "btn btn-gold";
        lblToggle.textContent = "Pause Engine";
    } else if (metrics.engine_status === "PAUSED" || metrics.engine_status === "NEWS_PAUSED") {
        stateEl.classList.add("paused");
        containerBadgeEngine.classList.add("paused");
        btnToggle.disabled = false;
        btnToggle.className = "btn btn-outline";
        lblToggle.textContent = "Resume Engine";
    } else if (metrics.engine_status === "KILL_SWITCH") {
        stateEl.classList.add("kill_switch");
        containerBadgeEngine.classList.add("killswitch");
        btnToggle.disabled = true; // Blocked under Kill-Switch
        lblToggle.textContent = "Locked";
    }

    // News Lock Badge
    const badgeNews = document.getElementById("val-news-badge");
    const containerBadgeNews = document.getElementById("indicator-news");
    if (metrics.active_news_event) {
        badgeNews.textContent = "PAUSED";
        containerBadgeNews.classList.add("active");
    } else {
        badgeNews.textContent = "INACTIVE";
        containerBadgeNews.classList.remove("active");
    }

    // Session PNL
    const pnlEl = document.getElementById("val-session-pnl");
    pnlEl.textContent = `${metrics.session_pnl >= 0 ? '+' : ''}$${metrics.session_pnl.toFixed(2)}`;
    pnlEl.className = "metric-value-large " + (metrics.session_pnl >= 0 ? "positive" : "negative");
    
    // Track Funded Capital (Real balance from Binance API)
    const currentCapital = metrics.account_balance;
    document.getElementById("val-session-capital").textContent = `$${currentCapital.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    document.getElementById("val-session-peak").textContent = `$${metrics.session_pnl >= 0 ? metrics.session_pnl.toFixed(2) : '0.00'}`;

    // Total Trades & Win rate
    document.getElementById("val-win-rate").textContent = `${metrics.win_rate.toFixed(1)}%`;
    document.getElementById("val-total-trades").textContent = metrics.total_trades;
    
    // Update win count (closed wins)
    const closedWins = Math.round(metrics.total_trades * (metrics.win_rate / 100));
    document.getElementById("val-total-wins").textContent = isNaN(closedWins) ? 0 : closedWins;

    // Killswitch risk tracker (Progress Bar)
    const progressEl = document.getElementById("killswitch-progress");
    const valRiskCurrent = document.getElementById("val-risk-current");
    const valRiskLimit = document.getElementById("val-risk-limit");
    const lblKillswitchStatus = document.getElementById("lbl-killswitch-status");
    const btnResetKill = document.getElementById("btn-reset-killswitch");

    const limit = configState.daily_loss_limit;
    valRiskLimit.textContent = `-$${limit.toFixed(2)}`;
    
    // Drawdown calculation toward the limit
    const loss = metrics.session_pnl < 0 ? Math.abs(metrics.session_pnl) : 0.0;
    valRiskCurrent.textContent = `-$${loss.toFixed(2)}`;
    
    const pct = Math.min((loss / limit) * 100.0, 100.0);
    progressEl.style.width = `${pct}%`;
    
    if (metrics.kill_switch_active) {
        lblKillswitchStatus.textContent = "TRIGGERED";
        lblKillswitchStatus.className = "danger-text";
        btnResetKill.disabled = false;
        
        // Dynamic styling tweaks
        progressEl.style.backgroundColor = "var(--color-red)";
    } else {
        lblKillswitchStatus.textContent = "SAFE";
        lblKillswitchStatus.className = "text-green";
        btnResetKill.disabled = true;
    }
}

function updateActivePosition(pos) {
    const emptyState = document.getElementById("pos-empty-state");
    const activeState = document.getElementById("pos-active-state");
    const btcEl = document.getElementById("live-btc-price");
    
    if (!pos) {
        emptyState.classList.remove("hide");
        activeState.classList.add("hide");
        window.globalMarketState = 0; // Neutral
        if (btcEl) {
            btcEl.style.color = "#FFFFFF";
            btcEl.style.textShadow = "0 0 5px #FFFFFF, 0 0 10px #FFFFFF";
        }
        return;
    }
    
    emptyState.classList.add("hide");
    activeState.classList.remove("hide");

    window.globalMarketState = pos.type === "BUY" ? 1 : -1;
    if (btcEl) {
        if (pos.type === "BUY") {
            btcEl.style.color = "#00FF9D";
            btcEl.style.textShadow = "0 0 10px #00FF9D, 0 0 20px #00FF9D";
        } else {
            btcEl.style.color = "#FF2E63";
            btcEl.style.textShadow = "0 0 10px #FF2E63, 0 0 20px #FF2E63";
        }
    }

    const badge = document.getElementById("lbl-pos-type");
    badge.textContent = pos.type;
    badge.className = "pos-badge " + (pos.type === "BUY" ? "" : "sell");

    document.getElementById("lbl-pos-qty").textContent = pos.quantity.toFixed(3);
    document.getElementById("lbl-pos-entry").textContent = `$${pos.entry_price.toFixed(2)}`;
    document.getElementById("lbl-pos-sl").textContent = `$${pos.stop_loss.toFixed(2)}`;
    document.getElementById("lbl-pos-tp").textContent = `$${pos.take_profit.toFixed(2)}`;
    
    // Calculate live current price and unrealized PnL
    const latestTick = tickDataBuffer[tickDataBuffer.length - 1];
    const currentPrice = latestTick ? latestTick.price : pos.entry_price;
    
    document.getElementById("lbl-pos-current").textContent = `$${currentPrice.toFixed(2)}`;
    
    let pnl = 0.0;
    if (pos.type === "BUY") {
        pnl = (currentPrice - pos.entry_price) * pos.quantity;
    } else {
        pnl = (pos.entry_price - currentPrice) * pos.quantity;
    }

    const pnlBanner = document.querySelector(".pos-pnl-banner");
    const pnlVal = document.getElementById("lbl-pos-pnl");
    pnlVal.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
    
    if (pnl >= 0) {
        pnlBanner.className = "pos-pnl-banner";
        pnlVal.className = "pnl-banner-val text-green";
    } else {
        pnlBanner.className = "pos-pnl-banner negative";
        pnlVal.className = "pnl-banner-val danger-text";
    }

    document.getElementById("lbl-pos-reason").textContent = pos.reason;
}

function updateWebSocketBadge(connected) {
    const badge = document.getElementById("val-ws-badge");
    const containerBadge = document.getElementById("indicator-websocket");
    
    if (connected) {
        badge.textContent = "CONNECTED";
        containerBadge.className = "status-indicator-badge connected";
    } else {
        badge.textContent = "DISCONNECTED";
        containerBadge.className = "status-indicator-badge";
    }
}

// 6. Config form fetching and syncing
async function fetchCurrentStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();
        
        configState = data.config;
        syncConfigForm(data.config);
        updateDashboardMetrics(data.metrics);
        updateActivePosition(data.active_position);
    } catch (e) {
        console.error("Error fetching status:", e);
    }
}

function syncConfigForm(cfg) {
    // Form limits
    const lossInput = document.getElementById("input-loss-limit");
    if (lossInput) {
        lossInput.value = cfg.daily_loss_limit;
        document.getElementById("display-loss-limit").textContent = `$${cfg.daily_loss_limit.toFixed(2)}`;
    }
}

// 7. Event listeners binding
function setupEventListeners() {

    const btnSimVol = document.getElementById("btn-sim-volatility");
    if (btnSimVol) {
        btnSimVol.addEventListener("click", () => {
            fetch("/api/simulate/spike?direction=UP", {method: "POST"}).catch(e => console.error(e));
        });
    }

    const btnStartBot = document.getElementById("btn-start-bot");
    if (btnStartBot) {
        btnStartBot.addEventListener("click", () => {
            document.getElementById("btn-toggle-autopilot").click(); // Trigger the real autopilot button logic
        });
    }

    const inputs = [
        { id: "input-loss-limit", displayId: "display-loss-limit", prefix: "$", suffix: "" }
    ];

    inputs.forEach(item => {

        const el = document.getElementById(item.id);
        const disp = document.getElementById(item.displayId);
        
        el.addEventListener("input", (e) => {
            const val = parseFloat(e.target.value);
            disp.textContent = `${item.prefix}${val.toFixed(2)}${item.suffix}`;
        });

        // Auto-save dynamically when the user releases the slider
        el.addEventListener("change", async () => {
            const payload = {
                daily_loss_limit: parseFloat(document.getElementById("input-loss-limit").value),
                trailing_stop_pct: configState.trailing_stop_pct,
                vwap_threshold_pct: configState.vwap_threshold_pct,
                concrete_floor_threshold_pct: configState.concrete_floor_threshold_pct,
                max_position_size: configState.max_position_size,
                run_autopilot: configState.run_autopilot
            };

            try {
                const res = await fetch("/api/config", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                configState = data.config;
                appendTerminalLine("info", `Risk control auto-saved: Loss Limit: $${payload.daily_loss_limit.toFixed(2)}, Trailing SL: ${payload.trailing_stop_pct.toFixed(2)}%, VWAP Limit: ${payload.vwap_threshold_pct.toFixed(2)}%`);
                fetchCurrentStatus();
            } catch (err) {
                appendTerminalLine("critical", `Failed to apply risk parameter: ${err.message}`);
            }
        });
    });


    // Toggle Autopilot Autonomously
    document.getElementById("btn-toggle-autopilot").addEventListener("click", async () => {
        const newAutopilot = !configState.run_autopilot;
        
        const payload = {
            ...configState,
            run_autopilot: newAutopilot
        };

        try {
            const res = await fetch("/api/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            configState = data.config;
            appendTerminalLine("info", `Autopilot state toggled. Run autopilot = ${newAutopilot.toString().toUpperCase()}`);
            fetchCurrentStatus();
        } catch (err) {
            appendTerminalLine("critical", `Error toggling Autopilot: ${err.message}`);
        }
    });

    // Reset Kill Switch
    document.getElementById("btn-reset-killswitch").addEventListener("click", async () => {
        try {
            const res = await fetch("/api/killswitch/reset", { method: "POST" });
            const data = await res.json();
            appendTerminalLine("info", "Kill-Switch manually reset. Execution system reactivated.");
            fetchCurrentStatus();
            fetchOrdersAndPlotMarkers(); // Reload chart markers
        } catch (err) {
            appendTerminalLine("critical", `Failed to reset Kill-Switch: ${err.message}`);
        }
    });

    // Forced Spikes (Simulation)
    // document.getElementById("btn-sim-spike-up").addEventListener("click", () => forceSpike("UP"));
    // document.getElementById("btn-sim-spike-down").addEventListener("click", () => forceSpike("DOWN"));

    // Show History Modal
    document.getElementById("btn-show-history").addEventListener("click", () => {
        document.getElementById("history-modal").classList.remove("hide");
        loadHistoryTable();
    });

    // Close History Modal
    document.getElementById("btn-close-history").addEventListener("click", () => {
        document.getElementById("history-modal").classList.add("hide");
    });

    // Close on overlay click
    document.getElementById("history-modal").addEventListener("click", (e) => {
        if (e.target.id === "history-modal") {
            document.getElementById("history-modal").classList.add("hide");
        }
    });

    // Toggle Indicators
    

    

    

    

    

    

    // Clear Terminal console
    document.getElementById("btn-clear-terminal").addEventListener("click", () => {
        const body = document.getElementById("terminal-table-body");
        if (body) body.innerHTML = "";
    });

    // Timeframe controls
    const tfButtons = [
        { id: "btn-tf-1m", interval: 60 },
        { id: "btn-tf-5m", interval: 300 },
        { id: "btn-tf-15m", interval: 900 },
        { id: "btn-tf-1h", interval: 3600 },
        { id: "btn-tf-4h", interval: 14400 },
        { id: "btn-tf-12h", interval: 43200 },
        { id: "btn-tf-24h", interval: 86400 }
    ];
    
    tfButtons.forEach(btnConfig => {
        const el = document.getElementById(btnConfig.id);
        if (el) {
            el.addEventListener("click", (e) => {
                // Update active class
                tfButtons.forEach(b => {
                    const btn = document.getElementById(b.id);
                    if (btn) btn.classList.remove("active");
                });
                e.target.classList.add("active");
                
                // Update interval and rebuild chart
                candleInterval = btnConfig.interval;
                if (tickDataBuffer.length > 0) {
                    handleHistoricalTicks(tickDataBuffer);
                    fetchOrdersAndPlotMarkers();
                }
                appendTerminalLine("info", `Timeframe changed to ${btnConfig.id.replace('btn-tf-', '')}`);
            });
        }
    });

    // Reset Database and In-memory Stats
    document.getElementById("btn-reset-db").addEventListener("click", async () => {
        if (!confirm("¿Estás seguro de que deseas reiniciar todo el historial de operaciones y estadísticas de sesión? Se creará una copia de seguridad en SQLite automáticamente antes de borrar los datos.")) {
            return;
        }
        try {
            appendTerminalLine("warning", "Solicitando reinicio del historial de operaciones...");
            const res = await fetch("/api/database/reset", { method: "POST" });
            const data = await res.json();
            
            if (res.ok) {
                appendTerminalLine("info", "HISTORIAL REINICIADO CON ÉXITO. Todas las estadísticas se han restablecido a cero.");
                // Clear trade markers on the chart by reloading
                fetchOrdersAndPlotMarkers();
                // Reset stats displayed on the UI
                if (data.metrics) {
                    updateDashboardMetrics(data.metrics);
                }
                document.getElementById("terminal-output").innerHTML = "";
                appendTerminalLine("info", "TZANiX Quant: Sistema limpio y listo para operar en real.");
            } else {
                appendTerminalLine("critical", `Error al reiniciar historial: ${data.detail || 'Error desconocido'}`);
            }
        } catch (e) {
            appendTerminalLine("critical", `Error de conexión: ${e.message}`);
        }
    });

    // Logs Tabs Toggles
    document.getElementById("tab-log-all").addEventListener("click", (e) => {
        activeLogTab = "all";
        toggleActiveTab(e.target);
        fetchRecentLogs();
    });

    document.getElementById("tab-log-orders").addEventListener("click", (e) => {
        activeLogTab = "orders";
        toggleActiveTab(e.target);
        fetchRecentOrders();
    });
}

function toggleActiveTab(clickedEl) {
    document.querySelectorAll(".console-tab").forEach(tab => tab.classList.remove("active"));
    clickedEl.classList.add("active");
}

function refreshIndicatorSeries(key, series) {
    const data = tickDataBuffer
        .filter(t => t[key] !== null && t[key] !== undefined)
        .map(t => ({ time: Math.floor(t.timestamp), value: t[key] }));
    series.setData(deduplicateSeriesData(data));
}

async function forceSpike(direction) {
    try {
        appendTerminalLine("warning", `Sending request to force market spike ${direction}...`);
        await fetch(`/api/simulate/spike?direction=${direction}`, { method: "POST" });
        setTimeout(fetchOrdersAndPlotMarkers, 500); // Reload trade markers
    } catch (e) {
        appendTerminalLine("critical", `Failed to force spike: ${e.message}`);
    }
}

// 8. Console Logging and Output panel (Quant Brutalism structured table)
function appendTerminalLine(level, message, timestamp = null) {
    const tableBody = document.getElementById("terminal-table-body");
    if (!tableBody) return;
    
    // Create new row
    const row = document.createElement("tr");
    row.style.borderBottom = "1px solid #1A1A1A";
    row.style.fontFamily = "var(--font-mono)";
    row.style.fontSize = "11px";
    row.style.height = "22px";
    
    // Format timestamp
    const d = timestamp ? new Date(timestamp * 1000) : new Date();
    const pad = (n) => n.toString().padStart(2, '0');
    const tsStr = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    
    // Parse message fields
    let action = "LOG";
    let computeTime = "50 µs"; // default mock core latency
    let price = "N/A";
    let zScore = "0.00";
    let ofi = "0.00";
    let adxVal = "N/A";
    let statusMotivo = message;
    
    // Color style classes for action column
    let actionColor = "#888888";
    
    if (message.includes("SIGNAL REJECTED: BUY") || (message.includes("BUY") && level === "warning")) {
        action = "REJECT (BUY)";
        actionColor = "#FF3333";
    } else if (message.includes("SIGNAL REJECTED: SELL") || (message.includes("SELL") && level === "warning")) {
        action = "REJECT (SELL)";
        actionColor = "#FF3333";
    } else if (message.includes("FUTURES LIVE SUCCESS") || message.includes("executed") || message.includes("ORDER FILLED")) {
        if (message.includes("BUY")) {
            action = "EXEC (BUY)";
            actionColor = "#00FF66";
        } else {
            action = "EXEC (SELL)";
            actionColor = "#00FF66";
        }
        computeTime = "42 µs";
    } else if (level === "system" || message.startsWith("SYSTEM:")) {
        action = "SYSTEM";
        actionColor = "#3b82f6";
    } else if (level === "error" || level === "critical") {
        action = "ERROR";
        actionColor = "#FF3333";
    }
    
    // Extract price
    const priceMatch = message.match(/(?:at|price=|\$|filled\s*at|close\s*@\s*)(\d+\.?\d*)/i);
    if (priceMatch) {
        price = parseFloat(priceMatch[1]).toLocaleString('en-US', { minimumFractionDigits: 2 });
    }
    
    // Extract Z-Score
    const zMatch = message.match(/(?:Z-Score|Z-score|Z=)\s*(-?\d+\.?\d*)/i);
    if (zMatch) {
        zScore = parseFloat(zMatch[1]).toFixed(2);
    }
    
    // Extract OFI
    const ofiMatch = message.match(/(?:OFI=)\s*(-?\d+\.?\d*)/i);
    if (ofiMatch) {
        ofi = parseFloat(ofiMatch[1]).toFixed(2);
    }
    
    // Extract ADX
    const adxMatch = message.match(/(?:ADX=)\s*(-?\d+\.?\d*)/i);
    if (adxMatch) {
        adxVal = parseFloat(adxMatch[1]).toFixed(0);
    }
    
    // Clean status/reason string of prefixes
    statusMotivo = statusMotivo
        .replace(/SIGNAL REJECTED:\s*/i, "")
        .replace(/SYSTEM:\s*/i, "")
        .replace(/\[FUTURES LIVE SUCCESS\]\s*/i, "");
        
    row.innerHTML = `
        <td style="padding: 4px 8px; color: #555;">${tsStr}</td>
        <td style="padding: 4px 8px; color: ${actionColor}; font-weight: bold;">${action}</td>
        <td style="padding: 4px 8px; color: #666;">${computeTime}</td>
        <td style="padding: 4px 8px; color: #FFF; font-weight: bold;">${price !== "N/A" ? "$" + price : "N/A"}</td>
        <td style="padding: 4px 8px; color: ${parseFloat(zScore) >= 0 ? '#00FF66' : '#FF3333'};">${zScore}</td>
        <td style="padding: 4px 8px; color: ${parseFloat(ofi) >= 0 ? '#00FF66' : '#FF3333'};">${ofi}</td>
        <td style="padding: 4px 8px; color: #666;">${adxVal}</td>
        <td style="padding: 4px 8px; color: #AAA; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${statusMotivo}">${statusMotivo}</td>
    `;
    
    tableBody.appendChild(row);
    
    // Scroll to bottom
    const consoleOut = document.getElementById("terminal-output");
    if (consoleOut) {
        consoleOut.scrollTop = consoleOut.scrollHeight;
    }
}

// Fetch SQLite generic audit logs
async function fetchRecentLogs() {
    try {
        const res = await fetch("/api/logs?limit=50");
        const logs = await res.json();
        
        const body = document.getElementById("terminal-table-body");
        if (body) body.innerHTML = "";
        
        // Reverse array to display chronological order (oldest to newest)
        logs.reverse().forEach(log => {
            appendTerminalLine(log.level, log.message, log.timestamp);
        });
    } catch (e) {
        console.error("Error loading logs:", e);
    }
}

// Fetch SQLite trade log (Orders Audit Trail)
async function fetchRecentOrders() {
    try {
        const res = await fetch("/api/orders?limit=50");
        const orders = await res.json();
        
        const body = document.getElementById("terminal-table-body");
        if (body) body.innerHTML = "";
        
        orders.reverse().forEach(o => {
            let msg = `[${o.status}] ${o.type} Order size=${o.quantity.toFixed(3)} | Entry=${o.entry_price.toFixed(2)} | SL=${o.stop_loss.toFixed(2)} | TP=${o.take_profit.toFixed(2)}`;
            if (o.status === "CLOSED") {
                msg += ` | Closed=${o.close_price.toFixed(2)} P&L=${o.profit_loss >= 0 ? '+' : ''}${o.profit_loss.toFixed(2)}`;
            }
            msg += ` | Reason: ${o.reason}`;
            
            const level = o.status === "REJECTED" ? "warning" : (o.status === "CLOSED" && (o.profit_loss || 0.0) < 0 ? "error" : "info");
            appendTerminalLine(level, msg, o.timestamp);
        });
    } catch (e) {
        console.error("Error loading orders:", e);
    }
}

function startConsolePolling() {
    // Poll logs every 3 seconds to keep tabs synchronized
    setInterval(() => {
        if (activeLogTab === "all") {
            fetchRecentLogs();
        } else {
            fetchRecentOrders();
        }
    }, 3000);
}

// 9. News Volatility Banner Controls
function triggerNewsAlertBanner(news) {
    const banner = document.getElementById("news-banner-alert");
    const desc = document.getElementById("lbl-news-alert-desc");
    const timer = document.getElementById("val-news-countdown");
    
    desc.textContent = news.title;
    banner.classList.remove("hide");
    
    appendTerminalLine("warning", `PAUSED INGESTION: News event '${news.title}' triggered. Signal search frozen.`);
    
    let countdown = news.duration;
    timer.textContent = `${countdown}s`;
    
    const interval = setInterval(() => {
        countdown--;
        timer.textContent = `${countdown}s`;
        
        if (countdown <= 0) {
            clearInterval(interval);
            banner.classList.add("hide");
            fetchOrdersAndPlotMarkers(); // Reload markers
        }
    }, 1000);
}

async function loadHistoryTable() {
    try {
        const res = await fetch("/api/orders?limit=100&exclude_rejected=true");
        let orders = await res.json();
        // Filter out rejected signals so the history modal only shows executed trades
        orders = orders.filter(o => o.status !== "REJECTED");
        const tbody = document.getElementById("history-table-body");
        tbody.innerHTML = "";
        
        if (orders.length === 0) {
            tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 2rem;">No hay operaciones registradas en SQLite.</td></tr>`;
            return;
        }
        
        orders.forEach(o => {
            const tr = document.createElement("tr");
            
            // Format timestamp
            const dateStr = new Date(o.timestamp * 1000).toLocaleString();
            
            // Format duration
            let durationStr = "-";
            if (o.status === "CLOSED" && o.close_timestamp) {
                const diff = o.close_timestamp - o.timestamp;
                if (diff < 60) {
                    durationStr = `${Math.round(diff)}s`;
                } else {
                    durationStr = `${Math.floor(diff / 60)}m ${Math.round(diff % 60)}s`;
                }
            } else if (o.status === "EXECUTED") {
                durationStr = `<span class="status-badge executed" style="animation: pulse 2s infinite;">Activa</span>`;
            }
            
            // Format P&L
            let pnlHtml = "-";
            if (o.status === "CLOSED") {
                const pnl = o.profit_loss || 0.0;
                const pnlClass = pnl > 0 ? "positive" : (pnl < 0 ? "negative" : "neutral");
                const prefix = pnl > 0 ? "+" : "";
                pnlHtml = `<span class="pnl-val ${pnlClass}">${prefix}$${pnl.toFixed(2)}</span>`;
            }
            
            // Format close price
            const closePriceStr = o.close_price ? `$${o.close_price.toFixed(2)}` : "-";
            
            tr.innerHTML = `
                <td style="font-family: var(--font-mono); color: var(--gold-dim); font-size: 0.65rem;">${o.id}</td>
                <td>${dateStr}</td>
                <td style="font-weight: 700; color: ${o.type === 'BUY' ? 'var(--color-green)' : 'var(--color-red)'};">${o.type}</td>
                <td style="font-family: var(--font-mono);">${o.quantity.toFixed(3)}</td>
                <td style="font-family: var(--font-mono);">$${o.entry_price.toFixed(2)}</td>
                <td style="font-family: var(--font-mono); text-decoration: underline dashed rgba(239, 68, 68, 0.4);">$${o.stop_loss.toFixed(2)}</td>
                <td style="font-family: var(--font-mono); text-decoration: underline dashed rgba(16, 185, 129, 0.4);">$${o.take_profit.toFixed(2)}</td>
                <td style="font-family: var(--font-mono);">${closePriceStr}</td>
                <td>${pnlHtml}</td>
                <td class="duration-lbl">${durationStr}</td>
                <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${o.reason}">${o.reason}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error loading history modal table:", err);
    }
}
