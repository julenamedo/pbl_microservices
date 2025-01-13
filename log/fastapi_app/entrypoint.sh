#!/bin/bash

echo "Service: ${SERVICE_NAME:-log-service}"
IP=$(hostname -i)
export IP
echo "IP: ${IP}"

# Function to handle termination signals
terminate() {
    echo "Termination signal received, shutting down..."
    kill -SIGTERM "$UVICORN_PID"
    wait "$UVICORN_PID"
    echo "Uvicorn has been terminated"
}

# Trap signals
trap terminate SIGTERM SIGINT

# Check for SSL certificate and key files
if [[ ! -f /keys/priv.pem || ! -f /keys/cert.pem ]]; then
    echo "SSL certificate or key file not found. Exiting."
    exit 1
fi

# Start Uvicorn server with SSL
echo "Starting Uvicorn server with SSL..."
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port ${UVICORN_PORT} \
  --reload \
  --ssl-keyfile /keys/priv.pem \
  --ssl-certfile /keys/cert.pem &

# Capture the PID of the Uvicorn process
UVICORN_PID=$!

# Wait for Uvicorn to terminate
wait "$UVICORN_PID"
