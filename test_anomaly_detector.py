import unittest
import time
from anomaly_detector import AnomalyDetector, LogEntry, SlidingWindow, BaselineEstimator

class TestAnomalyDetector(unittest.TestCase):
    def test_log_entry_parser(self):
        line = "[2026-09-28 12:00:00.123] [ERROR] [POST] [/api/v1/checkout] [500] [1200.5ms] - InternalServerError"
        entry = LogEntry.parse(line)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.level, "ERROR")
        self.assertEqual(entry.method, "POST")
        self.assertEqual(entry.endpoint, "/api/v1/checkout")
        self.assertEqual(entry.status_code, 500)
        self.assertEqual(entry.latency_ms, 1200.5)

    def test_sliding_window_metrics(self):
        window = SlidingWindow(window_size_seconds=30.0)
        now = time.time()
        
        # Add 8 normal entries and 2 error entries
        for i in range(8):
            window.add(LogEntry("2026-09-28 12:00:00", "INFO", "GET", "/", 200, 50.0, "OK", "raw", now + i*0.1))
        for i in range(2):
            window.add(LogEntry("2026-09-28 12:00:00", "ERROR", "GET", "/", 500, 500.0, "Err", "raw", now + (8+i)*0.1))

        stats = window.get_stats()
        self.assertEqual(stats["total_count"], 10)
        self.assertEqual(stats["error_count"], 2)
        self.assertEqual(stats["error_rate"], 0.20)

    def test_anomaly_detection_severity(self):
        detector = AnomalyDetector(window_size_sec=30.0, cooldown_sec=0.0)
        now = time.time()

        # Phase 1: Train baseline with 20 normal logs
        for i in range(20):
            entry = LogEntry("2026-09-28 12:00:00", "INFO", "GET", "/healthz", 200, 30.0, "OK", "raw", now + i*0.1)
            metrics, alert = detector.process_entry(entry)

        # Baseline should be very low error rate
        self.assertLess(detector.baseline.mean_error_rate, 0.05)

        # Phase 2: Inject error burst (15 error logs)
        alerts_generated = []
        for i in range(15):
            entry = LogEntry("2026-09-28 12:00:00", "ERROR", "POST", "/pay", 500, 1500.0, "Crash", "raw", now + 20 + i*0.1)
            metrics, alert = detector.process_entry(entry)
            if alert:
                alerts_generated.append(alert)

        self.assertGreater(len(alerts_generated), 0)
        latest_alert = alerts_generated[-1]
        self.assertIn(latest_alert.severity, ["MEDIUM", "HIGH", "CRITICAL"])
        self.assertGreaterEqual(latest_alert.z_score, 2.5)

if __name__ == "__main__":
    unittest.main()
