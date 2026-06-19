from ingestion.connectors.base_connector import BaseConnector, GitHubReleaseConnector
from ingestion.connectors.jira_connector import JiraReleaseConnector
# from ingestion.connectors.blog_connector import TechBlogConnector

class ConnectorFactory:
    """Factory để trả về đúng Connector dựa trên source_type cấu hình trong DAG."""
    
    @staticmethod
    def get_connector(tool_config: dict) -> BaseConnector:
        source_type = tool_config.get("source_type", "github")
        
        if source_type == "github":
            return GitHubReleaseConnector(
                owner=tool_config["owner"],
                repo=tool_config["repo"]
            )
            
        elif source_type == "jira":
            return JiraReleaseConnector(
                project_key=tool_config["project_key"]
            )
            
        elif source_type == "custom":
            # Chỗ trống (Placeholder) cho Custom Connectors tương lai.
            # Có thể nạp module động dựa vào một key trong config.
            raise NotImplementedError("Custom connectors have not been implemented yet.")
            
        # Các logic phân phối cho blog hoặc compatibility có thể được nối vào đây nếu cần,
        # mặc dù chúng thường có DAG riêng (VD: dag_ingest_blogs.py).
            
        raise ValueError(f"Unknown source_type: {source_type}")
