import os
import smtplib
import requests
import pymysql
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from packaging.version import parse as parse_version

class AlertingService:
    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST', 'localhost')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        
        self.db_host = os.getenv('STARROCKS_HOST', '127.0.0.1')
        self.db_port = int(os.getenv('STARROCKS_PORT', 9030))
        self.db_user = os.getenv('STARROCKS_USER', 'root')
        self.db_password = os.getenv('STARROCKS_PASSWORD', '')
        self.db_name = os.getenv('STARROCKS_DB', 'datastack_compass')

    def _get_db_connection(self):
        return pymysql.connect(
            host=self.db_host,
            port=self.db_port,
            user=self.db_user,
            password=self.db_password,
            database=self.db_name,
            cursorclass=pymysql.cursors.DictCursor
        )

    def get_asset_inventory(self) -> list[dict]:
        """
        Query StarRocks to get the list of assets currently in use.
        """
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT tool_name, version_in_use, owner_email, team_name FROM asset_inventory")
                    return cursor.fetchall()
        except Exception as e:
            print(f"Error fetching asset inventory: {e}")
            return []

    def _match_single_version(self, version_in_use: str, affected_version: str) -> bool:
        """
        Perform semantic version matching between the version in use and the affected version string.
        """
        affected_version = affected_version.strip()
        op = "=="
        val = affected_version
        
        for operator in ["<=", ">=", "==", "<", ">"]:
            if affected_version.startswith(operator):
                op = operator
                val = affected_version[len(operator):].strip()
                break
        
        if op == "==" and not affected_version.startswith("=="):
            val = affected_version

        try:
            v_use = parse_version(version_in_use)
            v_aff = parse_version(val)
            
            if op == "==": return v_use == v_aff
            if op == "<=": return v_use <= v_aff
            if op == ">=": return v_use >= v_aff
            if op == "<": return v_use < v_aff
            if op == ">": return v_use > v_aff
        except Exception:
            # Fallback to direct string comparison if parsing fails
            return version_in_use == val

        return False

    def match_cves_to_assets(self, new_cves: list, assets: list) -> list[dict]:
        """
        Cross-match CVE affected_versions vs version_in_use of each asset.
        Returns a list of matches: {cve, asset, is_critical: bool}
        """
        matches = []
        for asset in assets:
            for cve in new_cves:
                if asset.get('tool_name', '').lower() == cve.get('tool_name', '').lower():
                    for aff_ver in cve.get('affected_versions', []):
                        if self._match_single_version(asset.get('version_in_use', ''), aff_ver):
                            severity = str(cve.get('severity', '')).lower()
                            cvss = float(cve.get('cvss', 0.0))
                            is_critical = severity in ['critical', 'high'] or cvss >= 7.0
                            
                            matches.append({
                                'cve': cve,
                                'asset': asset,
                                'is_critical': is_critical
                            })
                            break  # Only need to match one affected version range per CVE/asset pair
        return matches

    def send_email_alert(self, matches: list):
        """
        Create and send an HTML email report of the detected vulnerabilities.
        """
        if not matches:
            return

        critical_count = sum(1 for m in matches if m['is_critical'])
        subject = f"[DataStack Compass] {critical_count} Critical CVEs Detected"
        
        table_rows = ""
        cc_emails = set()
        
        for m in matches:
            asset = m['asset']
            cve = m['cve']
            if asset.get('owner_email'):
                cc_emails.add(asset['owner_email'])
            
            table_rows += f'''
            <tr>
                <td>{asset.get('tool_name', '')}</td>
                <td>{asset.get('version_in_use', '')}</td>
                <td>{cve.get('cve_id', '')}</td>
                <td>{cve.get('cvss', '')}</td>
                <td>{cve.get('severity', '')}</td>
                <td>{cve.get('fix_version', '')}</td>
            </tr>
            '''
            
        html_content = f'''
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #e11d48;">CVE Alert Report</h2>
            <p>New vulnerabilities affecting your infrastructure have been detected:</p>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                <tr style="background-color: #f8fafc; text-align: left;">
                    <th>Tool</th>
                    <th>Version in Use</th>
                    <th>CVE ID</th>
                    <th>CVSS</th>
                    <th>Severity</th>
                    <th>Fix Version</th>
                </tr>
                {table_rows}
            </table>
        </body>
        </html>
        '''

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.smtp_user if self.smtp_user else "alert@datastack-compass.local"
        msg['To'] = "security@datastack-compass.local"
        
        if cc_emails:
            msg['Cc'] = ", ".join(cc_emails)
            
        msg.attach(MIMEText(html_content, 'html'))
        
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                
                all_recipients = [msg['To']] + list(cc_emails)
                server.sendmail(msg['From'], all_recipients, msg.as_string())
        except Exception as e:
            print(f"Failed to send email alert: {e}")

    def send_webhook(self, matches: list, webhook_url: str):
        """
        POST a JSON payload to a webhook URL (Slack incoming webhook format).
        """
        if not matches:
            return

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 DataStack Compass Alert: {len(matches)} New CVEs Detected"
                }
            },
            {
                "type": "divider"
            }
        ]
        
        for m in matches:
            asset = m['asset']
            cve = m['cve']
            emoji = "🔴" if m['is_critical'] else "🟡"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *{cve.get('cve_id', 'Unknown CVE')}* in *{asset.get('tool_name', '')}*\n"
                            f"• *Version in use:* {asset.get('version_in_use', '')} | *CVSS:* {cve.get('cvss', '')} ({cve.get('severity', '')})\n"
                            f"• *Fix available:* {cve.get('fix_version', 'N/A')}\n"
                            f"• *Owner:* {asset.get('team_name', '')} (<mailto:{asset.get('owner_email', '')}|{asset.get('owner_email', '')}>)"
                }
            })
            
        payload = {"blocks": blocks}
        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to send webhook: {e}")
