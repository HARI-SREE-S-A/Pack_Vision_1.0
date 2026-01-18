"""
Tests for installer detector module.
"""

import hashlib
import tempfile
from pathlib import Path

import pytest

from intune_packager.installer.detector import (
    InstallerDetector,
    InstallerType,
    InstallerInfo,
)


class TestInstallerType:
    """Tests for InstallerType enum."""
    
    def test_enum_values(self):
        """Test enum has expected values."""
        assert InstallerType.MSI.value == "msi"
        assert InstallerType.EXE.value == "exe"
        assert InstallerType.UNKNOWN.value == "unknown"


class TestInstallerDetector:
    """Tests for InstallerDetector class."""
    
    def test_validate_nonexistent_file(self, tmp_path):
        """Test validation fails for nonexistent file."""
        detector = InstallerDetector(str(tmp_path / "nonexistent.msi"))
        with pytest.raises(FileNotFoundError):
            detector.validate()
    
    def test_validate_empty_file(self, tmp_path):
        """Test validation fails for empty file."""
        empty_file = tmp_path / "empty.msi"
        empty_file.touch()
        
        detector = InstallerDetector(str(empty_file))
        with pytest.raises(ValueError, match="empty"):
            detector.validate()
    
    def test_validate_unsupported_extension(self, tmp_path):
        """Test validation fails for unsupported extension."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("content")
        
        detector = InstallerDetector(str(txt_file))
        with pytest.raises(ValueError, match="Unsupported"):
            detector.validate()
    
    def test_validate_valid_msi_extension(self, tmp_path):
        """Test validation passes for valid MSI file."""
        msi_file = tmp_path / "test.msi"
        msi_file.write_bytes(b"test content")
        
        detector = InstallerDetector(str(msi_file))
        assert detector.validate() is True
    
    def test_validate_valid_exe_extension(self, tmp_path):
        """Test validation passes for valid EXE file."""
        exe_file = tmp_path / "test.exe"
        exe_file.write_bytes(b"MZ test content")
        
        detector = InstallerDetector(str(exe_file))
        assert detector.validate() is True
    
    def test_detect_type_msi_by_extension(self, tmp_path):
        """Test MSI detection by extension."""
        msi_file = tmp_path / "test.msi"
        msi_file.write_bytes(b"test content")
        
        detector = InstallerDetector(str(msi_file))
        assert detector.detect_type() == InstallerType.MSI
    
    def test_detect_type_exe_by_magic_bytes(self, tmp_path):
        """Test EXE detection by MZ header."""
        exe_file = tmp_path / "test.exe"
        exe_file.write_bytes(b"MZ" + b"\x00" * 100)
        
        detector = InstallerDetector(str(exe_file))
        assert detector.detect_type() == InstallerType.EXE
    
    def test_compute_hashes(self, tmp_path):
        """Test hash computation."""
        content = b"test content for hashing"
        test_file = tmp_path / "test.msi"
        test_file.write_bytes(content)
        
        detector = InstallerDetector(str(test_file))
        md5, sha256 = detector.compute_hashes()
        
        expected_md5 = hashlib.md5(content).hexdigest()
        expected_sha256 = hashlib.sha256(content).hexdigest()
        
        assert md5 == expected_md5
        assert sha256 == expected_sha256
    
    def test_get_info(self, tmp_path):
        """Test getting complete installer info."""
        content = b"MZ" + b"test exe content"
        exe_file = tmp_path / "installer.exe"
        exe_file.write_bytes(content)
        
        detector = InstallerDetector(str(exe_file))
        info = detector.get_info()
        
        assert isinstance(info, InstallerInfo)
        assert info.filename == "installer.exe"
        assert info.type == InstallerType.EXE
        assert info.size == len(content)
        assert len(info.md5_hash) == 32
        assert len(info.sha256_hash) == 64
    
    def test_get_info_caching(self, tmp_path):
        """Test that get_info caches results."""
        msi_file = tmp_path / "test.msi"
        msi_file.write_bytes(b"content")
        
        detector = InstallerDetector(str(msi_file))
        info1 = detector.get_info()
        info2 = detector.get_info()
        
        assert info1 is info2  # Same object (cached)
    
    def test_installer_info_to_dict(self, tmp_path):
        """Test InstallerInfo serialization."""
        msi_file = tmp_path / "test.msi"
        msi_file.write_bytes(b"content")
        
        detector = InstallerDetector(str(msi_file))
        info = detector.get_info()
        info_dict = info.to_dict()
        
        assert isinstance(info_dict, dict)
        assert "path" in info_dict
        assert "type" in info_dict
        assert info_dict["type"] == "msi"
        assert "filename" in info_dict
        assert "size" in info_dict
        assert "md5_hash" in info_dict
        assert "sha256_hash" in info_dict
