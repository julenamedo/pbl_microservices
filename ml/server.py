import time
import logging
import pandas as pd
import pickle
from sklearn.preprocessing import StandardScaler, LabelEncoder
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch
from fastapi import FastAPI
import joblib

# Initialize Elasticsearch and FastAPI
es = Elasticsearch(["http://localhost:9200"], http_auth=("elastic", "admin"))
app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Load pre-trained models and encoders
with open('models/path_encoder.pkl', 'rb') as file:
    path_encoder = pickle.load(file)

with open('models/one_hot_columns.pkl', 'rb') as file:
    one_hot_columns = pickle.load(file)

model_path = 'models/model.joblib'
model = joblib.load(model_path)

scaler = StandardScaler()

# In-memory storage for malicious IPs
malicious_ips = set()

# File to log results
log_file = "analysis_results.log"

# Fetch logs from Elasticsearch
def fetch_logs(last_seconds):
    now = datetime.utcnow()
    start_time = now - timedelta(seconds=last_seconds)
    query = {
        "query": {
            "range": {
                "timestamp": {
                    "gte": start_time.isoformat(),
                    "lt": now.isoformat(),
                }
            }
        }
    }
    response = es.search(index="haproxy-logs-*", body=query, size=10000)
    logs = [hit["_source"] for hit in response["hits"]["hits"]]
    logger.info(f"Fetched {len(logs)} logs from Elasticsearch for the last {last_seconds} seconds")
    return logs

# Preprocess logs
def preprocess_logs(logs):
    dataset = pd.DataFrame(logs)
    if dataset.empty:
        logger.info("No logs to process.")
        return None

    # Drop unnecessary columns
    dataset = dataset.drop(columns=["response_header", "src_ip", "dst_ip"], errors="ignore")
    dataset["timestamp"] = pd.to_datetime(dataset["timestamp"])

    # Encode and normalize
    dataset["path"] = path_encoder.transform(dataset["path"])
    dataset = pd.get_dummies(dataset, columns=["protocol", "request_method", "status_code"], drop_first=True)
    for col in one_hot_columns:
        if col not in dataset.columns:
            dataset[col] = 0  # Add missing columns
    dataset = dataset[one_hot_columns]  # Ensure column order matches

    logger.info("Logs preprocessed successfully.")
    return dataset

# Predict malicious IPs
def predict_malicious_ips(dataset, raw_logs):
    predictions = model.predict(dataset)
    mapping = {0: "benign", 1: "malicious", 2: "benign", 3: "malicious", 4: "malicious", 5: "benign", 6: "benign", 7: "benign"}

    with open(log_file, "a") as log:
        for i, pred in enumerate(predictions):
            result = mapping[pred]
            log_entry = f"Analysing packet from src_ip={raw_logs[i]['src_ip']}: {result}"
            logger.info(log_entry)  # Logs to console
            log.write(f"{datetime.utcnow().isoformat()} - {log_entry}\n")  # Logs to file

            if result == "malicious":
                malicious_ips.add(raw_logs[i]["src_ip"])
                es.index(index="malicious-ips", body={"ip": raw_logs[i]["src_ip"], "timestamp": datetime.utcnow().isoformat()})

# Periodic processing
def process_logs():
    while True:
        logs_1s = fetch_logs(1)
        logs_3s = fetch_logs(3)

        if logs_1s:
            logger.info(f"Processing {len(logs_1s)} logs for 1s window")
            dataset_1s = preprocess_logs(logs_1s)
            if dataset_1s is not None:
                predict_malicious_ips(dataset_1s, logs_1s)

        if logs_3s:
            logger.info(f"Processing {len(logs_3s)} logs for 3s window")
            dataset_3s = preprocess_logs(logs_3s)
            if dataset_3s is not None:
                predict_malicious_ips(dataset_3s, logs_3s)

        time.sleep(1)

# API endpoint to retrieve malicious IPs
@app.get("/ip")
def get_malicious_ips():
    return {"malicious_ips": list(malicious_ips)}

# Run the log processing in the background
import threading
threading.Thread(target=process_logs, daemon=True).start()
