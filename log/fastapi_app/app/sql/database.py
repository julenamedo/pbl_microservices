# -*- coding: utf-8 -*-
"""Database session configuration."""
import os
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import ssl
from ssl import CERT_NONE
from influxdb_client import InfluxDBClient, Point, WritePrecision, WriteOptions
import ssl
from ssl import CERT_NONE
from influxdb_client import InfluxDBClient, Point, WritePrecision, WriteOptions

ssl_context = ssl.create_default_context(cafile="/keys/ca_cert.pem")
ssl_context.check_hostname = False
ssl_context.verify_mode = CERT_NONE

INFLUXDB_URL = "https://influxdb:8086"
INFLUXDB_TOKEN = "your-influxdb-token"
INFLUXDB_ORG = "your-org"
INFLUXDB_BUCKET = "your-bucket"
INFLUXDB_USERNAME = "admin"
INFLUXDB_PASSWORD = "adminpassword"
CA_CERT_PATH = "/keys/ca_cert.pem"

# Initialize the InfluxDB client
influxdb_client = InfluxDBClient(
    url=INFLUXDB_URL,
    username=INFLUXDB_USERNAME,
    password=INFLUXDB_PASSWORD,
    org=INFLUXDB_ORG,
    verify_ssl=False
)

# Correctly initialize Write API with batching or default options
write_api = influxdb_client.write_api(write_options=WriteOptions(batch_size=500, flush_interval=10_000))
