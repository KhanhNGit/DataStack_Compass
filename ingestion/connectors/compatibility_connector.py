"""
Compatibility Matrix Connector
==============================

Đọc cấu hình tĩnh từ configs/compatibility_matrices hoặc scrape trang web.
"""

from __future__ import annotations

import json
import os
import logging
import sys

from ingestion.connectors.base_connector import BaseConnector, HttpConnector, ConnectorError

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

class CompatibilityMatrixConnector(BaseConnector):
    """Connector đọc thông tin độ tương thích.
    
    Ưu tiên đọc file JSON tĩnh từ `configs/compatibility_matrices/{tool_name}.json`.
    Nếu không có, fallback sang dùng BaseConnector/HttpConnector.
    """
    
    def __init__(self, fallback_url: str = ""):
        self.fallback_url = fallback_url
        if fallback_url:
            self._http_client = HttpConnector(base_url=fallback_url)
        else:
            self._http_client = None

    def fetch(self, tool_name: str, version: str) -> dict:
        """Đọc thông tin ma trận tương thích."""
        
        static_file = os.path.join(_PROJECT_ROOT, "configs", "compatibility_matrices", f"{tool_name}.json")
        
        if os.path.exists(static_file):
            logger.info(f"Reading compatibility matrix from static file: {static_file}")
            try:
                with open(static_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                # Format: {"version": "3.6.0", "java_min": "11", "scala": "2.12|2.13", "dependencies": {...}}
                # Lọc ra đúng phiên bản hoặc dùng chung. 
                # Nếu static JSON là array của nhiều versions:
                if isinstance(data, list):
                    for item in data:
                        # so sánh prefix
                        if item.get("version", "").startswith(version) or version == "latest":
                            bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
                            item["source_url"] = f"s3a://{bucket}/configs/compatibility_matrices/{tool_name}.json"
                            return item
                elif isinstance(data, dict):
                    bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
                    data["source_url"] = f"s3a://{bucket}/configs/compatibility_matrices/{tool_name}.json"
                    return data
                    
            except Exception as e:
                logger.warning(f"Failed to parse JSON {static_file}: {e}")
                
        # Fallback Web Scrape
        if self._http_client:
            logger.info(f"Fallback to HTTP fetch for {tool_name} compatibility")
            return self._http_client.fetch(tool_name, version)
            
        raise ConnectorError(f"No compatibility matrix found for {tool_name} {version} and no fallback URL provided.")
