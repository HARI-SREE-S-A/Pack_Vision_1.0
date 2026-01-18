"""
Installer type detection and validation.

Detects whether an installer is EXE or MSI and validates file integrity.
"""

import hashlib
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class InstallerType(Enum):
    """Supported installer types."""
    MSI = "msi"
    EXE = "exe"
    UNKNOWN = "unknown"


# File signatures (magic bytes)
FILE_SIGNATURES = {
    # MSI files start with OLE compound document signature
    b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1': InstallerType.MSI,
    # EXE/DLL files start with MZ header
    b'MZ': InstallerType.EXE,
}


@dataclass
class InstallerInfo:
    """Information about a detected installer."""
    path: Path
    type: InstallerType
    size: int
    md5_hash: str
    sha256_hash: str
    filename: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "path": str(self.path),
            "type": self.type.value,
            "size": self.size,
            "md5_hash": self.md5_hash,
            "sha256_hash": self.sha256_hash,
            "filename": self.filename,
        }


class InstallerDetector:
    """Detects and validates installer files."""
    
    SUPPORTED_EXTENSIONS = {".msi", ".exe"}
    
    def __init__(self, installer_path: str):
        """
        Initialize detector with installer path.
        
        Args:
            installer_path: Path to the installer file
        """
        self.path = Path(installer_path).resolve()
        self._info: Optional[InstallerInfo] = None
    
    def validate(self) -> bool:
        """
        Validate that the installer file exists and is valid.
        
        Returns:
            True if valid, raises exception otherwise
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not a valid installer
        """
        if not self.path.exists():
            raise FileNotFoundError(f"Installer not found: {self.path}")
        
        if not self.path.is_file():
            raise ValueError(f"Path is not a file: {self.path}")
        
        extension = self.path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {extension}. "
                f"Supported types: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )
        
        # Validate file is readable and has content
        if self.path.stat().st_size == 0:
            raise ValueError(f"Installer file is empty: {self.path}")
        
        return True
    
    def detect_type(self) -> InstallerType:
        """
        Detect installer type using file signature.
        
        Returns:
            InstallerType enum value
        """
        # First check by extension
        extension = self.path.suffix.lower()
        if extension == ".msi":
            return InstallerType.MSI
        
        # For EXE, verify with magic bytes
        try:
            with open(self.path, 'rb') as f:
                header = f.read(8)
            
            for signature, installer_type in FILE_SIGNATURES.items():
                if header.startswith(signature):
                    return installer_type
            
            # If extension is .exe but no MZ header, still treat as EXE
            if extension == ".exe":
                return InstallerType.EXE
                
        except IOError:
            pass
        
        return InstallerType.UNKNOWN
    
    def compute_hashes(self) -> tuple[str, str]:
        """
        Compute MD5 and SHA256 hashes of the installer.
        
        Returns:
            Tuple of (md5_hash, sha256_hash)
        """
        md5 = hashlib.md5()
        sha256 = hashlib.sha256()
        
        with open(self.path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
                sha256.update(chunk)
        
        return md5.hexdigest(), sha256.hexdigest()
    
    def get_info(self) -> InstallerInfo:
        """
        Get complete installer information.
        
        Returns:
            InstallerInfo object with all details
        """
        if self._info is not None:
            return self._info
        
        self.validate()
        installer_type = self.detect_type()
        md5_hash, sha256_hash = self.compute_hashes()
        
        self._info = InstallerInfo(
            path=self.path,
            type=installer_type,
            size=self.path.stat().st_size,
            md5_hash=md5_hash,
            sha256_hash=sha256_hash,
            filename=self.path.name,
        )
        
        return self._info
