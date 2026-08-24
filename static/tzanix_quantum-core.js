// TZANiX Æther Core - HFT Spread & Order Book Heatmap Monitor (Quant Brutalism Design)
// Renders the real-time Order Book Heatmap (Depth L2) and Micro-price vs Mid-price spread.

(function() {
    let canvas, ctx, container;
    let ticks = [];
    const maxTicks = 150;
    let lastIndex = 0;
    let baselinePrice = 77200.00;
    
    // T2T Latencies History
    let t2tHistory = [];
    const maxLatencies = 50;
    for (let i = 0; i < maxLatencies; i++) {
        t2tHistory.push(10 + Math.random() * 45); // simulated baseline 10ms - 55ms
    }

    function generateMockTick(index) {
        const step = (Math.random() - 0.5) * 6.0;
        baselinePrice += step;
        const imbalance = Math.sin(index * 0.1) * 2.0 + (Math.random() - 0.5) * 1.5;
        const mid = baselinePrice;
        
        // Mock 5 levels of bids and asks
        const bids = [];
        const asks = [];
        for (let i = 0; i < 5; i++) {
            const pStep = 0.5 + i * 0.5;
            const vBid = 1.0 + Math.random() * 7.0;
            const vAsk = 1.0 + Math.random() * 7.0;
            bids.push([(mid - pStep).toString(), vBid.toString()]);
            asks.push([(mid + pStep).toString(), vAsk.toString()]);
        }
        
        return {
            index: index,
            midPrice: mid,
            microPrice: mid + imbalance,
            bids: bids,
            asks: asks
        };
    }

    function init() {
        container = document.getElementById("threejs-canvas-container");
        if (!container) return;
        
        container.innerHTML = "";
        
        canvas = document.createElement("canvas");
        canvas.style.width = "100%";
        canvas.style.height = "100%";
        canvas.style.display = "block";
        canvas.style.backgroundColor = "#000000"; // Pure Black
        container.appendChild(canvas);
        
        ctx = canvas.getContext("2d");
        
        if (window.ResizeObserver) {
            const resizeObserver = new ResizeObserver(() => resize());
            resizeObserver.observe(container);
        } else {
            window.addEventListener("resize", resize);
        }
        resize();
        
        // Pre-populate ticks buffer
        for (let i = 0; i < maxTicks; i++) {
            ticks.push(generateMockTick(lastIndex++));
        }
        
        // Loop
        requestAnimationFrame(tickLoop);
    }
    
    function resize() {
        if (!canvas) return;
        const rect = container.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.scale(dpr, dpr);
    }
    
    function tickLoop() {
        if (!canvas || !ctx) return;
        
        // If no live updates are arriving, slowly drift mock data
        if (ticks.length > 0 && Math.random() < 0.15) {
            ticks.push(generateMockTick(lastIndex++));
            if (ticks.length > maxTicks) {
                ticks.shift();
            }
            
            // Randomly append a new T2T latency entry to keep histogram alive
            t2tHistory.push(15 + Math.random() * 35);
            if (t2tHistory.length > maxLatencies) {
                t2tHistory.shift();
            }
        }
        
        draw();
        drawT2THistogram();
        requestAnimationFrame(tickLoop);
    }

    const paddingLeft = 65;
    const paddingRight = 15;
    const paddingTop = 30;
    const paddingBottom = 30;

    function draw() {
        const width = canvas.width / (window.devicePixelRatio || 1);
        const height = canvas.height / (window.devicePixelRatio || 1);
        
        ctx.clearRect(0, 0, width, height);
        
        // Background
        ctx.fillStyle = "#000000";
        ctx.fillRect(0, 0, width, height);
        
        const chartWidth = width - paddingLeft - paddingRight;
        const chartHeight = height - paddingTop - paddingBottom;
        
        // Calculate Y scale dynamically
        let minPrice = Infinity;
        let maxPrice = -Infinity;
        ticks.forEach(t => {
            minPrice = Math.min(minPrice, t.midPrice, t.microPrice);
            maxPrice = Math.max(maxPrice, t.midPrice, t.microPrice);
        });
        const diff = maxPrice - minPrice;
        minPrice -= diff * 0.15 || 2.0;
        maxPrice += diff * 0.15 || 2.0;

        const getY = (val) => paddingTop + chartHeight - ((val - minPrice) / (maxPrice - minPrice)) * chartHeight;
        const getX = (index) => paddingLeft + ((index - ticks[0].index) / ticks.length) * chartWidth;
        
        // 1. DRAW ORDER BOOK HEATMAP BRUMA IN BACKGROUND
        ticks.forEach((tick, idx) => {
            const x = getX(tick.index);
            const nextX = getX(tick.index + 1);
            const colWidth = Math.max(1, nextX - x);
            
            // Draw Bids (Green hue)
            if (tick.bids) {
                tick.bids.forEach(level => {
                    const p = parseFloat(level[0]);
                    const v = parseFloat(level[1]);
                    const y = getY(p);
                    const opacity = Math.min(v / 8.0, 1.0) * 0.18; // subtle transparent bruma
                    
                    ctx.fillStyle = `rgba(0, 255, 102, ${opacity})`;
                    ctx.fillRect(x, y - 2, colWidth + 0.5, 4);
                });
            }
            
            // Draw Asks (Red hue)
            if (tick.asks) {
                tick.asks.forEach(level => {
                    const p = parseFloat(level[0]);
                    const v = parseFloat(level[1]);
                    const y = getY(p);
                    const opacity = Math.min(v / 8.0, 1.0) * 0.18;
                    
                    ctx.fillStyle = `rgba(255, 51, 51, ${opacity})`;
                    ctx.fillRect(x, y - 2, colWidth + 0.5, 4);
                });
            }
        });

        // 2. DRAW GRID LINES OVER THE HEATMAP
        ctx.strokeStyle = "rgba(26, 26, 26, 0.6)";
        ctx.lineWidth = 1;
        
        // Horizontal grid lines and Y price labels
        ctx.fillStyle = "#666666";
        ctx.font = "9px 'JetBrains Mono', monospace";
        ctx.textAlign = "right";
        ctx.textBaseline = "middle";
        
        const step = (maxPrice - minPrice) / 5;
        for (let i = 0; i <= 5; i++) {
            const price = minPrice + step * i;
            const y = getY(price);
            ctx.beginPath();
            ctx.moveTo(paddingLeft, y);
            ctx.lineTo(width - paddingRight, y);
            ctx.stroke();
            
            ctx.fillText(price.toFixed(2), paddingLeft - 8, y);
        }
        
        // Vertical grid lines
        ctx.beginPath();
        for (let i = 1; i < 6; i++) {
            const x = paddingLeft + (chartWidth / 6) * i;
            ctx.moveTo(x, paddingTop);
            ctx.lineTo(x, height - paddingBottom);
        }
        ctx.stroke();
        
        // 3. PLOT MID-PRICE CURVE (Thin dashed white)
        ctx.strokeStyle = "#555555";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.setLineDash([2, 3]);
        ticks.forEach((tick, i) => {
            const x = getX(tick.index);
            const y = getY(tick.midPrice);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
        ctx.setLineDash([]);
        
        // 4. PLOT MICRO-PRICE CURVE (Solid high-contrast green)
        ctx.strokeStyle = "#00FF66";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ticks.forEach((tick, i) => {
            const x = getX(tick.index);
            const y = getY(tick.microPrice);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
        
        // Draw Outer Frame
        ctx.strokeStyle = "#222222";
        ctx.lineWidth = 1;
        ctx.strokeRect(paddingLeft, paddingTop, chartWidth, chartHeight);
        
        // Axis Title
        ctx.fillStyle = "#888888";
        ctx.font = "9px 'JetBrains Mono', monospace";
        ctx.textAlign = "left";
        ctx.fillText("MICRO-PRICE VS MID-PRICE SPREAD & ORDER BOOK HEATMAP (DEPTH L2)", paddingLeft, 16);
        
        // Legends
        const legendX = width - paddingRight - 360;
        ctx.fillStyle = "#00FF66";
        ctx.fillText("─── Micro-Price", legendX, 16);
        ctx.fillStyle = "#888888";
        ctx.fillText("- - Mid-Price", legendX + 110, 16);
        ctx.fillStyle = "rgba(0, 255, 102, 0.7)";
        ctx.fillText("░░░ Bids Depth", legendX + 200, 16);
        ctx.fillStyle = "rgba(255, 51, 51, 0.7)";
        ctx.fillText("░░░ Asks Depth", legendX + 290, 16);
    }
    
    function drawT2THistogram() {
        const hCanvas = document.getElementById("hft-t2t-histogram");
        if (!hCanvas) return;
        
        const hCtx = hCanvas.getContext("2d");
        const w = hCanvas.clientWidth;
        const h = hCanvas.clientHeight;
        
        hCanvas.width = w * window.devicePixelRatio;
        hCanvas.height = h * window.devicePixelRatio;
        hCtx.scale(window.devicePixelRatio, window.devicePixelRatio);
        
        hCtx.clearRect(0, 0, w, h);
        
        const barWidth = (w / maxLatencies) - 1;
        const maxVal = 60.0; // scale limit for 60ms latency
        
        t2tHistory.forEach((lat, i) => {
            const barHeight = (lat / maxVal) * h * 0.85;
            const x = i * (barWidth + 1);
            const y = h - barHeight;
            
            hCtx.fillStyle = lat > 45 ? "#FF3333" : "#00FF66";
            hCtx.fillRect(x, y, barWidth, barHeight);
        });
    }
    
    // Expose update handler to grab real websocket tick updates
    window.updateHFTChart = function(microPrice, midPrice, price, bids, asks) {
        if (!microPrice || !midPrice) {
            microPrice = price;
            midPrice = price;
        }
        
        baselinePrice = midPrice;
        
        ticks.push({
            index: lastIndex++,
            midPrice: midPrice,
            microPrice: microPrice,
            bids: bids || null,
            asks: asks || null
        });
        
        if (ticks.length > maxTicks) {
            ticks.shift();
        }
    };
    
    // Expose latency update handler to push actual order time values
    window.pushT2TLatency = function(latencyMs) {
        t2tHistory.push(latencyMs);
        if (t2tHistory.length > maxLatencies) {
            t2tHistory.shift();
        }
    };

    // DOM Ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
