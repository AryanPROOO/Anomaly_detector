import os
import time
import glob
import random
import pandas as pd
from datetime import datetime

LOG_FILE = "app.log"

CLASS_MAP = {
    0: ("INFO", 200, "Normal Sinus Rhythm (N)"),
    1: ("WARN", 400, "Supraventricular Premature Beat (S)"),
    2: ("ERROR", 500, "Premature Ventricular Contraction - PVC (V)"),
    3: ("ERROR", 502, "Fusion Heartbeat Signal (F)"),
    4: ("CRITICAL", 503, "CRITICAL: Ventricular Fibrillation / Acute Ischemic Event (Q)")
}

def find_dataset():
    cache_path = r"C:\Users\HP\.cache\kagglehub\datasets\shayanfazeli\heartbeat"
    csv_files = glob.glob(os.path.join(cache_path, "**", "mitbih_test.csv"), recursive=True)
    if not csv_files:
        csv_files = glob.glob(os.path.join(cache_path, "**", "*.csv"), recursive=True)
    if csv_files:
        return csv_files[0]
    return None

class ECGStreamReplayer:
    def __init__(self, log_filepath=LOG_FILE):
        self.log_filepath = log_filepath
        self.running = False
        self.dataset_path = None

    def load_data(self):
        self.dataset_path = find_dataset()
        if not self.dataset_path:
            raise FileNotFoundError("Kaggle ECG dataset (mitbih_test.csv) not found yet.")
        print(f"[ECGStreamReplayer] Loading Kaggle ECG dataset from: {self.dataset_path}")
        self.df = pd.read_csv(self.dataset_path, header=None)
        # Separate normal beats and arrhythmia beats for controlled streaming
        self.normal_beats = self.df[self.df.iloc[:, 187] == 0]
        self.arrhythmia_beats = self.df[self.df.iloc[:, 187] > 0]
        print(f"[ECGStreamReplayer] Loaded {len(self.df)} total ECG heartbeats ({len(self.normal_beats)} normal, {len(self.arrhythmia_beats)} arrhythmia).")

    def generate_log_line(self, mode="normal"):
        if mode == "normal" or self.arrhythmia_beats.empty:
            row = self.normal_beats.sample(n=1).iloc[0]
        else:
            row = self.arrhythmia_beats.sample(n=1).iloc[0]

        signal_lead = row.iloc[:187].values
        label = int(row.iloc[187])

        level, status, description = CLASS_MAP.get(label, ("INFO", 200, "Unknown Pattern"))
        
        # Calculate amplitude variance & latency metric
        amplitude_mean = float(signal_lead.mean()) * 1000
        latency_ms = round(max(abs(amplitude_mean), 20.0), 2)
        
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{now_str}] [{level}] [ECG_MONITOR] [/patient/ecg_lead_1] [{status}] [{latency_ms}ms] - Patient Heartbeat Event: {description} (Class {label})\n"
        return line

    def stream(self, duration_sec=60, delay_sec=0.2):
        self.load_data()
        self.running = True
        end_time = time.time() + duration_sec
        with open(self.log_filepath, "a", encoding="utf-8") as f:
            while time.time() < end_time and self.running:
                # 85% normal, 15% cardiac anomaly
                mode = "anomaly" if random.random() < 0.15 else "normal"
                line = self.generate_log_line(mode=mode)
                f.write(line)
                f.flush()
                time.sleep(delay_sec)
        self.running = False

    def stop(self):
        """Gracefully stop the ECG stream."""
        self.running = False

if __name__ == "__main__":
    replayer = ECGStreamReplayer()
    try:
        replayer.stream(duration_sec=30)
    except Exception as e:
        print("Error streaming ECG dataset:", e)
