"""
Installer metadata extraction.

Extracts metadata from EXE and MSI installers.
"""

import os
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .detector import InstallerDetector, InstallerType


@dataclass
class InstallerMetadata:
    """Metadata extracted from an installer."""
    filename: str
    file_version: Optional[str] = None
    product_name: Optional[str] = None
    product_version: Optional[str] = None
    manufacturer: Optional[str] = None
    description: Optional[str] = None
    install_command: Optional[str] = None
    uninstall_command: Optional[str] = None
    detection_rules: dict = field(default_factory=dict)
    raw_properties: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "filename": self.filename,
            "file_version": self.file_version,
            "product_name": self.product_name,
            "product_version": self.product_version,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "install_command": self.install_command,
            "uninstall_command": self.uninstall_command,
            "detection_rules": self.detection_rules,
        }


class MetadataExtractor:
    """Extracts metadata from installer files."""
    
    def __init__(self, installer_path: str):
        """
        Initialize metadata extractor.
        
        Args:
            installer_path: Path to the installer file
        """
        self.path = Path(installer_path).resolve()
        self.detector = InstallerDetector(installer_path)
    
    def extract(self) -> InstallerMetadata:
        """
        Extract metadata from the installer.
        
        Returns:
            InstallerMetadata object
        """
        info = self.detector.get_info()
        
        if info.type == InstallerType.MSI:
            return self._extract_msi_metadata()
        elif info.type == InstallerType.EXE:
            return self._extract_exe_metadata()
        else:
            return InstallerMetadata(filename=self.path.name)
    
    def _extract_msi_metadata(self) -> InstallerMetadata:
        """Extract metadata from MSI installer."""
        metadata = InstallerMetadata(filename=self.path.name)
        
        try:
            import msilib
            
            db = msilib.OpenDatabase(str(self.path), msilib.MSIDBOPEN_READONLY)
            
            # Standard MSI properties to extract
            properties_to_extract = [
                ("ProductName", "product_name"),
                ("ProductVersion", "product_version"),
                ("Manufacturer", "manufacturer"),
                ("ProductCode", None),
                ("UpgradeCode", None),
            ]
            
            for msi_prop, attr_name in properties_to_extract:
                try:
                    view = db.OpenView(
                        f"SELECT Value FROM Property WHERE Property = '{msi_prop}'"
                    )
                    view.Execute(None)
                    record = view.Fetch()
                    if record:
                        value = record.GetString(1)
                        metadata.raw_properties[msi_prop] = value
                        if attr_name:
                            setattr(metadata, attr_name, value)
                    view.Close()
                except Exception:
                    continue
            
            # Set install/uninstall commands for MSI
            product_code = metadata.raw_properties.get("ProductCode", "")
            metadata.install_command = f'msiexec /i "{self.path.name}" /qn'
            metadata.uninstall_command = f'msiexec /x "{product_code}" /qn'
            
            # Set detection rules
            if product_code:
                metadata.detection_rules = {
                    "type": "msi",
                    "product_code": product_code,
                }
            
        except ImportError:
            # msilib not available (non-Windows), use basic info
            metadata.install_command = f'msiexec /i "{self.path.name}" /qn'
        except Exception as e:
            # Log error but continue with basic metadata
            metadata.raw_properties["_error"] = str(e)
        
        return metadata
    
    def _extract_exe_metadata(self) -> InstallerMetadata:
        """Extract metadata from EXE installer."""
        metadata = InstallerMetadata(filename=self.path.name)
        
        try:
            import pefile
            
            pe = pefile.PE(str(self.path))
            
            # Extract version information if available
            if hasattr(pe, 'VS_VERSIONINFO') or hasattr(pe, 'FileInfo'):
                for fileinfo in getattr(pe, 'FileInfo', [[]]):
                    for info in fileinfo:
                        if hasattr(info, 'StringTable'):
                            for st in info.StringTable:
                                for key, value in st.entries.items():
                                    key_str = key.decode('utf-8', errors='ignore')
                                    value_str = value.decode('utf-8', errors='ignore')
                                    metadata.raw_properties[key_str] = value_str
                                    
                                    # Map to standard fields
                                    if key_str == "FileVersion":
                                        metadata.file_version = value_str
                                    elif key_str == "ProductName":
                                        metadata.product_name = value_str
                                    elif key_str == "ProductVersion":
                                        metadata.product_version = value_str
                                    elif key_str == "CompanyName":
                                        metadata.manufacturer = value_str
                                    elif key_str == "FileDescription":
                                        metadata.description = value_str
            
            pe.close()
            
        except ImportError:
            # pefile not available
            pass
        except Exception as e:
            metadata.raw_properties["_error"] = str(e)
        
        # Set default install command - common silent switches
        filename = self.path.name
        metadata.install_command = f'"{filename}" /S'
        metadata.uninstall_command = None
        
        # Set detection rules based on file
        metadata.detection_rules = {
            "type": "file",
            "path": f"%ProgramFiles%\\{metadata.product_name or filename}",
        }
        
        return metadata
    
    def suggest_silent_switches(self) -> list[str]:
        """
        Suggest common silent install switches based on installer type.
        
        Returns:
            List of possible silent install command variations
        """
        info = self.detector.get_info()
        filename = self.path.name
        
        if info.type == InstallerType.MSI:
            return [
                f'msiexec /i "{filename}" /qn',
                f'msiexec /i "{filename}" /qn /norestart',
                f'msiexec /i "{filename}" /quiet',
            ]
        elif info.type == InstallerType.EXE:
            # Common silent switches for various installer types
            return [
                f'"{filename}" /S',                    # NSIS, Inno Setup
                f'"{filename}" /silent',               # InstallShield
                f'"{filename}" /quiet',                # Various
                f'"{filename}" /VERYSILENT',           # Inno Setup
                f'"{filename}" -silent',               # InstallAnywhere
                f'"{filename}" --silent',              # Various
                f'"{filename}" /qn',                   # MSI wrapped
            ]
        
        return [f'"{filename}"']
