"""
DataStack Compass — DAG: Ingest Tech Blogs
==========================================

Thu thập RSS/Atom feed từ các blog công nghệ, lọc và lưu vào silver_blogs.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta

from airflow.decorators import dag, task

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ingestion.connectors.blog_connector import TechBlogConnector

logger = logging.getLogger(__name__)

default_args = {
    "owner": "data_platform",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

@dag(
    dag_id="ingest_tech_blogs",
    default_args=default_args,
    schedule="0 8 * * 1",  # Thứ Hai hàng tuần
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["compass", "ingestion", "blogs"],
)
def dag_ingest_blogs():
    
    @task
    def fetch_and_upsert_blogs() -> list[str]:
        """Fetch RSS feeds and upsert directly to silver_blogs."""
        from processing.spark_utils.session import get_spark_session
        from storage.delta.schemas import SCHEMAS
        
        # Lấy danh sách tools từ FEEDS của connector
        tools = list(TechBlogConnector.FEEDS.keys())
        connector = TechBlogConnector()
        
        all_entries = []
        
        for tool in tools:
            try:
                # "latest" means do not filter by a specific version strictly, just get recent
                data = connector.fetch_with_retry(tool_name=tool, version="")
                entries = data.get("entries", [])
                logger.info(f"Fetched {len(entries)} blog posts for {tool}")
                
                for entry in entries:
                    all_entries.append({
                        "tool_name": tool,
                        "title": entry["title"],
                        "url": entry["url"],
                        "published_date": datetime.fromisoformat(entry["published_date"]) if entry["published_date"] else datetime.now(),
                        "summary": entry["summary"][:1000] if entry["summary"] else "", # limit summary length
                        "tags": entry["tags"],
                        "source_feed": entry["source_feed"]
                    })
                    
            except Exception as e:
                logger.error(f"Failed to fetch blogs for {tool}: {e}")
                
        if not all_entries:
            logger.warning("No blogs fetched across all tools.")
            return []
            
        spark = get_spark_session("ingest_blogs")
        schema = SCHEMAS["silver_blogs"]
        
        df = spark.createDataFrame(all_entries, schema=schema)
        
        bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
        table_path = f"s3a://{bucket}/silver_blogs/"
        
        # Upsert by URL
        try:
            from delta.tables import DeltaTable
            if DeltaTable.isDeltaTable(spark, table_path):
                dt = DeltaTable.forPath(spark, table_path)
                dt.alias("t").merge(
                    df.alias("s"),
                    "t.url = s.url"
                ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
                logger.info(f"Merged {df.count()} blog posts into silver_blogs")
            else:
                df.write.format("delta").mode("overwrite").save(table_path)
                logger.info(f"Created silver_blogs table with {df.count()} rows")
        except Exception as e:
            logger.warning(f"Merge failed, trying overwrite/append: {e}")
            df.write.format("delta").mode("append").save(table_path)
            
        spark.stop()
        return tools

    @task
    def run_data_quality(tools: list[str]):
        """Run Great Expectations suite on the ingested data."""
        if not tools:
            logger.info("No tools to validate.")
            return
            
        from processing.spark_utils.session import get_spark_session
        from processing.great_expectations.suites.blog_suite import SilverBlogsSuite
        
        spark = get_spark_session("dq_blogs")
        suite = SilverBlogsSuite(raise_on_failure=False)
        
        for tool in tools:
            try:
                suite.run(spark, tool_name=tool)
            except Exception as e:
                logger.error(f"DQ failed for {tool}: {e}")
                
        spark.stop()

    # Flow
    fetched_tools = fetch_and_upsert_blogs()
    run_data_quality(fetched_tools)

dag_obj = dag_ingest_blogs()
