import pytest
import os
import pymysql
import requests
from pyspark.sql import SparkSession

@pytest.fixture(scope="session")
def spark_session():
    # Khởi tạo Spark Session với cấu hình hỗ trợ Delta Lake và S3A
    spark = SparkSession.builder \
        .appName("DataStackCompass_IntegrationTests") \
        .master("local[*]") \
        .config("spark.jars.packages", "io.delta:delta-spark_2.12:3.1.0,org.apache.hadoop:hadoop-aws:3.3.4") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .config("spark.hadoop.fs.s3a.endpoint", os.getenv("MINIO_ENDPOINT", "http://localhost:9000")) \
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("MINIO_ACCESS_KEY", "minioadmin")) \
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("MINIO_SECRET_KEY", "minioadmin")) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .getOrCreate()
    
    yield spark
    spark.stop()

@pytest.fixture(scope="session")
def db_connection():
    # Khởi tạo kết nối tới StarRocks thông qua pymysql
    host = os.getenv("STARROCKS_HOST", "127.0.0.1")
    port = int(os.getenv("STARROCKS_PORT", 9030))
    user = os.getenv("STARROCKS_USER", "root")
    password = os.getenv("STARROCKS_PASSWORD", "")
    db = os.getenv("STARROCKS_DB", "datastack_compass")
    
    # Tạo database test nếu chưa có
    temp_conn = pymysql.connect(host=host, port=port, user=user, password=password)
    try:
        with temp_conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db}")
    finally:
        temp_conn.close()

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db,
        cursorclass=pymysql.cursors.DictCursor
    )
    yield conn
    conn.close()

@pytest.fixture(scope="session")
def api_client():
    # Generic session wrapper (có thể thay bằng FastAPI TestClient nếu import app trực tiếp)
    session = requests.Session()
    # Mock property for easier testing if needed
    yield session
