# -*- coding: utf-8 -*-
"""Functions that interact with the database."""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from .database import write_api, INFLUXDB_BUCKET, INFLUXDB_ORG
from influxdb_client import Point
from influxdb_client import QueryApi
import influxdb_client

logger = logging.getLogger(__name__)


async def create_log(exchange, routing_key, data, log_level="INFO"):
    """Write a log to InfluxDB."""
    try:
        point = Point("log") \
            .tag("exchange", exchange) \
            .tag("routing_key", routing_key) \
            .tag("log_level", log_level) \
            .field("message", data) \
            .time(datetime.utcnow().isoformat())
        write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    except Exception as e:
        raise Exception(f"Error writing log to InfluxDB: {e}")


async def get_logs(limit=10):
    """Query logs from InfluxDB."""
    query_api = influxdb_client.query_api()
    query = f"""
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -1d)  # Adjust range as needed
      |> filter(fn: (r) => r._measurement == "log")
      |> sort(columns: ["_time"], desc: true)
      |> limit(n: {limit})
    """
    try:
        result = query_api.query(org=INFLUXDB_ORG, query=query)
        logs = []
        for table in result:
            for record in table.records:
                logs.append({
                    "time": record.get_time(),
                    "exchange": record.values.get("exchange"),
                    "routing_key": record.values.get("routing_key"),
                    "log_level": record.values.get("log_level"),
                    "message": record.get_value(),
                })
        return logs
    except Exception as e:
        raise Exception(f"Error querying logs from InfluxDB: {e}")