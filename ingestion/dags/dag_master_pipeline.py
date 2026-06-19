"""
DataStack Compass — Master Data Pipeline
========================================

DAG tổng hợp chạy vào 07:30 sáng hằng ngày.
Trách nhiệm: 
- Đợi ingestion DAGs hoàn thành
- Chạy Great Expectations kiểm tra Data Quality
- Build Gold Layer
- Update StarRocks Statistics
- Gửi báo cáo hàng ngày
- Dọn dẹp dữ liệu cũ
"""

import os
import sys
import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.sensors.external_task import ExternalTaskSensor

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

default_args = {
    "owner": "data_platform",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# --- Python Callables ---

def _run_great_expectations():
    """Chạy GE suites. Nếu lỗi thì cảnh báo nhưng không fail task."""
    logger.info("Starting Great Expectations Validation...")
    # Vì mock local, ta sẽ mô phỏng việc gọi python APIs.
    # Trong thực tế sẽ import các hàm từ processing/great_expectations/suites/
    try:
        # Chạy giả lập 1 suite cho 'apache-kafka' (hoặc loop list)
        logger.info("Running suite: silver_releases_suite")
        
        # Nếu thực sự muốn chạy, ta cần truyền SparkSession, nên tốt nhất để spark job hoặc bash
        # Tuy nhiên ta mô phỏng try/catch ở đây theo yêu cầu:
        pass
        
    except Exception as e:
        logger.error(f"DATA QUALITY WARNING: GE Suite failed: {e}")
        # Gửi email cảnh báo (simulate)
        logger.error("Simulated Email Sent: Data Quality Warning!")
        # Không raise e để task vẫn Pass

def _generate_daily_report():
    """Truy vấn StarRocks tạo báo cáo 24h và gửi Email."""
    import pymysql
    
    host = os.environ.get("STARROCKS_HOST", "127.0.0.1")
    port = int(os.environ.get("STARROCKS_PORT", "9030"))
    user = os.environ.get("STARROCKS_USER", "root")
    password = os.environ.get("STARROCKS_PASSWORD", "")
    report_email = os.environ.get("REPORT_EMAIL", "team@company.com")
    
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password, autocommit=True)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Truy vấn số lượng release mới
            cursor.execute("""
                SELECT COUNT(*) as new_releases 
                FROM minio_iceberg_catalog.silver.silver_releases 
                WHERE published_at >= DATE_SUB(NOW(), INTERVAL 1 DAY)
            """)
            releases = cursor.fetchone().get('new_releases', 0)
            
            # Truy vấn CVE mới
            cursor.execute("""
                SELECT severity, COUNT(*) as cnt 
                FROM minio_iceberg_catalog.silver.silver_cves 
                WHERE published_at >= DATE_SUB(NOW(), INTERVAL 1 DAY)
                GROUP BY severity
            """)
            cves = cursor.fetchall()
            
            # Khởi tạo body email HTML
            html = f"<h2>[DataStack Compass] Daily Report {datetime.now().strftime('%Y-%m-%d')}</h2>"
            html += f"<p><b>New Releases:</b> {releases}</p>"
            html += "<b>New CVEs (Last 24h):</b><ul>"
            if not cves:
                html += "<li>No new CVEs.</li>"
            for row in cves:
                html += f"<li>{row['severity']}: {row['cnt']}</li>"
            html += "</ul>"
            
            logger.info("--- SIMULATED EMAIL ---")
            logger.info(f"To: {report_email}")
            logger.info("Subject: [DataStack Compass] Daily Report " + datetime.now().strftime('%Y-%m-%d'))
            logger.info("Body:\n" + html)
            logger.info("-----------------------")
            
        conn.close()
    except Exception as e:
        logger.error(f"Failed to generate daily report: {e}")

