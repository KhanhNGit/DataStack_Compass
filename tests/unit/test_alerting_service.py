import pytest
from unittest.mock import patch, MagicMock
from api.services.alerting_service import AlertingService

@pytest.fixture
def alerting_service():
    return AlertingService()

def test_match_cves_to_assets_exact_match(alerting_service):
    assets = [
        {"tool_name": "apache-kafka", "version_in_use": "3.5.0", "owner_email": "data@corp.com", "team_name": "Data Team"}
    ]
    new_cves = [
        {
            "cve_id": "CVE-2023-1234",
            "tool_name": "apache-kafka",
            "affected_versions": ["3.5.0"],
            "cvss": 8.5,
            "severity": "High",
            "fix_version": "3.5.1"
        }
    ]
    
    matches = alerting_service.match_cves_to_assets(new_cves, assets)
    
    assert len(matches) == 1
    assert matches[0]['cve']['cve_id'] == "CVE-2023-1234"
    assert matches[0]['is_critical'] is True

def test_match_cves_to_assets_range_match(alerting_service):
    assets = [
        {"tool_name": "apache-spark", "version_in_use": "3.3.0", "owner_email": "ml@corp.com", "team_name": "ML Team"}
    ]
    new_cves = [
        {
            "cve_id": "CVE-2024-5678",
            "tool_name": "apache-spark",
            "affected_versions": ["<= 3.3.2"],
            "cvss": 5.0,
            "severity": "Medium",
            "fix_version": "3.3.3"
        }
    ]
    
    matches = alerting_service.match_cves_to_assets(new_cves, assets)
    
    assert len(matches) == 1
    assert matches[0]['is_critical'] is False

def test_match_cves_to_assets_no_match(alerting_service):
    assets = [
        {"tool_name": "apache-flink", "version_in_use": "1.18.0", "owner_email": "stream@corp.com", "team_name": "Stream Team"}
    ]
    new_cves = [
        {
            "cve_id": "CVE-2024-9999",
            "tool_name": "apache-flink",
            "affected_versions": ["< 1.17.0"],
            "cvss": 9.0,
            "severity": "Critical",
            "fix_version": "1.17.1"
        }
    ]
    
    matches = alerting_service.match_cves_to_assets(new_cves, assets)
    
    assert len(matches) == 0

@patch('api.services.alerting_service.smtplib.SMTP')
def test_send_email_alert(mock_smtp, alerting_service):
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server
    
    matches = [
        {
            "cve": {"cve_id": "CVE-TEST", "cvss": 9.8, "severity": "Critical", "fix_version": "2.0.0"},
            "asset": {"tool_name": "TestTool", "version_in_use": "1.0.0", "owner_email": "owner@corp.com", "team_name": "Test Team"},
            "is_critical": True
        }
    ]
    
    alerting_service.send_email_alert(matches)
    
    mock_smtp.assert_called_once()
    mock_server.sendmail.assert_called_once()
    
    # Check if owner email is included in the recipient list
    args, kwargs = mock_server.sendmail.call_args
    assert "owner@corp.com" in args[1] # args[1] is the recipient list

@patch('api.services.alerting_service.requests.post')
def test_send_webhook(mock_post, alerting_service):
    matches = [
        {
            "cve": {"cve_id": "CVE-WEBHOOK", "cvss": 5.5, "severity": "Medium", "fix_version": "2.0.0"},
            "asset": {"tool_name": "TestTool", "version_in_use": "1.0.0", "owner_email": "owner@corp.com", "team_name": "Test Team"},
            "is_critical": False
        }
    ]
    
    mock_post.return_value.raise_for_status = MagicMock()
    
    alerting_service.send_webhook(matches, "http://fake-webhook.url")
    
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://fake-webhook.url"
    assert "blocks" in kwargs['json']
    assert len(kwargs['json']['blocks']) > 0
    
    # Check payload content
    payload_text = str(kwargs['json']['blocks'])
    assert "CVE-WEBHOOK" in payload_text
    assert "TestTool" in payload_text
