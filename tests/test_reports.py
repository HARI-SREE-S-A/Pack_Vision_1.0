"""
Tests for report generator module.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from intune_packager.reports.generator import (
    ReportGenerator,
    DeploymentRecord,
)


class TestDeploymentRecord:
    """Tests for DeploymentRecord dataclass."""
    
    def test_create_record(self):
        """Test creating a deployment record."""
        record = DeploymentRecord(
            timestamp="2024-01-15T10:30:00",
            app_name="Test App",
            app_id="12345",
            status="success",
        )
        
        assert record.app_name == "Test App"
        assert record.app_id == "12345"
        assert record.status == "success"
    
    def test_to_dict(self):
        """Test record serialization."""
        record = DeploymentRecord(
            timestamp="2024-01-15T10:30:00",
            app_name="Test App",
            status="success",
            upload_time_seconds=45.5,
        )
        
        result = record.to_dict()
        
        assert isinstance(result, dict)
        assert result["app_name"] == "Test App"
        assert result["upload_time_seconds"] == 45.5
    
    def test_from_dict(self):
        """Test record deserialization."""
        data = {
            "timestamp": "2024-01-15T10:30:00",
            "app_name": "Test App",
            "app_id": "abc123",
            "status": "failed",
            "error_message": "Connection timeout",
        }
        
        record = DeploymentRecord.from_dict(data)
        
        assert record.app_name == "Test App"
        assert record.app_id == "abc123"
        assert record.status == "failed"
        assert record.error_message == "Connection timeout"
    
    def test_from_dict_ignores_extra_fields(self):
        """Test that extra fields are ignored."""
        data = {
            "timestamp": "2024-01-15T10:30:00",
            "app_name": "Test App",
            "status": "success",
            "extra_field": "should be ignored",
        }
        
        record = DeploymentRecord.from_dict(data)
        assert record.app_name == "Test App"


class TestReportGenerator:
    """Tests for ReportGenerator class."""
    
    @pytest.fixture
    def temp_history_file(self, tmp_path):
        """Create a temporary history file."""
        return tmp_path / "history.json"
    
    @pytest.fixture
    def generator(self, temp_history_file):
        """Create a report generator with temp file."""
        return ReportGenerator(history_file=str(temp_history_file))
    
    def test_create_record(self, generator):
        """Test creating and storing a record."""
        record = generator.create_record(
            app_name="Test App",
            status="success",
            app_id="12345",
        )
        
        assert record.app_name == "Test App"
        assert record.status == "success"
        assert record.app_id == "12345"
        assert record.timestamp  # Should have timestamp
    
    def test_get_records(self, generator):
        """Test retrieving records."""
        generator.create_record(app_name="App 1", status="success")
        generator.create_record(app_name="App 2", status="failed")
        
        records = generator.get_records()
        
        assert len(records) == 2
    
    def test_get_records_filtered_by_status(self, generator):
        """Test filtering records by status."""
        generator.create_record(app_name="App 1", status="success")
        generator.create_record(app_name="App 2", status="failed")
        generator.create_record(app_name="App 3", status="success")
        
        successful = generator.get_records(status="success")
        failed = generator.get_records(status="failed")
        
        assert len(successful) == 2
        assert len(failed) == 1
    
    def test_get_records_limited(self, generator):
        """Test limiting number of records."""
        for i in range(5):
            generator.create_record(app_name=f"App {i}", status="success")
        
        records = generator.get_records(limit=3)
        
        assert len(records) == 3
    
    def test_get_statistics(self, generator):
        """Test getting deployment statistics."""
        generator.create_record(app_name="App 1", status="success", upload_time_seconds=30.0)
        generator.create_record(app_name="App 2", status="success", upload_time_seconds=40.0)
        generator.create_record(app_name="App 3", status="failed")
        
        stats = generator.get_statistics()
        
        assert stats["total_deployments"] == 3
        assert stats["successful_deployments"] == 2
        assert stats["failed_deployments"] == 1
        assert stats["avg_upload_time"] == 35.0
    
    def test_generate_html(self, generator, tmp_path):
        """Test HTML report generation."""
        generator.create_record(app_name="Test App", status="success")
        
        output = generator.generate_html(str(tmp_path / "report.html"))
        
        assert output.exists()
        content = output.read_text()
        assert "Test App" in content
        assert "Deployment Report" in content
    
    def test_generate_csv(self, generator, tmp_path):
        """Test CSV report generation."""
        generator.create_record(app_name="Test App", status="success", app_id="123")
        
        output = generator.generate_csv(str(tmp_path / "report.csv"))
        
        assert output.exists()
        content = output.read_text()
        assert "Test App" in content
        assert "success" in content
    
    def test_generate_json(self, generator, tmp_path):
        """Test JSON report generation."""
        generator.create_record(app_name="Test App", status="success")
        
        output = generator.generate_json(str(tmp_path / "report.json"))
        
        assert output.exists()
        
        with open(output) as f:
            data = json.load(f)
        
        assert "records" in data
        assert "statistics" in data
        assert len(data["records"]) == 1
        assert data["records"][0]["app_name"] == "Test App"
    
    def test_generate_with_format(self, generator, tmp_path):
        """Test generate method with different formats."""
        generator.create_record(app_name="Test", status="success")
        
        html = generator.generate(format="html", output_path=str(tmp_path / "r.html"))
        assert html.suffix == ".html"
        
        csv = generator.generate(format="csv", output_path=str(tmp_path / "r.csv"))
        assert csv.suffix == ".csv"
        
        js = generator.generate(format="json", output_path=str(tmp_path / "r.json"))
        assert js.suffix == ".json"
    
    def test_generate_invalid_format(self, generator):
        """Test that invalid format raises error."""
        with pytest.raises(ValueError, match="Unsupported format"):
            generator.generate(format="pdf")
    
    def test_history_persistence(self, temp_history_file):
        """Test that history persists across instances."""
        # Create first generator and add records
        gen1 = ReportGenerator(history_file=str(temp_history_file))
        gen1.create_record(app_name="App 1", status="success")
        gen1.create_record(app_name="App 2", status="failed")
        
        # Create second generator with same file
        gen2 = ReportGenerator(history_file=str(temp_history_file))
        records = gen2.get_records()
        
        assert len(records) == 2
    
    def test_empty_statistics(self, generator):
        """Test statistics with no records."""
        stats = generator.get_statistics()
        
        assert stats["total_deployments"] == 0
        assert stats["successful_deployments"] == 0
        assert stats["failed_deployments"] == 0
        assert stats["avg_upload_time"] == 0
