"""
Deployment report generator.

Generates HTML, CSV, and JSON reports for deployment activities.
"""

import csv
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader, BaseLoader

from ..config import get_config


@dataclass
class DeploymentRecord:
    """Record of a deployment activity."""
    timestamp: str
    app_name: str
    app_id: Optional[str] = None
    version: Optional[str] = None
    source_file: Optional[str] = None
    package_file: Optional[str] = None
    status: str = "unknown"
    upload_time_seconds: Optional[float] = None
    error_message: Optional[str] = None
    publisher: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "DeploymentRecord":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Default HTML report template
DEFAULT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Intune Deployment Report</title>
    <style>
        :root {
            --primary: #0078d4;
            --success: #107c10;
            --error: #d13438;
            --warning: #ff8c00;
            --bg-dark: #1e1e1e;
            --bg-card: #252526;
            --text: #cccccc;
            --text-bright: #ffffff;
            --border: #3c3c3c;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, var(--bg-dark) 0%, #2d2d30 100%);
            color: var(--text);
            min-height: 100vh;
            padding: 2rem;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 3rem;
        }
        
        h1 {
            color: var(--text-bright);
            font-size: 2.5rem;
            font-weight: 300;
            margin-bottom: 0.5rem;
        }
        
        .subtitle {
            color: var(--primary);
            font-size: 1.1rem;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }
        
        .stat-card {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 1.5rem;
            text-align: center;
            border: 1px solid var(--border);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        }
        
        .stat-value {
            font-size: 2.5rem;
            font-weight: 600;
            color: var(--text-bright);
        }
        
        .stat-label {
            color: var(--text);
            font-size: 0.9rem;
            margin-top: 0.5rem;
        }
        
        .stat-card.success .stat-value { color: var(--success); }
        .stat-card.error .stat-value { color: var(--error); }
        .stat-card.primary .stat-value { color: var(--primary); }
        
        .table-container {
            background: var(--bg-card);
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--border);
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th, td {
            padding: 1rem 1.25rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        
        th {
            background: rgba(0,120,212,0.1);
            color: var(--primary);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.8rem;
            letter-spacing: 0.5px;
        }
        
        tr:hover {
            background: rgba(255,255,255,0.03);
        }
        
        .status-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
        }
        
        .status-success {
            background: rgba(16,124,16,0.2);
            color: var(--success);
        }
        
        .status-failed {
            background: rgba(209,52,56,0.2);
            color: var(--error);
        }
        
        .status-pending {
            background: rgba(255,140,0,0.2);
            color: var(--warning);
        }
        
        .app-id {
            font-family: 'Consolas', monospace;
            font-size: 0.8rem;
            color: var(--text);
        }
        
        footer {
            text-align: center;
            margin-top: 3rem;
            color: var(--text);
            font-size: 0.9rem;
        }
        
        .empty-state {
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text);
        }
        
        .empty-state h3 {
            color: var(--text-bright);
            margin-bottom: 1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📦 Intune Deployment Report</h1>
            <p class="subtitle">Generated on {{ generated_at }}</p>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card primary">
                <div class="stat-value">{{ total_deployments }}</div>
                <div class="stat-label">Total Deployments</div>
            </div>
            <div class="stat-card success">
                <div class="stat-value">{{ successful_deployments }}</div>
                <div class="stat-label">Successful</div>
            </div>
            <div class="stat-card error">
                <div class="stat-value">{{ failed_deployments }}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ avg_upload_time }}s</div>
                <div class="stat-label">Avg Upload Time</div>
            </div>
        </div>
        
        <div class="table-container">
            {% if records %}
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Application</th>
                        <th>Version</th>
                        <th>Status</th>
                        <th>App ID</th>
                        <th>Upload Time</th>
                    </tr>
                </thead>
                <tbody>
                    {% for record in records %}
                    <tr>
                        <td>{{ record.timestamp }}</td>
                        <td><strong>{{ record.app_name }}</strong></td>
                        <td>{{ record.version or '-' }}</td>
                        <td>
                            <span class="status-badge status-{{ 'success' if record.status == 'success' else 'failed' if record.status == 'failed' else 'pending' }}">
                                {{ record.status | upper }}
                            </span>
                        </td>
                        <td class="app-id">{{ record.app_id or '-' }}</td>
                        <td>{{ record.upload_time_seconds | round(1) if record.upload_time_seconds else '-' }}s</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty-state">
                <h3>No Deployments Yet</h3>
                <p>Run the packager to see deployment records here.</p>
            </div>
            {% endif %}
        </div>
        
        <footer>
            <p>Intune Packager &copy; {{ year }} | Enterprise Software Packaging Automation</p>
        </footer>
    </div>
