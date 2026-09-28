// WebSocket & Dashboard Application Logic
let socket = null;
let metricsChart = null;
let alertCount = 0;
let rawLogEntries = [];

const MAX_CHART_POINTS = 30;
const chartData = {
    labels: [],
    errorRates: [],
    baselineRates: []
};

document.addEventListener("DOMContentLoaded", () => {
    initChart();
    connectWebSocket();
    fetchStatus();
});

// Initialize Chart.js Trend Graph
function initChart() {
    const ctx = document.getElementById('metricsChart').getContext('2d');
    metricsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: 'Rolling Error Rate (%)',
                    data: chartData.errorRates,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.15)',
                    fill: true,
                    tension: 0.3,
                    borderWidth: 2,
                    pointRadius: 2
                },
                {
                    label: 'Dynamic Baseline (%)',
                    data: chartData.baselineRates,
                    borderColor: '#3b82f6',
                    borderDash: [5, 5],
                    fill: false,
                    tension: 0.3,
                    borderWidth: 2,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#9ca3af', font: { size: 10 } }
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: {
                        color: '#9ca3af',
                        font: { size: 10 },
                        callback: function(val) { return val + '%'; }
                    }
                }
            },
            plugins: {
                legend: {
                    labels: { color: '#f3f4f6', font: { size: 12 } }
                }
            }
        }
    });
}

// Connect WebSocket
function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        document.getElementById('wsStatusText').innerText = "WebSocket: Active";
        document.getElementById('wsStatus').style.borderColor = "rgba(16, 185, 129, 0.4)";
    };

    socket.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === "log_entry") {
                handleLogEntry(msg.data);
            } else if (msg.type === "metrics") {
                handleMetricsUpdate(msg.data);
            } else if (msg.type === "alert") {
                handleAlert(msg.data);
            }
        } catch (e) {
            console.error("Failed to parse WebSocket message:", e);
        }
    };

    socket.onclose = () => {
        document.getElementById('wsStatusText').innerText = "WebSocket: Disconnected (Reconnecting...)";
        document.getElementById('wsStatus').style.borderColor = "rgba(239, 68, 68, 0.4)";
        setTimeout(connectWebSocket, 3000);
    };

    socket.onerror = (err) => {
        console.error("WebSocket error:", err);
    };
}

// Update KPI cards and Chart
function handleMetricsUpdate(data) {
    document.getElementById('kpiErrorRate').innerText = `${data.error_rate_pct}%`;
    document.getElementById('kpiBaselineRate').innerText = `${data.baseline_error_rate_pct}%`;
    
    // Highlight Z-Score if anomalous
    const zElem = document.getElementById('kpiZScore');
    zElem.innerText = data.z_score;
    if (data.z_score >= 5.0) {
        zElem.style.color = "#ec4899";
    } else if (data.z_score >= 2.5) {
        zElem.style.color = "#f59e0b";
    } else {
        zElem.style.color = "#f3f4f6";
    }

    document.getElementById('kpiLatency').innerText = `${data.avg_latency_ms} ms`;
    document.getElementById('kpiBaselineLatency').innerText = `${data.baseline_latency_ms} ms`;
    document.getElementById('kpiTotalLogs').innerText = data.total_logs;
    document.getElementById('kpiThroughput').innerText = `${data.throughput_per_sec}/s`;

    // Push into chart data
    chartData.labels.push(data.timestamp);
    chartData.errorRates.push(data.error_rate_pct);
    chartData.baselineRates.push(data.baseline_error_rate_pct);

    if (chartData.labels.length > MAX_CHART_POINTS) {
        chartData.labels.shift();
        chartData.errorRates.shift();
        chartData.baselineRates.shift();
    }

    metricsChart.update('none');
}

// Append log entry to console
function handleLogEntry(log) {
    rawLogEntries.push(log);
    if (rawLogEntries.length > 200) rawLogEntries.shift();

    renderConsoleLogs();
}

function renderConsoleLogs() {
    const consoleBody = document.getElementById('logConsole');
    const filter = document.getElementById('logLevelFilter').value;

    const filtered = rawLogEntries.filter(log => filter === "ALL" || log.level === filter);

    if (filtered.length === 0) {
        consoleBody.innerHTML = '<div class="console-placeholder">No logs matching filter.</div>';
        return;
    }

    let html = "";
    filtered.slice(-80).forEach(log => {
        html += `
            <div class="log-row">
                <span class="log-time">[${log.timestamp.split(' ')[1] || log.timestamp}]</span>
                <span class="log-level level-${log.level}">[${log.level}]</span>
                <span class="log-msg">${log.method} ${log.endpoint} - ${log.status_code} (${log.latency_ms}ms) - ${escapeHtml(log.message)}</span>
            </div>
        `;
    });

    consoleBody.innerHTML = html;
    consoleBody.scrollTop = consoleBody.scrollHeight;
}

function filterLogs() {
    renderConsoleLogs();
}

function clearLogs() {
    rawLogEntries = [];
    renderConsoleLogs();
}

// Render generated anomaly alert card
function handleAlert(alert) {
    alertCount++;
    document.getElementById('alertCounterBadge').innerText = `${alertCount} Alerts`;

    const feedList = document.getElementById('alertFeedList');
    const emptyPlaceholder = feedList.querySelector('.empty-alerts');
    if (emptyPlaceholder) {
        emptyPlaceholder.remove();
    }

    const card = document.createElement('div');
    card.className = `alert-card severity-${alert.severity}`;

    card.innerHTML = `
        <div class="alert-top">
            <span class="alert-sev-tag sev-${alert.severity}">${alert.severity} ANOMALY</span>
            <span class="alert-time">${alert.timestamp}</span>
        </div>
        <div class="alert-title">${escapeHtml(alert.title)}</div>
        <div class="alert-desc">${escapeHtml(alert.description)}</div>
        <div class="alert-metrics">
            <span>Z-Score: <strong>${alert.z_score}</strong></span>
            <span>Error Rate: <strong>${(alert.current_error_rate * 100).toFixed(1)}%</strong></span>
            <span>Errors: <strong>${alert.error_logs_in_window}/${alert.total_logs_in_window}</strong></span>
        </div>
        <div class="aws-tag">
            <i class="fa-brands fa-aws"></i>
            <span>Pushed to AWS CloudWatch & SNS (${alert.aws_pushed ? 'Success' : 'Mock Mode'})</span>
        </div>
    `;

    feedList.prepend(card);
}

// Simulation Control Trigger
async function triggerSimulation(mode) {
    try {
        const res = await fetch('/api/simulation/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode, duration_sec: 15 })
        });
        const data = await res.json();
        console.log("Simulation triggered:", data);
    } catch (e) {
        console.error("Failed to set simulation mode:", e);
    }
}

async function triggerECGSimulation() {
    try {
        const res = await fetch('/api/simulation/ecg', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'ecg', duration_sec: 30 })
        });
        const data = await res.json();
        console.log("ECG Simulation triggered:", data);
    } catch (e) {
        console.error("Failed to trigger ECG simulation:", e);
    }
}

// Fetch Initial Status
async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.aws_notifier) {
            document.getElementById('awsStatusText').innerText = `AWS CloudWatch/SNS: ${data.aws_notifier.mode}`;
        }
    } catch (e) {
        console.error("Failed to fetch status:", e);
    }
}

function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
