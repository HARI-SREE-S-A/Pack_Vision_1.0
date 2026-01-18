"""
Microsoft Graph API client for Intune operations.

Provides methods for creating and managing Win32 apps in Intune.
"""

import json
from typing import Any, Optional
from urllib.parse import urljoin

import requests

from ..config import get_config
from .auth import IntuneAuth


class GraphAPIError(Exception):
    """Raised when Graph API request fails."""
    
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class GraphClient:
    """Client for Microsoft Graph API Intune operations."""
    
    def __init__(self, auth: Optional[IntuneAuth] = None):
        """
        Initialize Graph client.
        
        Args:
            auth: Optional IntuneAuth instance
        """
        self.config = get_config()
        self.auth = auth or IntuneAuth()
        self.base_url = self.config.get(
            "intune.graph_endpoint",
            "https://graph.microsoft.com/beta"
        )
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict = None,
        headers: dict = None,
        **kwargs
    ) -> dict:
        """
        Make authenticated request to Graph API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base URL)
            data: Request body data
            headers: Additional headers
            **kwargs: Additional arguments for requests
            
        Returns:
            Response JSON
            
        Raises:
            GraphAPIError: If request fails
        """
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        
        request_headers = self.auth.get_auth_headers()
        if headers:
            request_headers.update(headers)
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=request_headers,
                json=data if data else None,
                **kwargs
            )
            
            # Handle no-content responses
            if response.status_code == 204:
                return {}
            
            # Parse response
            try:
                result = response.json()
            except json.JSONDecodeError:
                result = {"raw_content": response.text}
            
            # Check for errors
            if not response.ok:
                error_msg = result.get("error", {}).get("message", response.text)
                raise GraphAPIError(
                    f"API request failed: {error_msg}",
                    status_code=response.status_code,
                    response=result
                )
            
            return result
            
        except requests.RequestException as e:
            raise GraphAPIError(f"Request failed: {e}")
    
    def create_win32_app(
        self,
        display_name: str,
        description: str = "",
        publisher: str = "",
        filename: str = "",
        install_command: str = "",
        uninstall_command: str = "",
        detection_rules: list = None,
        **kwargs
    ) -> dict:
        """
        Create a Win32 LOB app in Intune.
        
        Args:
            display_name: App display name
            description: App description
            publisher: Publisher name
            filename: Setup file name
            install_command: Install command line
            uninstall_command: Uninstall command line
            detection_rules: Detection rules for the app
            **kwargs: Additional app properties
            
        Returns:
            Created app object
        """
        config = self.config
        
        app_data = {
            "@odata.type": "#microsoft.graph.win32LobApp",
            "displayName": display_name,
            "description": description or display_name,
            "publisher": publisher or config.get("app_defaults.publisher", "IT"),
            "fileName": filename,
            "installCommandLine": install_command,
            "uninstallCommandLine": uninstall_command or "",
            "installExperience": {
                "runAsAccount": config.get("app_defaults.install_experience", "system"),
                "deviceRestartBehavior": config.get("app_defaults.restart_behavior", "suppress"),
            },
            "setupFilePath": filename,
            "minimumSupportedOperatingSystem": {
                "v10_1607": True,  # Windows 10 1607+
            },
            "detectionRules": detection_rules or [],
            "returnCodes": self._get_default_return_codes(),
        }
        
        # Merge additional properties
        app_data.update(kwargs)
        
        return self._make_request(
            "POST",
            "/deviceAppManagement/mobileApps",
            data=app_data
        )
    
    def _get_default_return_codes(self) -> list:
        """Get default MSI/EXE return codes."""
        return [
            {"returnCode": 0, "type": "success"},
            {"returnCode": 1707, "type": "success"},
            {"returnCode": 3010, "type": "softReboot"},
            {"returnCode": 1641, "type": "hardReboot"},
            {"returnCode": 1618, "type": "retry"},
        ]
    
    def get_app(self, app_id: str) -> dict:
        """
        Get app by ID.
        
        Args:
            app_id: Application ID
            
        Returns:
            App object
        """
        return self._make_request("GET", f"/deviceAppManagement/mobileApps/{app_id}")
    
    def list_apps(self, filter_query: str = None) -> list:
        """
        List mobile apps.
        
        Args:
            filter_query: OData filter query
            
        Returns:
            List of app objects
        """
        endpoint = "/deviceAppManagement/mobileApps"
        if filter_query:
            endpoint += f"?$filter={filter_query}"
        
        result = self._make_request("GET", endpoint)
        return result.get("value", [])
    
    def delete_app(self, app_id: str) -> bool:
        """
        Delete an app.
        
        Args:
            app_id: Application ID
            
        Returns:
            True if deleted
        """
        self._make_request("DELETE", f"/deviceAppManagement/mobileApps/{app_id}")
        return True
    
    def create_content_version(self, app_id: str) -> dict:
        """
        Create a new content version for an app.
        
        Args:
            app_id: Application ID
            
        Returns:
            Content version object
        """
        return self._make_request(
            "POST",
            f"/deviceAppManagement/mobileApps/{app_id}/microsoft.graph.win32LobApp/contentVersions",
            data={}
        )
    
    def create_content_file(
        self,
        app_id: str,
        content_version_id: str,
        filename: str,
        size: int,
        encrypted_size: int,
    ) -> dict:
        """
        Create a content file entry for upload.
        
        Args:
            app_id: Application ID
            content_version_id: Content version ID
            filename: File name
            size: Original file size
            encrypted_size: Encrypted file size
            
        Returns:
            Content file object with Azure storage URI
        """
        data = {
            "@odata.type": "#microsoft.graph.mobileAppContentFile",
            "name": filename,
            "size": size,
            "sizeEncrypted": encrypted_size,
            "isDependency": False,
        }
        
        return self._make_request(
            "POST",
            f"/deviceAppManagement/mobileApps/{app_id}/microsoft.graph.win32LobApp/"
            f"contentVersions/{content_version_id}/files",
            data=data
        )
    
    def get_content_file(
        self,
        app_id: str,
        content_version_id: str,
        file_id: str,
    ) -> dict:
        """
        Get content file status (for getting Azure storage URI).
        
        Args:
            app_id: Application ID
            content_version_id: Content version ID
            file_id: File ID
            
        Returns:
            Content file object
        """
        return self._make_request(
            "GET",
            f"/deviceAppManagement/mobileApps/{app_id}/microsoft.graph.win32LobApp/"
            f"contentVersions/{content_version_id}/files/{file_id}"
        )
    
    def commit_content_file(
        self,
        app_id: str,
        content_version_id: str,
        file_id: str,
        encryption_info: dict,
    ) -> dict:
        """
        Commit uploaded file content.
        
        Args:
            app_id: Application ID
            content_version_id: Content version ID
            file_id: File ID
            encryption_info: File encryption information
            
        Returns:
            Updated content file object
        """
        data = {
            "fileEncryptionInfo": encryption_info
        }
        
        return self._make_request(
            "POST",
            f"/deviceAppManagement/mobileApps/{app_id}/microsoft.graph.win32LobApp/"
            f"contentVersions/{content_version_id}/files/{file_id}/commit",
            data=data
        )
    
    def update_app_content_version(
        self,
        app_id: str,
        content_version_id: str,
    ) -> dict:
        """
        Update app to use the committed content version.
        
        Args:
            app_id: Application ID
            content_version_id: Content version ID
            
        Returns:
            Updated app object
        """
        data = {
            "@odata.type": "#microsoft.graph.win32LobApp",
            "committedContentVersion": content_version_id,
        }
        
        return self._make_request(
            "PATCH",
            f"/deviceAppManagement/mobileApps/{app_id}",
            data=data
        )
    
    def assign_app(
        self,
        app_id: str,
        group_ids: list,
        intent: str = "required",
    ) -> dict:
        """
        Assign app to groups.
        
        Args:
            app_id: Application ID
            group_ids: List of Azure AD group IDs
            intent: Assignment intent (required, available, uninstall)
            
        Returns:
            Assignment result
        """
        assignments = []
        for group_id in group_ids:
            assignments.append({
                "@odata.type": "#microsoft.graph.mobileAppAssignment",
                "intent": intent,
                "target": {
                    "@odata.type": "#microsoft.graph.groupAssignmentTarget",
                    "groupId": group_id,
                },
                "settings": {
                    "@odata.type": "#microsoft.graph.win32LobAppAssignmentSettings",
                    "notifications": "showAll",
                    "restartSettings": None,
                    "installTimeSettings": None,
                    "deliveryOptimizationPriority": "notConfigured",
                },
            })
        
        data = {"mobileAppAssignments": assignments}
        
        return self._make_request(
            "POST",
            f"/deviceAppManagement/mobileApps/{app_id}/assign",
            data=data
        )
    
    def get_app_assignments(self, app_id: str) -> list:
        """
        Get app assignments.
        
        Args:
            app_id: Application ID
            
        Returns:
            List of assignments
        """
        result = self._make_request(
            "GET",
            f"/deviceAppManagement/mobileApps/{app_id}/assignments"
        )
        return result.get("value", [])
    
    def get_app_install_status(self, app_id: str) -> dict:
        """
        Get app installation status summary.
        
        Args:
            app_id: Application ID
            
        Returns:
            Installation status summary
        """
        return self._make_request(
            "GET",
            f"/deviceAppManagement/mobileApps/{app_id}/deviceStatuses"
        )
