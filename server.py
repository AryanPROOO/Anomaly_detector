import os
import asyncio
import json
import logging
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from ecg_stream_replayer import ECGStreamReplayer
from anomaly_detector import AnomalyDetector, LogEntry, Alert
from aws_notifier import AWSNotifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Server")

app = FastAPI(title="Real-Time Log Anomaly Detector")

# Global Services
LOG_FILE = "app.log"
ecg_replayer = ECGStreamReplayer(log_filepath=LOG_FILE)
anomaly_detector = AnomalyDetector(window_size_sec=30.0, cooldown_sec=4.0)
aws_notifier = AWSNotifier()

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        to_remove = []
        payload = json.dumps(message)
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                to_remove.append(connection)
        for conn in to_remove:
            self.disconnect(conn)

manager = ConnectionManager()
alert_history: List[Dict[str, Any]] = []

# Background Log Tailing Task
async def tail_log_file():
    logger.info(f"Starting async tailer for {LOG_FILE}...")
    # Ensure log file exists
    if not os.path.exists(LOG_FILE):
        open(LOG_FILE, "w").close()

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        # Seek to end of file
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if line:
                entry = LogEntry.parse(line)
                if entry:
                    # Process entry in anomaly detector
                    metrics, alert = anomaly_detector.process_entry(entry)

                    # Broadcast log line
                    await manager.broadcast({
                        "type": "log_entry",
                        "data": {
                            "timestamp": entry.timestamp,
                            "level": entry.level,
                            "method": entry.method,
                            "endpoint": entry.endpoint,
                            "status_code": entry.status_code,
                            "latency_ms": entry.latency_ms,
                            "message": entry.message,
                            "raw_line": entry.raw_line
                        }
                    })

                    # Broadcast metrics update
                    await manager.broadcast({
                        "type": "metrics",
                        "data": metrics
                    })

                    # Handle alert if generated
                    if alert:
                        alert_dict = alert.__dict__
                        # Push to AWS
                        pushed = aws_notifier.push_alert(alert_dict)
                        alert_dict["aws_pushed"] = pushed
                        alert_history.insert(0, alert_dict)
                        if len(alert_history) > 100:
                            alert_history.pop()

                        await manager.broadcast({
                            "type": "alert",
                            "data": alert_dict
                        })
            else:
                await asyncio.sleep(0.1)

@app.on_event("startup")
async def startup_event():
    # Auto-start Kaggle ECG stream on server launch (continuous loop)
    import threading
    thread = threading.Thread(target=ecg_replayer.stream, kwargs={"duration_sec": 999999}, daemon=True)
    thread.start()
    logger.info("Kaggle ECG stream auto-started on server launch")
    # Start log tailing task
    asyncio.create_task(tail_log_file())

@app.on_event("shutdown")
def shutdown_event():
    ecg_replayer.stop()

# REST APIs
class SimulationRequest(BaseModel):
    mode: str
    duration_sec: int = 15

@app.post("/api/simulation/mode")
def set_simulation_mode(req: SimulationRequest):
    valid_modes = ["normal", "error_spike", "latency_spike", "critical_outage"]
    if req.mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of {valid_modes}")
    
    log_generator.set_mode(req.mode, req.duration_sec)
    return {"status": "success", "mode": req.mode, "duration_sec": req.duration_sec}

@app.post("/api/simulation/ecg")
def trigger_ecg_simulation(req: SimulationRequest):
    try:
        from ecg_stream_replayer import ECGStreamReplayer
        replayer = ECGStreamReplayer()
        import threading
        thread = threading.Thread(target=replayer.stream, kwargs={"duration_sec": req.duration_sec}, daemon=True)
        thread.start()
        return {"status": "success", "message": f"Started Kaggle ECG stream for {req.duration_sec}s"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status")
def get_status():
    return {
        "ecg_stream_running": ecg_replayer.running,
        "data_source": "Kaggle MIT-BIH ECG Heartbeat Dataset",
        "aws_notifier": aws_notifier.status_summary(),
        "baseline": {
            "mean_error_rate_pct": round(anomaly_detector.baseline.mean_error_rate * 100, 2),
            "std_error_rate": round(anomaly_detector.baseline.std_error_rate, 4),
            "mean_latency_ms": round(anomaly_detector.baseline.mean_latency, 2)
        }
    }

@app.get("/api/alerts")
def get_alerts():
    return {"alerts": alert_history}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep socket alive and receive client control messages if any
            data = await websocket.receive_text()
            # Handle client commands if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Serve Static Files
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")
