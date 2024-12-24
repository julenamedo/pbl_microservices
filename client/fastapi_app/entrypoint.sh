#!/bin/bash

echo "Service: ${SERVICE_NAME}"
IP=$(hostname -i)
export IP
echo "IP: ${IP}"

# Inicialización de la base de datos SQLite
echo "Initializing SQLite database..."
sqlite3 /volume/monolithic.db < /volume/init_db.sql

# Function to handle termination signals
terminate() {
  echo "Termination signal received, shutting down..."
  kill -SIGTERM "$UVICORN_PID"
  wait "$UVICORN_PID"
  echo "Uvicorn has been terminated"
}

# Trap signals
trap terminate SIGTERM SIGINT

# Lanzar Uvicorn
echo "Starting Uvicorn server..."
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --ssl-keyfile /keys/priv.pem \
  --ssl-certfile /keys/cert.pem &

# Capturar el PID del proceso Uvicorn
UVICORN_PID=$!

# Esperar que termine el proceso de Uvicorn
wait "$UVICORN_PID"