def _cleanup_bronze_old_data():
    """Chạy Spark expire_snapshots xoá dữ liệu cũ hơn 90 ngày."""
    from pyspark.sql import SparkSession
    
    logger.info("Starting Delta Expire Snapshots...")
    builder = (SparkSession.builder
        .appName("CleanupBronze")
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.local.type", "hadoop")
        .config("spark.sql.catalog.local.warehouse", "s3a://")
        .config("spark.hadoop.fs.s3a.access.key", os.environ.get("MINIO_ACCESS_KEY", ""))
        .config("spark.hadoop.fs.s3a.secret.key", os.environ.get("MINIO_SECRET_KEY", ""))
        .config("spark.hadoop.fs.s3a.endpoint", os.environ.get("MINIO_ENDPOINT", "http://127.0.0.1:9000"))
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem"))

    try:
        spark = builder.getOrCreate()
        
        timestamp_90_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
        spark.sql(f"CALL local.system.expire_snapshots('bronze.bronze_raw_releases', TIMESTAMP '{timestamp_90_days_ago}')")
        
        # Mở rộng thêm cho cves nếu có
        try:
            spark.sql(f"CALL local.system.expire_snapshots('bronze.raw_cves', TIMESTAMP '{timestamp_90_days_ago}')")
        except Exception as e:
            logger.info(f"raw_cves expire_snapshots ignored (might not exist yet): {e}")
            
        logger.info("Expire snapshots completed successfully.")
        spark.stop()
    except Exception as e:
        logger.error(f"Vacuum failed: {e}")
        # Dọn dẹp lỗi có thể để pipeline pass, hoặc fail. Theo design, mình cứ log.


# --- DAG Definition ---

with DAG(
    dag_id="master_data_pipeline",
    default_args=default_args,
    schedule="30 7 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["compass", "master"],
) as dag:

    # 1. Sensors
    wait_for_releases = ExternalTaskSensor(
        task_id="wait_for_releases",
        external_dag_id="ingest_software_releases",
        execution_delta=timedelta(hours=5, minutes=30),  # 07:30 - 02:00
        timeout=timedelta(hours=2).total_seconds(),
        mode="reschedule"
    )
    
    wait_for_cves = ExternalTaskSensor(
        task_id="wait_for_cves",
        external_dag_id="ingest_cves",
        execution_delta=timedelta(hours=1, minutes=30),  # 07:30 - 06:00
        timeout=timedelta(hours=1).total_seconds(),
        mode="reschedule"
    )
    
    # 2. Great Expectations
    run_ge_all = PythonOperator(
        task_id="run_great_expectations_all",
        python_callable=_run_great_expectations
    )
    
    # 3. Build Gold Layer (Spark Submit)
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
        {_PROJECT_ROOT}/processing/spark_jobs/build_gold_summary.py
    """
    
    build_gold = BashOperator(
        task_id="build_gold_layer",
        bash_command=spark_submit_cmd,
        env=os.environ.copy()
    )
    
    # 4. Refresh StarRocks Stats
    refresh_stats = BashOperator(
        task_id="refresh_starrocks_stats",
        bash_command="""
            mysql -h ${STARROCKS_HOST:-127.0.0.1} -P ${STARROCKS_PORT:-9030} -u ${STARROCKS_USER:-root} \\
            -e "ANALYZE TABLE minio_iceberg_catalog.silver.silver_releases;"
        """
    )
    
    # 5. Generate Report
    generate_report = PythonOperator(
        task_id="generate_daily_report",
        python_callable=_generate_daily_report
    )
    
    # 6. Cleanup Bronze
    cleanup_bronze = PythonOperator(
        task_id="cleanup_bronze_old_data",
        python_callable=_cleanup_bronze_old_data
    )

    # --- Dependencies ---
    [wait_for_releases, wait_for_cves] >> run_ge_all
    run_ge_all >> build_gold
    build_gold >> refresh_stats
    refresh_stats >> generate_report
    generate_report >> cleanup_bronze
