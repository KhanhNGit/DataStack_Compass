"""
Blog Connector
==============

Connector sử dụng feedparser để đọc RSS/Atom feed từ các trang blog công nghệ.
"""

from __future__ import annotations

import logging
from datetime import datetime
import time

import feedparser
from ingestion.connectors.base_connector import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

class TechBlogConnector(BaseConnector):
    """Connector cho RSS/Atom feeds.
    
    Yêu cầu thư viện: feedparser
    """
    
    FEEDS = {
        "apache-kafka": "https://kafka.apache.org/blog.atom",
        "apache-flink": "https://flink.apache.org/atom.xml",
        "apache-spark": "https://spark.apache.org/news/index.xml",
    }
    
    def fetch(self, tool_name: str, version: str) -> dict:
        """Đọc và filter RSS feed cho một tool.
        
        Note: tham số `version` ở đây có thể là string rỗng nếu ta chỉ
        muốn lấy blog post mới nhất mà không phụ thuộc phiên bản.
        Nếu truyền vào version, bộ lọc sẽ tìm kiếm từ khóa version trong text.
        """
        url = self.FEEDS.get(tool_name)
        if not url:
            raise ConnectorError(f"Không có feed URL cho {tool_name}")
            
        logger.info(f"Parsing RSS feed from {url}")
        feed = feedparser.parse(url)
        
        if feed.bozo and getattr(feed.bozo_exception, 'getMessage', lambda: '')():
            logger.warning(f"Feed parser bozo exception: {feed.bozo_exception}")
            # Nếu hoàn toàn không thể parse, bozo sẽ throw errors. Tuy nhiên RSS feed
            # thường vẫn parse được một phần dữ liệu dẫu sai cấu trúc.
        
        entries = []
        for entry in feed.entries:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            link = entry.get("link", "")
            
            # Extract datetime
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            if published_parsed:
                published_date = datetime.fromtimestamp(time.mktime(published_parsed)).isoformat()
            else:
                published_date = datetime.now().isoformat()
                
            tags = [t.get("term") for t in entry.get("tags", []) if t.get("term")]
            
            # Lọc nội dung nếu version != ""
            # Filter entries có chứa keyword từ tool_name hoặc version trong title/description
            text_to_search = (title + " " + summary).lower()
            
            if version and version != "latest":
                if version.lower() not in text_to_search:
                    continue
                    
            entries.append({
                "title": title,
                "url": link,
                "published_date": published_date,
                "summary": summary,
                "tags": tags,
                "source_feed": url
            })
            
        return {
            "tool_name": tool_name,
            "version": version,
            "entries": entries,
            "source_url": url
        }
