"""
DataStack Compass — DAG: Ingest Software Releases
==================================================

Thu thập Release Notes từ GitHub cho các tools trong Data Stack.
Lưu raw data vào Delta Lake bronze layer (s3a://bronze/bronze_raw_releases/).

Schedule : Hàng ngày lúc 02:00 AM UTC
Executor : Hoạt động trên cả LocalExecutor (dev) và CeleryExecutor (prod)
Idempotent: Có — mỗi lần chạy append dữ liệu mới, không xóa/ghi đè dữ liệu cũ.

Task Flow
---------
    check_connectivity
          │
          ▼
    fetch_releases  ──(dynamic map × N tools)
          │
          ▼
    trigger_processing  ──(dynamic map × N tools)
          │
          ▼
    send_summary
"""

from __future__ import annotations

import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

from airflow.decorators import dag, task
from airflow.exceptions import AirflowException

# ─── Đảm bảo project root nằm trên sys.path ────────────────────────────────
# Airflow mount DAGs tại /opt/airflow/dags (= ingestion/dags).
# Project root = 2 levels up → cho phép import processing.*, storage.*, etc.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

# =============================================================================
# Tool registry — hardcode ban đầu, sẽ đọc từ DB sau
# =============================================================================

TOOLS: List[Dict[str, str]] = [
    {"name": "apache-kafka",  "owner": "apache",    "repo": "kafka"},
    {"name": "apache-flink",  "owner": "apache",    "repo": "flink"},
    {"name": "apache-spark",  "owner": "apache",    "repo": "spark"},
    {"name": "delta-io",      "owner": "delta-io",  "repo": "delta"},
    {"name": "starrocks",     "owner": "StarRocks", "repo": "starrocks"},
]

# =============================================================================
# Default args — chung cho tất cả tasks trong DAG
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
# DAG definition
# =============================================================================

