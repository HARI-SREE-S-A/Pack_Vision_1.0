"""
Intune Win32 app uploader.

Handles the complete upload workflow for Win32 apps to Intune.
"""

import base64
import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from .auth import IntuneAuth
from .graph_client import GraphClient, GraphAPIError


@dataclass
class UploadResult:
    """Result of upload operation."""
    success: bool
    app_id: Optional[str] = None
    app_name: Optional[str] = None
    error_message: Optional[str] = None
    upload_time_seconds: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "app_id": self.app_id,
            "app_name": self.app_name,
            "error_message": self.error_message,
            "upload_time_seconds": self.upload_time_seconds,
        }


class IntuneUploader:
    """Uploads Win32 apps to Microsoft Intune."""
    
    BLOCK_SIZE = 4 * 1024 * 1024  # 4 MB blocks for Azure upload
    MAX_WAIT_TIME = 600  # 10 minutes max wait for Azure URI
    POLL_INTERVAL = 5  # 5 seconds between polls
    
    def __init__(
        self,
        auth: Optional[IntuneAuth] = None,
        client: Optional[GraphClient] = None,
    ):
        """
        Initialize uploader.
        
        Args:
            auth: Optional IntuneAuth instance
            client: Optional GraphClient instance
        """
        self.auth = auth or IntuneAuth()
        self.client = client or GraphClient(self.auth)
    
    def upload(
        self,
        intunewin_path: str,
        display_name: str,
        description: str = "",
        publisher: str = "",
        install_command: str = "",
        uninstall_command: str = "",
        version: str = "",
    ) -> UploadResult:
        """
        Upload an .intunewin package to Intune.
        
        Args:
            intunewin_path: Path to the .intunewin file
            display_name: App display name
            description: App description
            publisher: Publisher name
            install_command: Install command line
            uninstall_command: Uninstall command line
            version: App version
            
        Returns:
            UploadResult with success status
        """
        start_time = time.time()
        intunewin_path = Path(intunewin_path)
        
        if not intunewin_path.exists():
            return UploadResult(
                success=False,
                error_message=f"File not found: {intunewin_path}"
            )
        
        try:
            # Extract encryption info and file info from .intunewin
            encryption_info, inner_file_info = self._extract_intunewin_info(intunewin_path)
            
            # Get file sizes
            file_size = intunewin_path.stat().st_size
            
            # Create the app in Intune
            print(f"Creating app '{display_name}' in Intune...")
            
            detection_rules = self._create_detection_rules(install_command, version)
            
            app = self.client.create_win32_app(
                display_name=display_name,
                description=description or display_name,
                publisher=publisher,
                filename=inner_file_info.get("name", intunewin_path.stem),
                install_command=install_command,
                uninstall_command=uninstall_command,
                detection_rules=detection_rules,
            )
            
            app_id = app["id"]
            print(f"Created app with ID: {app_id}")
            
            # Create content version
            print("Creating content version...")
            content_version = self.client.create_content_version(app_id)
            content_version_id = content_version["id"]
            
            # Create content file entry
            print("Creating content file entry...")
            content_file = self.client.create_content_file(
                app_id=app_id,
                content_version_id=content_version_id,
                filename=intunewin_path.name,
                size=inner_file_info.get("unencryptedSize", file_size),
                encrypted_size=file_size,
            )
            file_id = content_file["id"]
            
            # Wait for Azure storage URI
            print("Waiting for Azure storage URI...")
            azure_uri = self._wait_for_azure_uri(
                app_id, content_version_id, file_id
            )
            
            if not azure_uri:
                return UploadResult(
                    success=False,
                    app_id=app_id,
                    app_name=display_name,
                    error_message="Timeout waiting for Azure storage URI"
                )
            
            # Upload file to Azure Storage
            print(f"Uploading {intunewin_path.name} to Azure...")
            self._upload_to_azure(intunewin_path, azure_uri)
            
            # Commit the file
            print("Committing file upload...")
            self.client.commit_content_file(
                app_id=app_id,
                content_version_id=content_version_id,
                file_id=file_id,
                encryption_info=encryption_info,
            )
            
            # Wait for commit to complete
            print("Waiting for commit to complete...")
            self._wait_for_commit(app_id, content_version_id, file_id)
            
            # Update app with committed content version
            print("Finalizing app...")
            self.client.update_app_content_version(app_id, content_version_id)
            
            elapsed_time = time.time() - start_time
            print(f"Upload complete! App ID: {app_id}")
            
            return UploadResult(
                success=True,
                app_id=app_id,
                app_name=display_name,
                upload_time_seconds=elapsed_time,
            )
            
        except GraphAPIError as e:
            return UploadResult(
                success=False,
                error_message=f"Graph API error: {e}",
            )
        except Exception as e:
            return UploadResult(
                success=False,
                error_message=f"Upload failed: {e}",
            )
    
    def _extract_intunewin_info(self, intunewin_path: Path) -> tuple[dict, dict]:
        """
        Extract encryption info and file info from .intunewin package.
        
        The .intunewin file is a ZIP containing:
        - IntunePackage.intunewin (encrypted content)
        - Detection.xml (metadata)
        """
        encryption_info = {}
        file_info = {}
        
        try:
            with zipfile.ZipFile(intunewin_path, 'r') as zf:
                # Find Detection.xml
                for name in zf.namelist():
                    if "detection.xml" in name.lower():
                        xml_content = zf.read(name).decode('utf-8')
                        root = ET.fromstring(xml_content)
                        
                        # Extract encryption info
                        enc_info = root.find(".//EncryptionInfo")
                        if enc_info is not None:
                            encryption_info = {
                                "encryptionKey": self._get_xml_text(enc_info, "EncryptionKey"),
                                "macKey": self._get_xml_text(enc_info, "macKey"),
                                "initializationVector": self._get_xml_text(enc_info, "initializationVector"),
                                "mac": self._get_xml_text(enc_info, "mac"),
                                "profileIdentifier": self._get_xml_text(enc_info, "profileIdentifier"),
                                "fileDigest": self._get_xml_text(enc_info, "fileDigest"),
                                "fileDigestAlgorithm": self._get_xml_text(enc_info, "fileDigestAlgorithm"),
                            }
                        
                        # Extract file info
                        app_info = root.find(".//ApplicationInfo")
                        if app_info is not None:
                            file_info = {
                                "name": self._get_xml_text(app_info, "Name"),
                                "unencryptedSize": int(self._get_xml_text(app_info, "UnencryptedContentSize") or 0),
                                "setupFile": self._get_xml_text(app_info, "SetupFile"),
                            }
                        
                        break
        except Exception as e:
            print(f"Warning: Could not parse .intunewin metadata: {e}")
        
        # Use defaults if not found
        if not encryption_info:
            encryption_info = self._generate_default_encryption_info()
        
        return encryption_info, file_info
    
    def _get_xml_text(self, parent: ET.Element, tag: str) -> Optional[str]:
        """Get text content of XML child element."""
        elem = parent.find(tag)
        return elem.text if elem is not None else None
    
    def _generate_default_encryption_info(self) -> dict:
        """Generate default encryption info structure."""
        return {
            "encryptionKey": "",
            "macKey": "",
            "initializationVector": "",
            "mac": "",
            "profileIdentifier": "ProfileVersion1",
            "fileDigest": "",
            "fileDigestAlgorithm": "SHA256",
        }
    
    def _create_detection_rules(self, install_command: str, version: str) -> list:
        """Create detection rules for the app."""
        rules = []
        
        # File-based detection (common approach)
        if ".msi" in install_command.lower():
            # MSI detection using product code would be ideal
            # For now, use script detection
            rules.append({
                "@odata.type": "#microsoft.graph.win32LobAppPowerShellScriptDetection",
                "enforceSignatureCheck": False,
                "runAs32Bit": False,
                "scriptContent": base64.b64encode(
                    b"# Detection script - customize as needed\n"
                    b"$app = Get-WmiObject -Class Win32_Product | Where-Object { $_.Name -like '*AppName*' }\n"
                    b"if ($app) { Write-Output 'Installed'; exit 0 } else { exit 1 }"
                ).decode('utf-8'),
            })
        else:
            # EXE detection using registry or file
            rules.append({
                "@odata.type": "#microsoft.graph.win32LobAppFileSystemDetection",
                "path": "%ProgramFiles%",
                "fileOrFolderName": "placeholder.exe",
                "check32BitOn64System": False,
                "detectionType": "exists",
            })
        
        return rules
    
    def _wait_for_azure_uri(
        self,
        app_id: str,
        content_version_id: str,
        file_id: str,
    ) -> Optional[str]:
        """Wait for Azure storage URI to become available."""
        start_time = time.time()
        
        while (time.time() - start_time) < self.MAX_WAIT_TIME:
            content_file = self.client.get_content_file(
                app_id, content_version_id, file_id
            )
            
            azure_uri = content_file.get("azureStorageUri")
            if azure_uri:
                return azure_uri
            
            state = content_file.get("uploadState")
            if state == "azureStorageUriRequestFailed":
                raise GraphAPIError("Azure storage URI request failed")
            
            time.sleep(self.POLL_INTERVAL)
        
        return None
    
    def _upload_to_azure(self, file_path: Path, azure_uri: str) -> None:
        """
        Upload file to Azure Blob Storage using block upload.
        
        Args:
            file_path: Path to file to upload
            azure_uri: Azure Blob Storage SAS URI
        """
        file_size = file_path.stat().st_size
        block_ids = []
        
        with open(file_path, 'rb') as f:
            block_num = 0
            
            while True:
                chunk = f.read(self.BLOCK_SIZE)
                if not chunk:
                    break
                
                # Generate block ID
                block_id = base64.b64encode(
                    f"block{block_num:05d}".encode()
                ).decode()
                block_ids.append(block_id)
                
                # Upload block
                block_uri = f"{azure_uri}&comp=block&blockid={block_id}"
                response = requests.put(
                    block_uri,
                    data=chunk,
                    headers={
                        "x-ms-blob-type": "BlockBlob",
                        "Content-Length": str(len(chunk)),
                    }
                )
                response.raise_for_status()
                
                block_num += 1
                uploaded = min((block_num) * self.BLOCK_SIZE, file_size)
                print(f"  Uploaded {uploaded:,} / {file_size:,} bytes ({100*uploaded/file_size:.1f}%)")
        
        # Commit all blocks
        block_list_xml = '<?xml version="1.0" encoding="utf-8"?><BlockList>'
        for block_id in block_ids:
            block_list_xml += f"<Latest>{block_id}</Latest>"
        block_list_xml += "</BlockList>"
        
        commit_uri = f"{azure_uri}&comp=blocklist"
        response = requests.put(
            commit_uri,
            data=block_list_xml,
            headers={"Content-Type": "application/xml"}
        )
        response.raise_for_status()
    
    def _wait_for_commit(
        self,
        app_id: str,
        content_version_id: str,
        file_id: str,
    ) -> bool:
        """Wait for file commit to complete."""
        start_time = time.time()
        
        while (time.time() - start_time) < self.MAX_WAIT_TIME:
            content_file = self.client.get_content_file(
                app_id, content_version_id, file_id
            )
            
            state = content_file.get("uploadState")
            if state == "commitFileSuccess":
                return True
            elif state in ("commitFileFailed", "commitFilePending"):
                if state == "commitFileFailed":
                    raise GraphAPIError("File commit failed")
            
            time.sleep(self.POLL_INTERVAL)
        
        return False
