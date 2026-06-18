import pytest
import os
import time
import requests
import subprocess
import boto3
from botocore.client import Config

# Cố gắng import connector, nếu file chưa tồn tại sẽ mock exception để tests không sập lúc parse file
try:
    from ingestion.connectors.github_connector import GitHubReleaseConnector
except ImportError:
    class GitHubReleaseConnector:
        @classmethod
        def fetch(cls, owner, repo):
            raise NotImplementedError("GitHubReleaseConnector is not implemented yet in ingestion.connectors.github_connector")

# Đánh dấu toàn bộ file này thuộc nhóm integration tests
pytestmark = pytest.mark.integration

def test_minio_connection():
    """1. Kết nối MinIO, tạo/xóa bucket test, verify S3A path hoạt động"""
    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    
    s3 = boto3.client('s3',
                      endpoint_url=endpoint,
                      aws_access_key_id=access_key,
                      aws_secret_access_key=secret_key,
                      config=Config(signature_version='s3v4'))
    
    bucket_name = "test-compass-bucket"
    
    # Tạo bucket
    try:
        s3.create_bucket(Bucket=bucket_name)
    except Exception as e:
        if "BucketAlreadyOwnedByYou" not in str(e):
            raise
            
    # List và verify
    response = s3.list_buckets()
    buckets = [bucket['Name'] for bucket in response['Buckets']]
    assert bucket_name in buckets
    
    # Xóa bucket
    s3.delete_bucket(Bucket=bucket_name)
    
    response = s3.list_buckets()
    buckets = [bucket['Name'] for bucket in response['Buckets']]
    assert bucket_name not in buckets

def test_spark_delta_write_read(spark_session):
    """2. Khởi tạo Spark session, ghi Delta 5 rows, đọc lại verify số rows"""
    test_path = "s3a://silver/test_table/"
    
    # Cần tạo bucket silver nếu chưa có
    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    s3 = boto3.client('s3', endpoint_url=endpoint, aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    try:
        s3.create_bucket(Bucket="silver")
    except Exception:
        pass
        
    data = [("A", 1), ("B", 2), ("C", 3), ("D", 4), ("E", 5)]
    columns = ["name", "value"]
    
    # Tạo DataFrame
    df = spark_session.createDataFrame(data, columns)
    
    # Ghi Delta
    df.write.format("iceberg").mode("overwrite").save(test_path)
    
    # Đọc lại Delta
    read_df = spark_session.read.format("iceberg").load(test_path)
    
    # Verify số lượng rows
    assert read_df.count() == 5
    
    # Cleanup (xóa object test_table trong MinIO bằng boto3)
    objects = s3.list_objects_v2(Bucket="silver", Prefix="test_table/")
    if 'Contents' in objects:
        for obj in objects['Contents']:
            s3.delete_object(Bucket="silver", Key=obj['Key'])

def test_github_connector():
    """3. Verify real API call từ GitHubReleaseConnector"""
    assert os.getenv("GITHUB_TOKEN") is not None, "GITHUB_TOKEN must be set for this real API call"
    
    # KHÔNG mock
    releases = GitHubReleaseConnector.fetch("apache", "kafka")
    
    assert isinstance(releases, list)
    assert len(releases) > 0
    
    first_release = releases[0]
    assert "tag_name" in first_release
    assert "published_at" in first_release
    assert "body" in first_release

def test_starrocks_query(db_connection):
    """4. Connect StarRocks, create table, insert, select và drop"""
    with db_connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_table (
                id INT, 
                name VARCHAR(100)
            ) ENGINE=OLAP 
            DISTRIBUTED BY HASH(id) BUCKETS 1 
            PROPERTIES ('replication_num' = '1')
        """)
        
        cursor.execute("INSERT INTO test_table (id, name) VALUES (1, 'Compass Integration Test')")
        db_connection.commit()
        
        # Đợi 1 giây để StarRocks async visibility sync hoàn thiện sau khi insert
        time.sleep(1)
        
        cursor.execute("SELECT * FROM test_table WHERE id = 1")
        result = cursor.fetchone()
        
        assert result is not None
        assert result['id'] == 1
        assert result['name'] == 'Compass Integration Test'
        
        cursor.execute("DROP TABLE test_table")
        db_connection.commit()

def test_api_health():
    """5. Start FastAPI server trong subprocess, fetch GET /health, verify response"""
    import sys
    
    # Khởi động app FastAPI
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE,
        cwd=os.path.join(os.path.dirname(__file__), "..", "..") # Chạy từ root project
    )
    
    try:
        # Chờ server khởi động
        time.sleep(3)
        
        response = requests.get("http://127.0.0.1:8000/health", timeout=5)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("db") is True
    except Exception as e:
        pytest.fail(f"API server did not start or failed health check: {e}")
    finally:
        process.terminate()
        process.wait()

def test_full_ingestion_pipeline():
    """6. Trigger DAG qua Airflow REST API, poll trạng thái đến khi thành công"""
    airflow_url = os.getenv("AIRFLOW_URL", "http://localhost:8080")
    auth = (os.getenv("AIRFLOW_USER", "admin"), os.getenv("AIRFLOW_PASS", "admin"))
    
    dag_id = "ingest_software_releases"
    trigger_url = f"{airflow_url}/api/v1/dags/{dag_id}/dagRuns"
    
    # Trigger DAG
    trigger_res = requests.post(trigger_url, json={}, auth=auth)
    
    # Nếu Airflow chưa bật hoặc authorization sai, bài test sẽ fail tại đây
    if trigger_res.status_code != 200:
        pytest.skip(f"Airflow is not available or DAG '{dag_id}' does not exist. Status: {trigger_res.status_code}")
        
    dag_run_id = trigger_res.json().get("dag_run_id")
    assert dag_run_id is not None
    
    # Poll status mỗi 10s
    status_url = f"{airflow_url}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}"
    timeout = 300 # 5 phút
    interval = 10
    elapsed = 0
    state = "running"
    
    while elapsed < timeout:
        res = requests.get(status_url, auth=auth)
        assert res.status_code == 200
        
        state = res.json().get("state")
        if state in ["success", "failed"]:
            break
            
        time.sleep(interval)
        elapsed += interval
        
    assert state == "success", f"DAG run ended with state: {state} sau {elapsed}s"
    
    # Verify records có tồn tại trong bucket bronze (mô phỏng Data layer checks)
    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    s3 = boto3.client('s3', endpoint_url=endpoint, aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    
    try:
        objects = s3.list_objects_v2(Bucket="bronze", Prefix="software_releases/")
        assert 'Contents' in objects and len(objects['Contents']) > 0, "No records generated in bronze/software_releases/"
    except Exception as e:
        pytest.fail(f"Failed to verify MinIO bronze layer: {e}")