</body>
</html>
"""


class ReportGenerator:
    """Generates deployment reports."""
    
    def __init__(self, history_file: Optional[str] = None):
        """
        Initialize report generator.
        
        Args:
            history_file: Optional path to deployment history JSON file
        """
        config = get_config()
        self.history_file = Path(
            history_file or config.get("reporting.history_file", "./deployment_history.json")
        )
        self.output_dir = Path(config.get("reporting.output_dir", "./reports"))
        self._records: List[DeploymentRecord] = []
        self._load_history()
    
    def _load_history(self) -> None:
        """Load deployment history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    self._records = [
                        DeploymentRecord.from_dict(r) for r in data.get("records", [])
                    ]
            except Exception:
                self._records = []
    
    def _save_history(self) -> None:
        """Save deployment history to file."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, 'w') as f:
            json.dump({
                "records": [r.to_dict() for r in self._records],
                "last_updated": datetime.now().isoformat(),
            }, f, indent=2)
    
    def add_record(self, record: DeploymentRecord) -> None:
        """
        Add a deployment record.
        
        Args:
            record: DeploymentRecord to add
        """
        self._records.append(record)
        self._save_history()
    
    def create_record(
        self,
        app_name: str,
        status: str,
        app_id: Optional[str] = None,
        **kwargs
    ) -> DeploymentRecord:
        """
        Create and add a new deployment record.
        
        Args:
            app_name: Application name
            status: Deployment status
            app_id: Optional app ID
            **kwargs: Additional record fields
            
        Returns:
            Created DeploymentRecord
        """
        record = DeploymentRecord(
            timestamp=datetime.now().isoformat(),
            app_name=app_name,
            app_id=app_id,
            status=status,
            **kwargs
        )
        self.add_record(record)
        return record
    
    def get_records(
        self,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[DeploymentRecord]:
        """
        Get deployment records.
        
        Args:
            status: Optional status filter
            limit: Optional limit on number of records
            
        Returns:
            List of DeploymentRecord
        """
        records = self._records
        
        if status:
            records = [r for r in records if r.status == status]
        
        # Sort by timestamp descending
        records = sorted(records, key=lambda r: r.timestamp, reverse=True)
        
        if limit:
            records = records[:limit]
        
        return records
    
    def get_statistics(self) -> dict:
        """Get deployment statistics."""
        total = len(self._records)
        successful = len([r for r in self._records if r.status == "success"])
        failed = len([r for r in self._records if r.status == "failed"])
        
        upload_times = [
            r.upload_time_seconds for r in self._records
            if r.upload_time_seconds is not None
        ]
        avg_time = sum(upload_times) / len(upload_times) if upload_times else 0
        
        return {
            "total_deployments": total,
            "successful_deployments": successful,
            "failed_deployments": failed,
            "avg_upload_time": round(avg_time, 1),
        }
    
    def generate_html(self, output_path: Optional[str] = None) -> Path:
        """
        Generate HTML report.
        
        Args:
            output_path: Optional output file path
            
        Returns:
            Path to generated report
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = Path(output_path) if output_path else self.output_dir / "report.html"
        
        # Use Jinja2 with string template
        env = Environment(loader=BaseLoader())
        template = env.from_string(DEFAULT_TEMPLATE)
        
        stats = self.get_statistics()
        records = self.get_records()
        
        html = template.render(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            year=datetime.now().year,
            records=records,
            **stats
        )
        
        output_path.write_text(html, encoding='utf-8')
        return output_path
    
    def generate_csv(self, output_path: Optional[str] = None) -> Path:
        """
        Generate CSV report.
        
        Args:
            output_path: Optional output file path
            
        Returns:
            Path to generated report
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = Path(output_path) if output_path else self.output_dir / "report.csv"
        
        records = self.get_records()
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            if records:
                writer = csv.DictWriter(f, fieldnames=records[0].to_dict().keys())
                writer.writeheader()
                for record in records:
                    writer.writerow(record.to_dict())
        
        return output_path
    
    def generate_json(self, output_path: Optional[str] = None) -> Path:
        """
        Generate JSON report.
        
        Args:
            output_path: Optional output file path
            
        Returns:
            Path to generated report
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = Path(output_path) if output_path else self.output_dir / "report.json"
        
        records = self.get_records()
        stats = self.get_statistics()
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "statistics": stats,
            "records": [r.to_dict() for r in records],
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        
        return output_path
    
    def generate(
        self,
        format: str = "html",
        output_path: Optional[str] = None,
    ) -> Path:
        """
        Generate report in specified format.
        
        Args:
            format: Report format (html, csv, json)
            output_path: Optional output file path
            
        Returns:
            Path to generated report
        """
        format = format.lower()
        
        if format == "html":
            return self.generate_html(output_path)
        elif format == "csv":
            return self.generate_csv(output_path)
        elif format == "json":
            return self.generate_json(output_path)
        else:
            raise ValueError(f"Unsupported format: {format}. Use html, csv, or json.")
