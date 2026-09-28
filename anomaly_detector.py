import re
import math
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

# Pattern matching for standard log format:
# [2026-09-28 12:00:00.123] [INFO] [GET] [/api/v1/users] [200] [45.2ms] - Log message
LOG_REGEX = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\]\s+\[(?P<level>[^\]]+)\]\s+\[(?P<method>[^\]]+)\]\s+\[(?P<endpoint>[^\]]+)\]\s+\[(?P<status>\d+)\]\s+\[(?P<latency>[\d\.]+)ms\]\s+-\s+(?P<message>.*)$"
)

@dataclass
class LogEntry:
    timestamp: str
    level: str
    method: str
    endpoint: str
    status_code: int
    latency_ms: float
    message: str
    raw_line: str
    time_epoch: float = field(default_factory=time.time)

    @classmethod
    def parse(cls, line: str) -> Optional['LogEntry']:
        line_clean = line.strip()
        match = LOG_REGEX.match(line_clean)
        if match:
            gd = match.groupdict()
            try:
                # Try parsing timestamp to epoch
                dt = datetime.strptime(gd['timestamp'], "%Y-%m-%d %H:%M:%S.%f")
                epoch = dt.timestamp()
            except Exception:
                epoch = time.time()

            return cls(
                timestamp=gd['timestamp'],
                level=gd['level'].upper(),
                method=gd['method'],
                endpoint=gd['endpoint'],
                status_code=int(gd['status']),
                latency_ms=float(gd['latency']),
                message=gd['message'],
                raw_line=line_clean,
                time_epoch=epoch
            )
        else:
            # Fallback simple parser for generic log format
            level = "INFO"
            if "ERROR" in line_clean.upper():
                level = "ERROR"
            elif "WARN" in line_clean.upper():
                level = "WARN"
            elif "CRITICAL" in line_clean.upper() or "FATAL" in line_clean.upper():
                level = "CRITICAL"

            return cls(
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                level=level,
                method="RAW",
                endpoint="/",
                status_code=500 if level in ["ERROR", "CRITICAL"] else 200,
                latency_ms=0.0,
                message=line_clean,
                raw_line=line_clean,
                time_epoch=time.time()
            )

@dataclass
class Alert:
    id: str
    timestamp: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    title: str
    description: str
    z_score: float
    current_error_rate: float
    baseline_error_rate: float
    avg_latency_ms: float
    total_logs_in_window: int
    error_logs_in_window: int
    log_sample: str
    aws_pushed: bool = False

class SlidingWindow:
    def __init__(self, window_size_seconds: float = 30.0):
        self.window_size_seconds = window_size_seconds
        self.entries: deque[LogEntry] = deque()

    def add(self, entry: LogEntry):
        self.entries.append(entry)
        self.cleanup(entry.time_epoch)

    def cleanup(self, current_epoch: float):
        cutoff = current_epoch - self.window_size_seconds
        while self.entries and self.entries[0].time_epoch < cutoff:
            self.entries.popleft()

    def get_stats(self) -> Dict[str, Any]:
        if not self.entries:
            return {
                "total_count": 0,
                "error_count": 0,
                "error_rate": 0.0,
                "avg_latency_ms": 0.0,
                "throughput_per_sec": 0.0
            }

        total = len(self.entries)
        errors = sum(
            1 for e in self.entries 
            if e.level in ["ERROR", "CRITICAL"] or e.status_code >= 500
        )
        total_latency = sum(e.latency_ms for e in self.entries)

        # Time span
        time_span = max(self.entries[-1].time_epoch - self.entries[0].time_epoch, 1.0)

        return {
            "total_count": total,
            "error_count": errors,
            "error_rate": round(errors / total, 4) if total > 0 else 0.0,
            "avg_latency_ms": round(total_latency / total, 2) if total > 0 else 0.0,
            "throughput_per_sec": round(total / time_span, 2)
        }

class BaselineEstimator:
    """
    Establishes and dynamically updates normal behavior baseline using
    Exponentially Weighted Moving Average (EWMA) & Exponential Variance.
    """
    def __init__(self, alpha: float = 0.05, initial_mean: float = 0.03, initial_std: float = 0.02):
        self.alpha = alpha  # Smoothing factor (0 < alpha <= 1)
        self.mean_error_rate = initial_mean
        self.var_error_rate = initial_std ** 2
        self.mean_latency = 50.0
        self.var_latency = 20.0 ** 2
        self.sample_count = 0

    def update(self, current_error_rate: float, current_latency: float):
        self.sample_count += 1
        
        # During initial warm-up period (first 10 samples), use simple average for stability
        if self.sample_count <= 10:
            diff_err = current_error_rate - self.mean_error_rate
            self.mean_error_rate += diff_err / self.sample_count
            self.var_error_rate += diff_err * (current_error_rate - self.mean_error_rate)
            
            diff_lat = current_latency - self.mean_latency
            self.mean_latency += diff_lat / self.sample_count
            self.var_latency += diff_lat * (current_latency - self.mean_latency)
        else:
            # EWMA update for baseline drift resilience
            diff_err = current_error_rate - self.mean_error_rate
            self.mean_error_rate += self.alpha * diff_err
            self.var_error_rate = (1 - self.alpha) * (self.var_error_rate + self.alpha * (diff_err ** 2))

            diff_lat = current_latency - self.mean_latency
            self.mean_latency += self.alpha * diff_lat
            self.var_latency = (1 - self.alpha) * (self.var_latency + self.alpha * (diff_lat ** 2))

    @property
    def std_error_rate(self) -> float:
        return max(math.sqrt(max(self.var_error_rate, 0.0)), 0.01)

    @property
    def std_latency(self) -> float:
        return max(math.sqrt(max(self.var_latency, 0.0)), 1.0)

