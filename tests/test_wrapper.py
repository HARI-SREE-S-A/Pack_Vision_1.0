"""
Tests for IntuneWrapper module.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from intune_packager.installer.wrapper import (
    IntuneWrapper,
    PackageResult,
    IntuneWrapperError,
)


class TestPackageResult:
    """Tests for PackageResult dataclass."""
    
    def test_success_result(self):
        """Test successful result creation."""
        result = PackageResult(
            success=True,
            intunewin_path=Path("/output/test.intunewin"),
            source_file="test.msi",
            package_size=1024,
        )
        
        assert result.success is True
        assert result.intunewin_path == Path("/output/test.intunewin")
    
    def test_failure_result(self):
        """Test failure result creation."""
        result = PackageResult(
            success=False,
            error_message="File not found",
            source_file="missing.msi",
        )
        
        assert result.success is False
        assert result.error_message == "File not found"
    
    def test_to_dict(self):
        """Test result serialization."""
        result = PackageResult(
            success=True,
            intunewin_path=Path("/output/test.intunewin"),
            source_file="test.msi",
        )
        
        data = result.to_dict()
        
        assert isinstance(data, dict)
        assert data["success"] is True
        # Use Path comparison to handle cross-platform differences
        assert Path(data["intunewin_path"]).name == "test.intunewin"


class TestIntuneWrapper:
    """Tests for IntuneWrapper class."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        with patch("intune_packager.installer.wrapper.get_config") as mock:
            config = MagicMock()
            config.get.side_effect = lambda key, default=None: {
                "packaging.output_dir": "./output",
                "packaging.intune_win_util_path": "./tools/IntuneWinAppUtil.exe",
                "packaging.auto_download_util": False,
            }.get(key, default)
            mock.return_value = config
            yield mock
    
    def test_package_missing_file(self, mock_config):
        """Test packaging a missing file."""
        wrapper = IntuneWrapper()
        result = wrapper.package("/nonexistent/installer.msi")
        
        assert result.success is False
        assert "not found" in result.error_message.lower()
    
    def test_package_result_includes_source(self, mock_config, tmp_path):
        """Test that package result includes source file path."""
        test_file = tmp_path / "test.msi"
        test_file.write_bytes(b"test content")
        
        wrapper = IntuneWrapper()
        result = wrapper.package(str(test_file))
        
        # Will fail because IntuneWinAppUtil is not available, 
        # but should include source file
        assert result.source_file == str(test_file.resolve())
    
    @patch("intune_packager.installer.wrapper.Path.exists")
    def test_ensure_util_raises_when_not_found(self, mock_exists, mock_config, tmp_path):
        """Test that missing utility raises error when auto-download disabled."""
        # Make all Path.exists() calls return False
        mock_exists.return_value = False
        
        # Configure auto-download to be disabled
        mock_config.return_value.get.side_effect = lambda key, default=None: {
            "packaging.output_dir": str(tmp_path),
            "packaging.intune_win_util_path": str(tmp_path / "nonexistent" / "util.exe"),
            "packaging.auto_download_util": False,
        }.get(key, default)
        
        wrapper = IntuneWrapper()
        
        with pytest.raises(IntuneWrapperError, match="not found"):
            wrapper.ensure_util_available()
    
    @patch("intune_packager.installer.wrapper.urllib.request.urlretrieve")
    def test_download_util(self, mock_urlretrieve, mock_config, tmp_path):
        """Test utility download."""
        # Configure to allow auto-download
        mock_config.return_value.get.side_effect = lambda key, default=None: {
            "packaging.output_dir": str(tmp_path),
            "packaging.auto_download_util": True,
        }.get(key, default)
        
        wrapper = IntuneWrapper()
        
        # Mock the download
        def fake_download(url, path):
            Path(path).write_bytes(b"fake util")
        
        mock_urlretrieve.side_effect = fake_download
        
        path = wrapper._download_util()
        
        assert path.exists()
        mock_urlretrieve.assert_called_once()
    
    def test_extract_intunewin_info_nonexistent(self, mock_config, tmp_path):
        """Test extracting info from nonexistent file."""
        wrapper = IntuneWrapper()
        
        with pytest.raises(Exception):
            wrapper.extract_intunewin_info(str(tmp_path / "nonexistent.intunewin"))
