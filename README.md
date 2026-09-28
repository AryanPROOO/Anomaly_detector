# Real-Time Log Anomaly Detector

A FastAPI-based real-time system that monitors application logs, detects anomalies (error spikes, latency spikes, critical outages), and sends alerts to AWS SNS.

---

## Features

- **Real-time log monitoring** — Tails log files and processes entries as they arrive
- **Anomaly detection** — Uses statistical analysis (z-score) to detect:
  - Error rate spikes
  - Latency spikes
  - Critical outages
- **WebSocket live updates** — Frontend receives logs, metrics, and alerts in real-time
- **AWS SNS integration** — Pushes alerts to AWS for notifications
- **Simulation modes** — Test with normal, error spike, latency spike, or critical outage scenarios
- **ECG data replay** — Replays Kaggle MIT-BIH heartbeat dataset for demo purposes

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure AWS (optional)
Create `.env` file or set environment variables:
```env
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
SNS_TOPIC_ARN=arn:aws:sns:region:account:topic-name
```

### 3. Run the server
```bash
python server.py
```

### 4. Open the dashboard
Visit: **http://localhost:8000**

---

## Project Structure

```
anomaly_detection/
├── server.py              # FastAPI app + WebSocket server
├── anomaly_detector.py    # Log parsing & statistical anomaly detection
├── ecg_stream_replayer.py # Kaggle ECG dataset replayer
├── aws_notifier.py        # AWS SNS alert publisher
├── requirements.txt       # Python dependencies
├── static/
│   ├── index.html         # Dashboard UI
│   ├── app.js             # Frontend logic (WebSocket + charts)
│   └── style.css          # Styling
├── test_anomaly_detector.py
└── app.log                # Sample log file (auto-generated)
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Dashboard UI |
| `GET` | `/api/status` | System status & baselines |
| `GET` | `/api/alerts` | Recent alert history |
| `POST` | `/api/simulation/mode` | Set log simulation mode |
| `POST` | `/api/simulation/ecg` | Trigger ECG data replay |
| `WS` | `/ws` | WebSocket for live updates |

### Simulation Modes
```json
POST /api/simulation/mode
{ "mode": "normal" }           // Normal operation
{ "mode": "error_spike" }      // Sudden error increase
{ "mode": "latency_spike" }    // High latency spike
{ "mode": "critical_outage" }  // Simulated outage
```

---

## How It Works

1. **Log Ingestion** — Server tails `app.log` continuously
2. **Parsing** — Each line parsed into structured `LogEntry` (timestamp, level, method, endpoint, status, latency)
3. **Detection** — Sliding window (30s) tracks error rate & latency; z-score > 2.5 triggers alert
4. **Alerting** — Alerts broadcast via WebSocket + pushed to AWS SNS
5. **Visualization** — Frontend shows live logs, metrics charts, and alert feed

---

## Requirements

- Python 3.9+
- FastAPI, Uvicorn, WebSockets
- boto3 (for AWS SNS)
- Internet access (for Kaggle ECG dataset download on first run)

---

## License

MIT License