class AnomalyDetector:
    def __init__(self, window_size_sec: float = 30.0, cooldown_sec: float = 5.0):
        self.window = SlidingWindow(window_size_seconds=window_size_sec)
        self.baseline = BaselineEstimator()
        self.cooldown_sec = cooldown_sec
        self.last_alert_time = 0.0
        self.alert_counter = 0

    def process_entry(self, entry: LogEntry) -> tuple[Dict[str, Any], Optional[Alert]]:
        self.window.add(entry)
        stats = self.window.get_stats()

        error_rate = stats["error_rate"]
        avg_latency = stats["avg_latency_ms"]
        total_logs = stats["total_count"]
        error_logs = stats["error_count"]

        # Only update baseline when in normal non-spike state or warm-up
        # If current error rate is abnormally high, do not poison normal baseline
        z_score_err = (error_rate - self.baseline.mean_error_rate) / self.baseline.std_error_rate

        if z_score_err < 3.0:
            self.baseline.update(error_rate, avg_latency)

        # Detect anomaly
        alert = None
        now = time.time()

        # Alert evaluation conditions:
        # 1. Total logs in window >= 5 (sufficient sample size)
        # 2. Z-Score > 2.5 OR Error Rate > 20% OR CRITICAL level log line
        is_anomaly = False
        severity = "INFO"

        if total_logs >= 5:
            if entry.level == "CRITICAL" or error_rate >= 0.70 or z_score_err >= 8.0:
                is_anomaly = True
                severity = "CRITICAL"
            elif error_rate >= 0.40 or z_score_err >= 5.0:
                is_anomaly = True
                severity = "HIGH"
            elif error_rate >= 0.20 or z_score_err >= 3.5:
                is_anomaly = True
                severity = "MEDIUM"
            elif error_rate >= 0.10 or z_score_err >= 2.5:
                is_anomaly = True
                severity = "LOW"

        # Cooldown check for emitting alerts
        if is_anomaly and (now - self.last_alert_time >= self.cooldown_sec or severity == "CRITICAL"):
            self.last_alert_time = now
            self.alert_counter += 1
            alert_id = f"ALT-{int(now)}-{self.alert_counter:04d}"

            title_map = {
                "LOW": "Minor Error Rate / Latency Deviation Detected",
                "MEDIUM": "Elevated Error Rate Spike",
                "HIGH": "High Error Frequency Anomaly Alert",
                "CRITICAL": "CRITICAL System Failure / Cascade Crash Detected!"
            }

            desc = (
                f"Sliding Window ({self.window.window_size_seconds}s) error rate reached "
                f"{error_rate*100:.1f}% (Baseline: {self.baseline.mean_error_rate*100:.1f}%, "
                f"Z-Score: {z_score_err:.2f}). {error_logs}/{total_logs} errors in window."
            )

            alert = Alert(
                id=alert_id,
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                severity=severity,
                title=title_map[severity],
                description=desc,
                z_score=round(z_score_err, 2),
                current_error_rate=error_rate,
                baseline_error_rate=round(self.baseline.mean_error_rate, 4),
                avg_latency_ms=avg_latency,
                total_logs_in_window=total_logs,
                error_logs_in_window=error_logs,
                log_sample=entry.raw_line
            )

        # Return latest metrics dictionary along with optional Alert object
        metrics = {
            "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
            "total_logs": total_logs,
            "error_logs": error_logs,
            "error_rate": error_rate,
            "error_rate_pct": round(error_rate * 100, 2),
            "baseline_error_rate": round(self.baseline.mean_error_rate, 4),
            "baseline_error_rate_pct": round(self.baseline.mean_error_rate * 100, 2),
            "z_score": round(z_score_err, 2),
            "avg_latency_ms": avg_latency,
            "baseline_latency_ms": round(self.baseline.mean_latency, 2),
            "throughput_per_sec": stats["throughput_per_sec"]
        }

        return metrics, alert