@dag(
    dag_id="ingest_software_releases",
    description="Thu thập Release Notes từ GitHub cho các Data Stack tools",
    schedule="0 2 * * *",           # Hàng ngày lúc 02:00 AM UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "releases"],
    default_args=_DEFAULT_ARGS,
    doc_md=__doc__,
)
def ingest_software_releases():
    """DAG chính: ingest release notes → bronze → trigger processing."""

    # ─────────────────────────────────────────────────────────────────────
    # Task 1: Kiểm tra kết nối trước khi crawl
    # ─────────────────────────────────────────────────────────────────────

    @task(task_id="check_connectivity")
    def check_connectivity() -> dict:
        """Kiểm tra kết nối MinIO (S3) và GitHub API.

        Raises
        ------
        AirflowException
            Nếu bất kỳ service nào không accessible.
        """
        import requests

        errors: List[str] = []

        # ── MinIO ────────────────────────────────────────────────────────
        minio_endpoint = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
        minio_health_url = f"{minio_endpoint}/minio/health/live"
        try:
            resp = requests.get(minio_health_url, timeout=10)
            if resp.status_code != 200:
                errors.append(
                    f"MinIO health check failed: HTTP {resp.status_code} at {minio_health_url}"
                )
            else:
                logger.info("✓ MinIO is healthy at %s", minio_endpoint)
        except requests.ConnectionError:
            errors.append(f"MinIO unreachable at {minio_health_url}")
        except requests.Timeout:
            errors.append(f"MinIO health check timed out at {minio_health_url}")

        # ── GitHub API ───────────────────────────────────────────────────
        github_url = "https://api.github.com/rate_limit"
        gh_headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            gh_headers["Authorization"] = f"Bearer {token}"

        try:
            resp = requests.get(github_url, headers=gh_headers, timeout=10)
            if resp.status_code != 200:
                errors.append(
                    f"GitHub API check failed: HTTP {resp.status_code}"
                )
            else:
                rate_info = resp.json().get("rate", {})
                remaining = rate_info.get("remaining", "?")
                limit = rate_info.get("limit", "?")
                logger.info(
                    "✓ GitHub API accessible — rate limit: %s/%s remaining",
                    remaining,
                    limit,
                )
                if isinstance(remaining, int) and remaining < len(TOOLS) * 2:
                    errors.append(
                        f"GitHub API rate limit too low: {remaining}/{limit} "
                        f"(need at least {len(TOOLS) * 2})"
                    )
        except requests.ConnectionError:
            errors.append("GitHub API unreachable")
        except requests.Timeout:
            errors.append("GitHub API request timed out")

        # ── Kết quả ─────────────────────────────────────────────────────
        if errors:
            error_msg = "Connectivity check FAILED:\n" + "\n".join(
                f"  ✗ {e}" for e in errors
            )
            logger.error(error_msg)
            raise AirflowException(error_msg)

        return {"status": "healthy", "tools_count": len(TOOLS)}

    # ─────────────────────────────────────────────────────────────────────
    # Task 2: Fetch releases (dynamic task mapping)
    # ─────────────────────────────────────────────────────────────────────

    @task(task_id="fetch_releases", retries=2, retry_delay=timedelta(minutes=3))
    def fetch_releases(tool: dict) -> dict:
        """Fetch releases từ GitHub và lưu vào Delta Lake bronze layer.

        Parameters
        ----------
        tool : dict
            Chứa keys: ``name``, ``owner``, ``repo``.

        Returns
        -------
        dict
            Summary: ``{tool_name, version, status, releases_count}``.
        """
        from ingestion.connectors.base_connector import (
            ConnectorError,
            GitHubReleaseConnector,
        )
        from processing.spark_utils.session import get_spark_session

        tool_name = tool["name"]
        owner = tool["owner"]
        repo = tool["repo"]

        logger.info("Fetching releases for %s (%s/%s)", tool_name, owner, repo)

        connector = GitHubReleaseConnector(owner=owner, repo=repo)

        try:
            # Lấy latest release (kèm list tất cả releases)
            data = connector.fetch_with_retry(
                tool_name=tool_name,
                version="latest",
                max_retries=3,
                backoff_factor=2.0,
            )
        except ConnectorError as exc:
            logger.error("Failed to fetch %s: %s", tool_name, exc)
            return {
                "tool_name": tool_name,
                "version": None,
                "status": "failed",
                "error": str(exc),
                "releases_count": 0,
            }

        # Lưu vào bronze layer
        spark = get_spark_session(f"ingest-{tool_name}")
        try:
            connector.save_to_bronze(
                spark=spark,
                data=data,
                tool_name=tool_name,
                source_type="github",
            )
        finally:
            spark.stop()

        releases_count = len(data.get("releases", []))
        latest_version = data.get("tag_name", "unknown")

        logger.info(
            "✓ %s: saved %d releases, latest=%s",
            tool_name,
            releases_count,
            latest_version,
        )

        return {
            "tool_name": tool_name,
            "version": latest_version,
            "status": "success",
            "releases_count": releases_count,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Task 3: Trigger downstream processing DAG
    # ─────────────────────────────────────────────────────────────────────

    @task(task_id="trigger_processing", trigger_rule="none_failed_min_one_success")
    def trigger_processing(result: dict) -> dict:
        """Trigger DAG 'process_releases' cho tool vừa ingest thành công.

        Parameters
        ----------
        result : dict
            Output từ ``fetch_releases``.

        Returns
        -------
        dict
            ``{tool_name, triggered}``.
        """
        from airflow.api.common.trigger_dag import trigger_dag

        tool_name = result["tool_name"]

        if result.get("status") != "success":
            logger.warning(
                "Skipping processing trigger for %s (status=%s)",
                tool_name,
                result.get("status"),
            )
            return {"tool_name": tool_name, "triggered": False}

        try:
            trigger_dag(
                dag_id="process_releases",
                conf={"tool_name": tool_name},
                replace_microseconds=False,
            )
            logger.info("✓ Triggered 'process_releases' for %s", tool_name)
            return {"tool_name": tool_name, "triggered": True}

        except Exception as exc:
            # Không fail DAG nếu downstream DAG chưa tồn tại
            logger.warning(
                "Could not trigger 'process_releases' for %s: %s",
                tool_name,
                exc,
            )
            return {"tool_name": tool_name, "triggered": False}

    # ─────────────────────────────────────────────────────────────────────
    # Task 4: Tổng kết
    # ─────────────────────────────────────────────────────────────────────

    @task(task_id="send_summary", trigger_rule="all_done")
    def send_summary(results: list) -> dict:
        """Log tổng kết số releases đã thu thập.

        Parameters
        ----------
        results : list[dict]
            List outputs từ ``trigger_processing``.

        Returns
        -------
        dict
            Summary statistics.
        """
        # Flatten — results có thể là list of list do dynamic mapping
        flat: List[dict] = []
        for item in results:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)

        triggered = [r for r in flat if r.get("triggered")]
        skipped = [r for r in flat if not r.get("triggered")]

        summary = {
            "total_tools": len(flat),
            "triggered": len(triggered),
            "skipped": len(skipped),
            "triggered_tools": [r["tool_name"] for r in triggered],
            "skipped_tools": [r["tool_name"] for r in skipped],
        }

        logger.info(
            "═══ Ingestion Summary ═══\n"
            "  Total tools : %d\n"
            "  Triggered   : %d (%s)\n"
            "  Skipped     : %d (%s)\n"
            "═════════════════════════",
            summary["total_tools"],
            summary["triggered"],
            ", ".join(summary["triggered_tools"]) or "none",
            summary["skipped"],
            ", ".join(summary["skipped_tools"]) or "none",
        )

        return summary

    # ─────────────────────────────────────────────────────────────────────
    # DAG wiring: linear → fan-out → fan-in
    # ─────────────────────────────────────────────────────────────────────

    connectivity = check_connectivity()

    # Dynamic task mapping: tạo N parallel fetch_releases tasks
    fetch_results = fetch_releases.expand(tool=TOOLS)

    # Trigger downstream processing cho từng tool
    trigger_results = trigger_processing.expand(result=fetch_results)

    # Tổng kết sau khi tất cả hoàn thành
    summary = send_summary(results=trigger_results)

    # Dependencies
    connectivity >> fetch_results  # noqa: W503


# Instantiate DAG
ingest_software_releases()
