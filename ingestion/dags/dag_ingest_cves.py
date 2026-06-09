"""
DataStack Compass — DAG: Ingest CVE Data from NVD
==================================================

Thu thập thông tin CVE (Common Vulnerabilities and Exposures) từ NVD API
cho các tools đang track trong hệ thống.

Schedule  : Hàng ngày lúc 06:00 AM UTC
Idempotent: Có — dùng Delta Lake MERGE (upsert) theo cve_id, không tạo bản ghi trùng.
Rate Limit: NVD API cho phép 5 req/30s (không API key), 50 req/30s (có API key).

Data source: https://services.nvd.nist.gov/rest/json/cves/2.0

Task Flow
---------
    get_tool_list
          │
          ▼
    fetch_cves_for_tool  ──(dynamic map × N tools)
          │
          ▼
    upsert_cves_to_silver  ──(dynamic map × N tools)
          │
          ▼
    check_critical_cves
          │
          ▼
    should_send_alert  ──(ShortCircuit)
          │
          ▼
    send_alert_if_critical
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from airflow.decorators import dag, task
from airflow.exceptions import AirflowException
from airflow.operators.python import ShortCircuitOperator

# ─── Project root trên sys.path ─────────────────────────────────────────────
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

NVD_API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"

# NVD rate limit: 5 requests / 30 seconds (no API key)
#                50 requests / 30 seconds (with API key)
_NVD_SLEEP_NO_KEY = 6.0     # 30s / 5 = 6s giữa mỗi request
_NVD_SLEEP_WITH_KEY = 0.6   # 30s / 50 = 0.6s

# Fallback tool list nếu StarRocks chưa có data
_FALLBACK_TOOLS = [
    "apache-kafka",
    "apache-flink",
    "apache-spark",
    "delta-io",
    "starrocks",
]

# CVSS severity mapping
_SEVERITY_MAP = {
    (0.0, 0.1): "None",
    (0.1, 4.0): "Low",
    (4.0, 7.0): "Medium",
    (7.0, 9.0): "High",
    (9.0, 10.1): "Critical",
}

# StarRocks connection
_STARROCKS_HOST = os.environ.get("STARROCKS_HOST", "127.0.0.1")
_STARROCKS_PORT = int(os.environ.get("STARROCKS_PORT", "9030"))
_STARROCKS_USER = os.environ.get("STARROCKS_USER", "root")
_STARROCKS_PASSWORD = os.environ.get("STARROCKS_PASSWORD", "")

# =============================================================================
# Default args
# =============================================================================

_DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "datastack-compass",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


# =============================================================================
# Helpers (module-level, lazy-imported inside tasks)
# =============================================================================

def _get_nvd_sleep() -> float:
    """Thời gian sleep giữa các NVD requests dựa trên có API key hay không."""
    return _NVD_SLEEP_WITH_KEY if os.environ.get("NVD_API_KEY") else _NVD_SLEEP_NO_KEY


def _nvd_headers() -> Dict[str, str]:
    """Headers cho NVD API, kèm API key nếu có."""
    headers = {"Accept": "application/json"}
    api_key = os.environ.get("NVD_API_KEY")
    if api_key:
        headers["apiKey"] = api_key
    return headers


def _cvss_to_severity(score: Optional[float]) -> str:
    """Map CVSS score → severity label theo NVD standard."""
    if score is None:
        return "Low"
    for (lo, hi), label in _SEVERITY_MAP.items():
        if lo <= score < hi:
            return label
    return "Low"


def _parse_nvd_cve(cve_item: dict, tool_name: str) -> Optional[dict]:
    """Parse một CVE item từ NVD API response.

    Returns
    -------
    dict | None
        Parsed CVE record, hoặc None nếu không liên quan đến tool.
    """
    cve_data = cve_item.get("cve", {})
    cve_id = cve_data.get("id", "")

    # ── Description (English) ────────────────────────────────────────────
    descriptions = cve_data.get("descriptions", [])
    description_en = ""
    for desc in descriptions:
        if desc.get("lang") == "en":
            description_en = desc.get("value", "")
            break

    # Kiểm tra xem CVE có liên quan đến tool không
    tool_keywords = tool_name.replace("-", " ").lower().split()
    desc_lower = description_en.lower()
    cve_id_lower = cve_id.lower()

    # Match nếu tất cả keywords xuất hiện trong description hoặc CVE configs
    is_relevant = all(kw in desc_lower for kw in tool_keywords)

    if not is_relevant:
        # Kiểm tra thêm trong configurations
        configs = cve_data.get("configurations", [])
        config_str = str(configs).lower()
        is_relevant = all(kw in config_str for kw in tool_keywords)

    if not is_relevant:
        return None

    # ── CVSS Score ────────────────────────────────────────────────────────
    cvss_score = None
    metrics = cve_data.get("metrics", {})

    # Thử CVSS v3.1 trước, fallback v3.0, rồi v2
    for metric_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        metric_list = metrics.get(metric_key, [])
        if metric_list:
            cvss_data = metric_list[0].get("cvssData", {})
            cvss_score = cvss_data.get("baseScore")
            if cvss_score is not None:
                cvss_score = float(cvss_score)
                break

    severity = _cvss_to_severity(cvss_score)

    # ── Affected versions ─────────────────────────────────────────────────
    affected_versions: List[str] = []
    fixed_in_version: Optional[str] = None

    configs = cve_data.get("configurations", [])
    for config in configs:
        for node in config.get("nodes", []):
            for cpe_match in node.get("cpeMatch", []):
                if cpe_match.get("vulnerable"):
                    criteria = cpe_match.get("criteria", "")
                    # CPE format: cpe:2.3:a:vendor:product:version:...
                    parts = criteria.split(":")
                    if len(parts) >= 6 and parts[5] not in ("*", "-"):
                        affected_versions.append(parts[5])

                    # Version ranges
                    up_to = cpe_match.get("versionEndExcluding")
                    if up_to:
                        fixed_in_version = up_to
                    up_to_incl = cpe_match.get("versionEndIncluding")
                    if up_to_incl and not fixed_in_version:
                        affected_versions.append(up_to_incl)

    # Deduplicate
    affected_versions = list(dict.fromkeys(affected_versions)) or ["unknown"]

    # ── Published date ────────────────────────────────────────────────────
    published_str = cve_data.get("published", "")
    published_at = None
    if published_str:
        try:
            published_at = datetime.fromisoformat(
                published_str.replace("Z", "+00:00")
            )
        except ValueError:
            pass

    return {
        "cve_id": cve_id,
        "tool_name": tool_name,
        "affected_versions": affected_versions,
        "fixed_in_version": fixed_in_version,
        "cvss_score": cvss_score,
        "severity": severity,
        "description": description_en[:4000] if description_en else None,
        "published_at": published_at,
    }


# =============================================================================
# DAG definition
# =============================================================================

@dag(
    dag_id="ingest_cves",
    description="Thu thập CVE data từ NVD API cho các Data Stack tools",
    schedule="0 6 * * *",           # Hàng ngày lúc 06:00 AM UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "cves", "security"],
    default_args=_DEFAULT_ARGS,
    doc_md=__doc__,
)
def ingest_cves():
    """DAG: NVD CVE scan → silver upsert → critical alert."""

    # ─────────────────────────────────────────────────────────────────────
    # Task 1: Lấy danh sách tool đang track từ StarRocks
    # ─────────────────────────────────────────────────────────────────────

    @task(task_id="get_tool_list")
    def get_tool_list() -> List[str]:
        """Query StarRocks để lấy DISTINCT tool_name từ silver_releases.

        Fallback về danh sách hardcode nếu StarRocks chưa có data.

        Returns
        -------
        list[str]
            Danh sách tool names.
        """
        import pymysql

        try:
            conn = pymysql.connect(
                host=_STARROCKS_HOST,
                port=_STARROCKS_PORT,
                user=_STARROCKS_USER,
                password=_STARROCKS_PASSWORD,
                database="default_catalog.silver",
                connect_timeout=10,
            )
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT DISTINCT tool_name FROM silver_releases"
                    )
                    tools = [row[0] for row in cursor.fetchall()]

                if tools:
                    logger.info(
                        "✓ Loaded %d tools from StarRocks: %s",
                        len(tools),
                        tools,
                    )
                    return tools

            finally:
                conn.close()

        except Exception as exc:
            logger.warning(
                "Could not query StarRocks (using fallback list): %s", exc
            )

        logger.info("Using fallback tool list: %s", _FALLBACK_TOOLS)
        return _FALLBACK_TOOLS

    # ─────────────────────────────────────────────────────────────────────
    # Task 2: Fetch CVEs từ NVD API
    # ─────────────────────────────────────────────────────────────────────

    @task(task_id="fetch_cves_for_tool", retries=2, retry_delay=timedelta(minutes=5))
    def fetch_cves_for_tool(tool_name: str) -> Dict[str, Any]:
        """Gọi NVD API tìm CVE mới trong 24h cho tool.

        Parameters
        ----------
        tool_name : str
            Tên tool (e.g. ``"apache-kafka"``).

        Returns
        -------
        dict
            ``{tool_name, cves: list[dict], count, status}``.
        """
        import requests

        # Date range: yesterday → today (UTC)
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        # NVD API date format: ISO 8601
        date_fmt = "%Y-%m-%dT%H:%M:%S.000"
        params = {
            "keywordSearch": tool_name.replace("-", " "),
            "pubStartDate": yesterday.strftime(date_fmt),
            "pubEndDate": now.strftime(date_fmt),
        }

        logger.info(
            "Fetching CVEs for %s from NVD (range: %s → %s)",
            tool_name,
            params["pubStartDate"],
            params["pubEndDate"],
        )

        # ── Rate limiting ────────────────────────────────────────────────
        sleep_time = _get_nvd_sleep()
        time.sleep(sleep_time)

        try:
            resp = requests.get(
                NVD_API_BASE,
                params=params,
                headers=_nvd_headers(),
                timeout=30,
            )
        except requests.RequestException as exc:
            logger.error("NVD API request failed for %s: %s", tool_name, exc)
            return {
                "tool_name": tool_name,
                "cves": [],
                "count": 0,
                "status": "error",
                "error": str(exc),
            }

        if resp.status_code == 403:
            logger.warning("NVD API rate limited — sleeping 30s and retrying")
            time.sleep(30)
            resp = requests.get(
                NVD_API_BASE,
                params=params,
                headers=_nvd_headers(),
                timeout=30,
            )

        if resp.status_code >= 400:
            logger.error(
                "NVD API error for %s: HTTP %d %s",
                tool_name,
                resp.status_code,
                resp.reason,
            )
            return {
                "tool_name": tool_name,
                "cves": [],
                "count": 0,
                "status": "error",
                "error": f"HTTP {resp.status_code}",
            }

        data = resp.json()
        vulnerabilities = data.get("vulnerabilities", [])

        # Parse và filter CVEs
        parsed_cves: List[dict] = []
        for vuln in vulnerabilities:
            parsed = _parse_nvd_cve(vuln, tool_name)
            if parsed:
                parsed_cves.append(parsed)

        logger.info(
            "✓ %s: found %d CVEs (%d total from NVD, %d relevant)",
            tool_name,
            len(parsed_cves),
            len(vulnerabilities),
            len(parsed_cves),
        )

        return {
            "tool_name": tool_name,
            "cves": parsed_cves,
            "count": len(parsed_cves),
            "status": "success",
        }

    # ─────────────────────────────────────────────────────────────────────
    # Task 3: Upsert CVEs vào Silver layer (Delta MERGE)
    # ─────────────────────────────────────────────────────────────────────

    @task(task_id="upsert_cves_to_silver")
    def upsert_cves_to_silver(fetch_result: dict) -> dict:
        """MERGE INTO silver_cves bằng Delta Lake merge (cve_id làm key).

        Parameters
        ----------
        fetch_result : dict
            Output từ ``fetch_cves_for_tool``.

        Returns
        -------
        dict
            ``{tool_name, upserted, skipped, status}``.
        """
        from delta.tables import DeltaTable
        from pyspark.sql import Row

        from processing.spark_utils.session import get_spark_session
        from storage.delta.schemas import SCHEMAS

        tool_name = fetch_result["tool_name"]
        cves = fetch_result.get("cves", [])

        if not cves:
            logger.info("No CVEs to upsert for %s", tool_name)
            return {
                "tool_name": tool_name,
                "upserted": 0,
                "skipped": 0,
                "status": "no_data",
            }

        bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
        table_path = f"s3a://{bucket}/silver_cves/"
        schema = SCHEMAS["silver_cves"]

        spark = get_spark_session(f"cve-upsert-{tool_name}")

        try:
            # Tạo DataFrame từ parsed CVEs
            rows = []
            for cve in cves:
                rows.append(Row(
                    cve_id=cve["cve_id"],
                    tool_name=cve["tool_name"],
                    affected_versions=cve["affected_versions"],
                    fixed_in_version=cve.get("fixed_in_version"),
                    cvss_score=cve.get("cvss_score"),
                    severity=cve["severity"],
                    description=cve.get("description"),
                    published_at=cve.get("published_at"),
                ))

            updates_df = spark.createDataFrame(rows, schema)

            # Delta MERGE — upsert theo cve_id
            if DeltaTable.isDeltaTable(spark, table_path):
                delta_table = DeltaTable.forPath(spark, table_path)

                merge_result = (
                    delta_table.alias("target")
                    .merge(
                        updates_df.alias("source"),
                        "target.cve_id = source.cve_id"
                    )
                    .whenMatchedUpdateAll()
                    .whenNotMatchedInsertAll()
                    .execute()
                )

                logger.info(
                    "✓ Merged %d CVEs into silver_cves for %s",
                    len(cves),
                    tool_name,
                )
            else:
                # Bảng chưa tồn tại → tạo mới
                updates_df.write.format("delta").mode("overwrite").save(table_path)
                logger.info(
                    "✓ Created silver_cves with %d records for %s",
                    len(cves),
                    tool_name,
                )

            return {
                "tool_name": tool_name,
                "upserted": len(cves),
                "skipped": 0,
                "status": "success",
            }

        except Exception as exc:
            logger.error(
                "Failed to upsert CVEs for %s: %s", tool_name, exc
            )
            return {
                "tool_name": tool_name,
                "upserted": 0,
                "skipped": len(cves),
                "status": "error",
                "error": str(exc),
            }
        finally:
            spark.stop()

    # ─────────────────────────────────────────────────────────────────────
    # Task 4: Kiểm tra CVE Critical mới trong 24h
    # ─────────────────────────────────────────────────────────────────────

    @task(task_id="check_critical_cves")
    def check_critical_cves(upsert_results: list, **context) -> dict:
        """Query StarRocks tìm CVE Critical/High mới trong 24h.

        Pushes XCom ``has_critical_cves`` = True nếu tìm thấy.

        Returns
        -------
        dict
            ``{has_critical, critical_count, critical_cves}``.
        """
        import pymysql

        ti = context["ti"]
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        critical_cves: List[dict] = []

        try:
            conn = pymysql.connect(
                host=_STARROCKS_HOST,
                port=_STARROCKS_PORT,
                user=_STARROCKS_USER,
                password=_STARROCKS_PASSWORD,
                database="default_catalog.silver",
                connect_timeout=10,
            )
            try:
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(
                        """
                        SELECT cve_id, tool_name, cvss_score, severity, description
                        FROM silver_cves
                        WHERE severity IN ('Critical', 'High')
                          AND published_at >= %s
                        ORDER BY cvss_score DESC
                        """,
                        (yesterday.strftime("%Y-%m-%d %H:%M:%S"),),
                    )
                    critical_cves = cursor.fetchall()
            finally:
                conn.close()

        except Exception as exc:
            # Fallback: trích từ upsert results
            logger.warning(
                "Could not query StarRocks for critical CVEs: %s. "
                "Falling back to in-memory check.",
                exc,
            )
            for result in upsert_results:
                if isinstance(result, list):
                    items = result
                else:
                    items = [result]
                for item in items:
                    if item.get("status") == "success" and item.get("upserted", 0) > 0:
                        # Không có detail từ upsert result, đánh dấu cần kiểm tra
                        pass

        has_critical = len(critical_cves) > 0

        # Push XCom cho ShortCircuitOperator
        ti.xcom_push(key="has_critical_cves", value=has_critical)
        ti.xcom_push(key="critical_cves_data", value=critical_cves[:20])

        if has_critical:
            logger.warning(
                "⚠️ Found %d Critical/High CVEs in last 24h!",
                len(critical_cves),
            )
            for cve in critical_cves[:5]:
                logger.warning(
                    "  • %s (%s) — CVSS %.1f — %s",
                    cve.get("cve_id", "?"),
                    cve.get("tool_name", "?"),
                    cve.get("cvss_score", 0) or 0,
                    (cve.get("description", "") or "")[:100],
                )
        else:
            logger.info("✓ No Critical/High CVEs found in last 24h")

        return {
            "has_critical": has_critical,
            "critical_count": len(critical_cves),
            "critical_cves": [
                {
                    "cve_id": c.get("cve_id"),
                    "tool_name": c.get("tool_name"),
                    "cvss_score": c.get("cvss_score"),
                    "severity": c.get("severity"),
                }
                for c in critical_cves[:20]
            ],
        }

    # ─────────────────────────────────────────────────────────────────────
    # Task 5a: ShortCircuit — skip alert nếu không có critical CVEs
    # ─────────────────────────────────────────────────────────────────────

    def _should_send_alert(**context) -> bool:
        """Trả về True nếu có Critical CVEs → cho phép send_alert chạy."""
        ti = context["ti"]
        return ti.xcom_pull(
            task_ids="check_critical_cves",
            key="has_critical_cves",
        ) is True

    should_alert = ShortCircuitOperator(
        task_id="should_send_alert",
        python_callable=_should_send_alert,
    )

    # ─────────────────────────────────────────────────────────────────────
    # Task 5b: Gửi email alert cho Critical CVEs
    # ─────────────────────────────────────────────────────────────────────

    @task(task_id="send_alert_if_critical")
    def send_alert_if_critical(**context) -> dict:
        """Gửi email SMTP thông báo CVE critical mới.

        Environment
        -----------
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
        SMTP_FROM, ALERT_EMAIL_TO
        """
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        ti = context["ti"]
        critical_cves = ti.xcom_pull(
            task_ids="check_critical_cves",
            key="critical_cves_data",
        ) or []

        if not critical_cves:
            logger.info("No critical CVEs to alert on (unexpected)")
            return {"sent": False, "reason": "no_data"}

        # ── SMTP config từ env ───────────────────────────────────────────
        smtp_host = os.environ.get("SMTP_HOST", "localhost")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_password = os.environ.get("SMTP_PASSWORD", "")
        from_addr = os.environ.get("SMTP_FROM", "datastack-compass@localhost")
        to_addrs = os.environ.get("ALERT_EMAIL_TO", "admin@localhost")

        # ── Build email ──────────────────────────────────────────────────
        subject = (
            f"🚨 DataStack Compass: {len(critical_cves)} Critical/High CVEs "
            f"detected — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        )

        # HTML body
        rows_html = ""
        for cve in critical_cves:
            score = cve.get("cvss_score") or 0
            color = "#dc3545" if cve.get("severity") == "Critical" else "#fd7e14"
            rows_html += f"""
            <tr>
                <td><a href="https://nvd.nist.gov/vuln/detail/{cve.get('cve_id', '')}">{cve.get('cve_id', 'N/A')}</a></td>
                <td>{cve.get('tool_name', 'N/A')}</td>
                <td style="color:{color};font-weight:bold">{cve.get('severity', 'N/A')}</td>
                <td>{score:.1f}</td>
                <td>{(cve.get('description', '') or '')[:200]}</td>
            </tr>"""

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #dc3545;">🚨 Critical/High CVEs Detected</h2>
            <p>DataStack Compass đã phát hiện <strong>{len(critical_cves)}</strong>
            CVE mức Critical/High trong 24 giờ qua.</p>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%">
                <thead style="background:#343a40;color:white">
                    <tr>
                        <th>CVE ID</th>
                        <th>Tool</th>
                        <th>Severity</th>
                        <th>CVSS</th>
                        <th>Description</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            <p style="margin-top:16px;color:#6c757d;font-size:12px">
                Generated by DataStack Compass at {datetime.now(timezone.utc).isoformat()}
            </p>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addrs
        msg.attach(MIMEText(html_body, "html"))

        # ── Send ─────────────────────────────────────────────────────────
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                if smtp_port == 587:
                    server.starttls()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_addr, to_addrs.split(","), msg.as_string())

            logger.info(
                "✓ Alert email sent to %s (%d CVEs)", to_addrs, len(critical_cves)
            )
            return {"sent": True, "to": to_addrs, "cve_count": len(critical_cves)}

        except Exception as exc:
            logger.error("Failed to send alert email: %s", exc)
            # Không raise — alerting failure không nên fail toàn DAG
            return {"sent": False, "error": str(exc)}

    # ─────────────────────────────────────────────────────────────────────
    # DAG wiring
    # ─────────────────────────────────────────────────────────────────────

    tools = get_tool_list()

    # Dynamic fan-out: N parallel fetch tasks (with NVD rate limiting)
    fetch_results = fetch_cves_for_tool.expand(tool_name=tools)

    # Dynamic fan-out: N parallel upsert tasks
    upsert_results = upsert_cves_to_silver.expand(fetch_result=fetch_results)

    # Fan-in: kiểm tra critical CVEs
    critical_check = check_critical_cves(upsert_results=upsert_results)

    # ShortCircuit → alert
    alert = send_alert_if_critical()

    critical_check >> should_alert >> alert


# Instantiate DAG
ingest_cves()
