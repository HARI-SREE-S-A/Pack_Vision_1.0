"""
IntuneWinAppUtil wrapper.

Wraps installers to .intunewin format for Intune deployment.
"""

import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import get_config


INTUNE_WIN_UTIL_URL = (
    "https://github.com/microsoft/Microsoft-Win32-Content-Prep-Tool/raw/master/"
    "IntuneWinAppUtil.exe"
)


@dataclass
class PackageResult:
    """Result of packaging operation."""
    success: bool
    intunewin_path: Optional[Path] = None
    error_message: Optional[str] = None
    source_file: Optional[str] = None
    package_size: Optional[int] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "intunewin_path": str(self.intunewin_path) if self.intunewin_path else None,
            "error_message": self.error_message,
            "source_file": self.source_file,
            "package_size": self.package_size,
        }


class IntuneWrapperError(Exception):
    """Error during Intune packaging."""
    pass


class IntuneWrapper:
    """Wraps installers to .intunewin format."""
    
    def __init__(self, util_path: Optional[str] = None):
        """
        Initialize wrapper.
        
        Args:
            util_path: Optional path to IntuneWinAppUtil.exe
        """
        self.config = get_config()
        self._util_path: Optional[Path] = None
        
        if util_path:
            self._util_path = Path(util_path)
        else:
            configured_path = self.config.get("packaging.intune_win_util_path")
            if configured_path:
                self._util_path = Path(configured_path)
    
    def ensure_util_available(self) -> Path:
        """
        Ensure IntuneWinAppUtil.exe is available.
        
        Downloads it if not found and auto_download is enabled.
        
        Returns:
            Path to the utility
            
        Raises:
            IntuneWrapperError: If utility not found and can't be downloaded
        """
        if self._util_path and self._util_path.exists():
            return self._util_path
        
        # Check default location
        default_path = Path("./tools/IntuneWinAppUtil.exe")
        if default_path.exists():
            self._util_path = default_path
            return self._util_path
        
        # Try to download if enabled
        if self.config.get("packaging.auto_download_util", True):
            return self._download_util()
        
        raise IntuneWrapperError(
            "IntuneWinAppUtil.exe not found. Please download it from "
            "https://github.com/microsoft/Microsoft-Win32-Content-Prep-Tool "
            "or enable auto_download_util in config."
        )
    
    def _download_util(self) -> Path:
        """Download IntuneWinAppUtil.exe from GitHub."""
        tools_dir = Path("./tools")
        tools_dir.mkdir(parents=True, exist_ok=True)
        
        util_path = tools_dir / "IntuneWinAppUtil.exe"
        
        print(f"Downloading IntuneWinAppUtil.exe...")
        try:
            urllib.request.urlretrieve(INTUNE_WIN_UTIL_URL, util_path)
            print(f"Downloaded to: {util_path}")
            self._util_path = util_path
            return util_path
        except Exception as e:
            raise IntuneWrapperError(f"Failed to download IntuneWinAppUtil: {e}")
    
    def package(
        self,
        installer_path: str,
        output_dir: Optional[str] = None,
        setup_file: Optional[str] = None,
    ) -> PackageResult:
        """
        Package an installer to .intunewin format.
        
        Args:
            installer_path: Path to the installer (EXE/MSI)
            output_dir: Optional output directory (defaults to ./output)
            setup_file: Optional setup file name (defaults to installer filename)
            
        Returns:
            PackageResult with success status and output path
        """
        installer_path = Path(installer_path).resolve()
        
        if not installer_path.exists():
            return PackageResult(
                success=False,
                error_message=f"Installer not found: {installer_path}",
                source_file=str(installer_path),
            )
        
        # Ensure utility is available
        try:
            util_path = self.ensure_util_available()
        except IntuneWrapperError as e:
            return PackageResult(
                success=False,
                error_message=str(e),
                source_file=str(installer_path),
            )
        
        # Set up directories
        output_dir = Path(output_dir or self.config.get("packaging.output_dir", "./output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        
        source_dir = installer_path.parent
        setup_file = setup_file or installer_path.name
        
        # Build command
        # IntuneWinAppUtil.exe -c <source_folder> -s <setup_file> -o <output_folder> -q
        cmd = [
            str(util_path),
            "-c", str(source_dir),
            "-s", setup_file,
            "-o", str(output_dir),
            "-q",  # Quiet mode
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            
            # Check for output file
            expected_output = output_dir / f"{installer_path.stem}.intunewin"
            
            if expected_output.exists():
                return PackageResult(
                    success=True,
                    intunewin_path=expected_output,
                    source_file=str(installer_path),
                    package_size=expected_output.stat().st_size,
                )
            else:
                # Try to find the output file with different name patterns
                for file in output_dir.glob("*.intunewin"):
                    return PackageResult(
                        success=True,
                        intunewin_path=file,
                        source_file=str(installer_path),
                        package_size=file.stat().st_size,
                    )
                
                return PackageResult(
                    success=False,
                    error_message=f"Package created but output file not found. "
                                  f"Stdout: {result.stdout}\nStderr: {result.stderr}",
                    source_file=str(installer_path),
                )
                
        except subprocess.TimeoutExpired:
            return PackageResult(
                success=False,
                error_message="Packaging timed out after 5 minutes",
                source_file=str(installer_path),
            )
        except Exception as e:
            return PackageResult(
                success=False,
                error_message=f"Packaging failed: {e}",
                source_file=str(installer_path),
            )
    
    def extract_intunewin_info(self, intunewin_path: str) -> dict:
        """
        Extract information from an .intunewin package.
        
        The .intunewin file is actually a ZIP containing encrypted content
        and a detection.xml file.
        
        Args:
            intunewin_path: Path to the .intunewin file
            
        Returns:
            Dictionary with package information
        """
        intunewin_path = Path(intunewin_path)
        info = {
            "path": str(intunewin_path),
            "size": intunewin_path.stat().st_size,
            "filename": intunewin_path.name,
        }
        
        try:
            with zipfile.ZipFile(intunewin_path, 'r') as zf:
                info["contents"] = zf.namelist()
                
                # Try to read Detection.xml if present
                for name in zf.namelist():
                    if name.lower().endswith("detection.xml"):
                        info["detection_xml"] = zf.read(name).decode('utf-8')
                        break
        except Exception as e:
            info["error"] = str(e)
        
        return info
