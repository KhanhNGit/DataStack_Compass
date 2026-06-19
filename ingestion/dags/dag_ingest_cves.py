"""
DataStack Compass — DAG: Ingest CVE Data from cvelistV5
==================================================

Thu thập thông tin CVE từ repo GitHub cvelistV5 thay vì NVD API.
Sử dụng Medallion Architecture:
- Bronze: File JSONL nguyên bản từ cvelistV5 (lưu trên MinIO).
- Silver: Bảng Iceberg silver_cves đã được lọc theo Tool Catalog và chuẩn hóa ranges.

Schedule  : Hàng ngày lúc 06:00 AM UTC
Idempotent: Có (ghi đè file JSONL ở Bronze, dùng Delta MERGE ở Silver).

Task Flow
---------
    sync_cvelist_repo (Download & Upload to Bronze)
           │
           ▼
    trigger_spark_transform (Spark: Parse JSONL -> Match Rules -> Extract Ranges -> Silver Iceberg)
           │
           ▼
    check_critical_cves (Query Silver)
           │
           ▼
    should_send_alert (ShortCircuit)
           │
           ▼
    send_alert_if_critical
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator
from airflow.operators.python import ShortCircuitOperator

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

_DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "datastack-compass",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

@dag(
    dag_id="ingest_cves",
    description="Thu thập CVE data từ cvelistV5 cho các Data Stack tools",
    schedule="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "cves", "security"],
    default_args=_DEFAULT_ARGS,
    doc_md=__doc__,
)
def ingest_cves():

    # ─────────────────────────────────────────────────────────────────────
    # Task 1: Download & Upload to Bronze (cvelist_connector)
    # ─────────────────────────────────────────────────────────────────────
    sync_cvelist_repo = BashOperator(
        task_id="sync_cvelist_repo",
        bash_command="python /opt/airflow/compass_project/ingestion/connectors/cvelist_connector.py",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Task 2: Transform CVEs (Bronze -> Silver via Spark)
    # ─────────────────────────────────────────────────────────────────────
    # Sử dụng spark-submit chạy job processing/spark_jobs/transform_cves.py
    trigger_spark_transform = BashOperator(
        task_id="trigger_spark_transform",
        bash_command=(
            "spark-submit --master \"local[*]\" "
            "--packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 "
            "--conf \"spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions\" "
            "--conf \"spark.sql.catalog.local=org.apache.iceberg.spark.SparkCatalog\" "
            "--conf \"spark.sql.catalog.local.type=hadoop\" "
            "--conf \"spark.sql.catalog.local.warehouse=s3a://${MINIO_BUCKET_BRONZE:-compass-lake}/\" "
            "--conf \"spark.hadoop.fs.s3a.access.key=${MINIO_ACCESS_KEY}\" "
            "--conf \"spark.hadoop.fs.s3a.secret.key=${MINIO_SECRET_KEY}\" "
            "--conf \"spark.hadoop.fs.s3a.endpoint=${MINIO_ENDPOINT:-http://127.0.0.1:9000}\" "
            "--conf \"spark.hadoop.fs.s3a.path.style.access=true\" "
            "--conf \"spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem\" "
            "/opt/airflow/compass_project/processing/spark_jobs/transform_cves.py"
        ),
    )

    # ─────────────────────────────────────────────────────────────────────
    # Task 2.5: Enrich Missing CVSS using NVD API
    # ─────────────────────────────────────────────────────────────────────
    @task(task_id="enrich_missing_cvss")
    def enrich_missing_cvss(**context) -> dict:
        import time
        import requests
        from processing.spark_utils.session import get_spark_session
        
        spark = get_spark_session("enrich_cvss")
        try:
            # Find CVEs with NULL cvss_score
            df = spark.read.table("local.silver.silver_cves")
            missing_df = df.filter(df.cvss_score.isNull()).select("cve_id", "tool_name").distinct()
            missing_cves = [r.asDict() for r in missing_df.collect()]
            
            if not missing_cves:
                logger.info("No CVEs missing CVSS scores.")
                spark.stop()
                return {"enriched": 0}
                
            logger.info(f"Found {len(missing_cves)} CVEs missing CVSS. Fetching from NVD...")
            enriched_records = []
            
            for item in missing_cves:
                cve_id = item["cve_id"]
                url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}"
                try:
                    time.sleep(6) # Rate limit: 5 req / 30s
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        vulns = data.get("vulnerabilities", [])
                        if vulns:
                            cve_data = vulns[0].get("cve", {})
                            metrics = cve_data.get("metrics", {})
                            cvss_score = None
                            severity = "Low"
                            
                            for k in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                                if k in metrics and metrics[k]:
                                    cvss_score = metrics[k][0].get("cvssData", {}).get("baseScore")
                                    severity = metrics[k][0].get("baseSeverity", "Low").capitalize()
                                    if cvss_score is not None:
                                        cvss_score = float(cvss_score)
                                        break
                                        
                            if cvss_score is not None:
                                enriched_records.append((cve_id, cvss_score, severity))
                except Exception as e:
                    logger.warning(f"Failed to fetch {cve_id} from NVD: {e}")
                    
            if enriched_records:
                # Create a DataFrame and update Iceberg table
                from pyspark.sql.types import StructType, StructField, StringType, FloatType
                schema = StructType([
                    StructField("cve_id", StringType(), False),
                    StructField("cvss_score", FloatType(), False),
                    StructField("severity", StringType(), False)
                ])
                updates_df = spark.createDataFrame(enriched_records, schema)
                updates_df.createOrReplaceTempView("updates")
                
                spark.sql("""
                    MERGE INTO local.silver.silver_cves target
                    USING updates source
                    ON target.cve_id = source.cve_id
                    WHEN MATCHED THEN UPDATE SET 
                        cvss_score = source.cvss_score,
                        severity = source.severity
                """)
                logger.info(f"Successfully enriched {len(enriched_records)} CVEs.")
                
            spark.stop()
            return {"enriched": len(enriched_records)}
            
        except Exception as e:
            logger.error(f"Enrichment failed: {e}")
            try: spark.stop()
            except: pass
            return {"enriched": 0}

    enrich_task = enrich_missing_cvss()

    # ─────────────────────────────────────────────────────────────────────
    # Task 3: Check Critical CVEs
    # ─────────────────────────────────────────────────────────────────────
    @task(task_id="check_critical_cves")
    def check_critical_cves(**context) -> dict:
        ti = context["ti"]
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        critical_cves: List[dict] = []
        try:
            from processing.spark_utils.session import get_spark_session
            spark = get_spark_session("check_critical_cves")
            try:
                df = spark.read.table("local.silver.silver_cves")
                df.createOrReplaceTempView("silver_cves")
                query = f"""
                    SELECT cve_id, tool_name, cvss_score, severity, description
                    FROM silver_cves
                    WHERE severity IN ('Critical', 'High')
                      AND published_at >= '{yesterday.strftime("%Y-%m-%d %H:%M:%S")}'
                    ORDER BY cvss_score DESC
                """
                critical_cves = [row.asDict() for row in spark.sql(query).collect()]
                spark.stop()
            except Exception as e:
                logger.warning(f"Failed to query silver_cves via Spark: {e}")
                critical_cves = []
        except Exception as exc:
            logger.warning(f"Could not init spark session: {exc}")

        has_critical = len(critical_cves) > 0
        ti.xcom_push(key="has_critical_cves", value=has_critical)
        ti.xcom_push(key="critical_cves_data", value=critical_cves[:20])

        if has_critical:
            logger.warning("⚠️ Found %d Critical/High CVEs in last 24h!", len(critical_cves))
        else:
            logger.info("✓ No Critical/High CVEs found in last 24h")

        return {
            "has_critical": has_critical,
            "critical_count": len(critical_cves),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Task 4 & 5: Alerting
    # ─────────────────────────────────────────────────────────────────────
    def _should_send_alert(**context) -> bool:
        ti = context["ti"]
        return ti.xcom_pull(task_ids="check_critical_cves", key="has_critical_cves") is True

    should_alert = ShortCircuitOperator(
        task_id="should_send_alert",
        python_callable=_should_send_alert,
    )

    @task(task_id="send_alert_if_critical")
    def send_alert_if_critical(**context) -> dict:
        # Same as before
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        ti = context["ti"]
        critical_cves = ti.xcom_pull(task_ids="check_critical_cves", key="critical_cves_data") or []
        if not critical_cves: return {"sent": False}
        
        smtp_host = os.environ.get("SMTP_HOST", "localhost")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_password = os.environ.get("SMTP_PASSWORD", "")
        from_addr = os.environ.get("SMTP_FROM", "datastack-compass@localhost")
        to_addrs = os.environ.get("ALERT_EMAIL_TO", "admin@localhost")
        
        subject = f"🚨 DataStack Compass: {len(critical_cves)} Critical/High CVEs detected"
        rows_html = ""
        for cve in critical_cves:
            score = cve.get("cvss_score") or 0
            color = "#dc3545" if cve.get("severity") == "Critical" else "#fd7e14"
            rows_html += f"<tr><td>{cve.get('cve_id')}</td><td>{cve.get('tool_name')}</td><td style='color:{color}'>{cve.get('severity')}</td><td>{score:.1f}</td><td>{(cve.get('description') or '')[:200]}</td></tr>"
        
        html_body = f"<html><body><h2>🚨 Critical/High CVEs</h2><table border='1'><thead><tr><th>CVE</th><th>Tool</th><th>Severity</th><th>CVSS</th><th>Description</th></tr></thead><tbody>{rows_html}</tbody></table></body></html>"
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addrs
        msg.attach(MIMEText(html_body, "html"))
        
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                if smtp_port == 587: server.starttls()
                if smtp_user and smtp_password: server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, to_addrs.split(","), msg.as_string())
            return {"sent": True}
        except Exception as exc:
            return {"sent": False, "error": str(exc)}

    # Wiring
    critical_check = check_critical_cves()
    alert = send_alert_if_critical()

    sync_cvelist_repo >> trigger_spark_transform >> enrich_task >> critical_check >> should_alert >> alert

ingest_cves()
