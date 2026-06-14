"""
Jira Release Connector
======================

Connector gọi Jira REST API để lấy các issues (Bug, Feature, Improvement) 
cho một project và version cụ thể.
"""

from __future__ import annotations

import base64
import os
import logging
from typing import Dict

import requests
from ingestion.connectors.base_connector import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

class JiraReleaseConnector(BaseConnector):
    """Connector cho Jira REST API v3.
    
    Đọc JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN từ environment variables.
    """
    def __init__(self, project_key: str):
        self.project_key = project_key
        self.base_url = os.environ.get("JIRA_BASE_URL", "https://issues.apache.org/jira").rstrip("/")
        self.email = os.environ.get("JIRA_EMAIL", "")
        self.token = os.environ.get("JIRA_API_TOKEN", "")
        
    @property
    def headers(self) -> Dict[str, str]:
        h = super().headers.copy()
        if self.email and self.token:
            auth_str = f"{self.email}:{self.token}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            h["Authorization"] = f"Basic {b64_auth}"
        return h

    def fetch(self, tool_name: str, version: str) -> dict:
        """Lấy danh sách Jira issues theo version.
        
        Sử dụng JQL: project={project} AND issuetype in (Bug, "New Feature", Improvement) AND fixVersion={version}
        """
        # Format JQL
        jql = f'project="{self.project_key}" AND issuetype in (Bug, "New Feature", Improvement) AND fixVersion="{version}"'
        
        params = {
            "jql": jql,
            "maxResults": 100,
            "fields": "summary,issuetype,status,fixVersions"
        }
        
        url = f"{self.base_url}/rest/api/3/search"
        logger.info(f"Fetching Jira issues for {self.project_key} version {version}")
        
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        
        if resp.status_code >= 400:
            raise ConnectorError(
                f"Jira API error: {resp.status_code} {resp.text}",
                status_code=resp.status_code,
                url=url
            )
            
        data = resp.json()
        
        issues = []
        for item in data.get("issues", []):
            issue_id = item.get("key")
            fields = item.get("fields", {})
            summary = fields.get("summary", "")
            
            raw_type = fields.get("issuetype", {}).get("name", "")
            if raw_type == "New Feature":
                issue_type = "Feature"
            elif raw_type == "Bug":
                issue_type = "Bug"
            else:
                issue_type = "Improvement"
                
            status = fields.get("status", {}).get("name", "")
            fix_versions = [v.get("name") for v in fields.get("fixVersions", [])]
            issue_url = f"{self.base_url}/browse/{issue_id}"
            
            issues.append({
                "id": issue_id,
                "summary": summary,
                "type": issue_type,
                "status": status,
                "fixVersions": fix_versions,
                "url": issue_url
            })
            
        return {
            "tool_name": tool_name,
            "version": version,
            "issues": issues,
            "source_url": f"{self.base_url}/issues/?jql={requests.utils.quote(jql)}"
        }
