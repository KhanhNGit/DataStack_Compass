"""
DataStack Compass — Process Releases DAG
========================================

DAG này được trigger tự động bởi ``ingest_software_releases`` sau khi có dữ liệu mới.
Nó gọi PySpark job ``transform_releases.py`` để xử lý raw data (Bronze) thành clean data (Silver).
"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

_PROJECT_ROOT = "/opt/airflow/compass_project"

default_args = {
    "owner": "datastack-compass",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="process_releases",
    default_args=default_args,
    schedule=None,  # Triggered by ingest_software_releases
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=3,
    tags=["compass", "processing"],
) as dag:

    # Lấy tool_name từ DagRun conf
    # {{ dag_run.conf.get('tool_name') }}
    
    spark_submit_cmd = f"""
        spark-submit \\
        --master "local[*]" \\
        --driver-memory 512m \\
        --executor-memory 512m \\
        --conf "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions" \\
        --conf "spark.sql.catalog.local=org.apache.iceberg.spark.SparkCatalog" \\
        --conf "spark.sql.catalog.local.type=hadoop" \\
        --conf "spark.sql.catalog.local.warehouse=s3a://" \\
        --conf "spark.hadoop.fs.s3a.access.key=${{MINIO_ACCESS_KEY}}" \\
        --conf "spark.hadoop.fs.s3a.secret.key=${{MINIO_SECRET_KEY}}" \\
        --conf "spark.hadoop.fs.s3a.endpoint=${{MINIO_ENDPOINT:-http://127.0.0.1:9000}}" \\
        --conf "spark.hadoop.fs.s3a.path.style.access=true" \\
        --conf "spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem" \\
        {_PROJECT_ROOT}/processing/spark_jobs/transform_releases.py \\
        --tool-name "{{{{ dag_run.conf.get('tool_name') }}}}"
    """

    process_task = BashOperator(
        task_id="run_transform_releases",
        bash_command=spark_submit_cmd,
        env={
            **os.environ,
            "PYTHONPATH": _PROJECT_ROOT,
        }
    )
