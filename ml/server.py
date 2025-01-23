import time
import requests
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
    return [hit["_source"] for hit in response["hits"]["hits"]]

# Preprocess logs
def preprocess_logs(logs):
    dataset = pd.DataFrame(logs)
    if dataset.empty:
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

    return dataset

# Aggregate logs
def aggregate_logs(dataset, window):
    dataset = dataset.set_index("timestamp")
    agg_data = dataset.rolling(f"{window}s").sum()
    agg_data["num_request_1s"] = dataset.rolling(f"{window}s").size()
    return agg_data.reset_index()

# Predict malicious IPs
def predict_malicious_ips(dataset, raw_logs):
    predictions = model.predict(dataset)
    mapping = {0: 0, 1: 1, 2: 0, 3: 1, 4: 1, 5: 0, 6: 0, 7: 0}
    malicious = [raw_logs[i]["src_ip"] for i, pred in enumerate(predictions) if mapping[pred] == 1]

    # Save malicious IPs
    for ip in malicious:
        malicious_ips.add(ip)
        # Store in Elasticsearch
        es.index(index="malicious-ips", body={"ip": ip, "timestamp": datetime.utcnow().isoformat()})

# Periodic processing
def process_logs():
    while True:
        logs_1s = fetch_logs(1)
        logs_3s = fetch_logs(3)

        if logs_1s:
            dataset_1s = preprocess_logs(logs_1s)
            if dataset_1s is not None:
                predict_malicious_ips(dataset_1s, logs_1s)

        if logs_3s:
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