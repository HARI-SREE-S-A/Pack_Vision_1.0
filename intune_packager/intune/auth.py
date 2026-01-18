"""
Azure AD authentication for Microsoft Graph API.

Uses MSAL for client credentials flow (app-only authentication).
"""

import json
from pathlib import Path
from typing import Optional

import msal

from ..config import get_config


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class IntuneAuth:
    """Handles Azure AD authentication for Intune Graph API."""
    
    AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}"
    SCOPE = ["https://graph.microsoft.com/.default"]
    TOKEN_CACHE_FILE = ".token_cache.json"
    
    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        """
        Initialize authentication.
        
        Args:
            tenant_id: Azure AD tenant ID
            client_id: Application (client) ID
            client_secret: Client secret
        """
        config = get_config()
        
        self.tenant_id = tenant_id or config.get("azure.tenant_id")
        self.client_id = client_id or config.get("azure.client_id")
        self.client_secret = client_secret or config.get("azure.client_secret")
        
        self._token_cache = msal.SerializableTokenCache()
        self._load_token_cache()
        
        self._app: Optional[msal.ConfidentialClientApplication] = None
        self._access_token: Optional[str] = None
    
    def _get_authority(self) -> str:
        """Get Azure AD authority URL."""
        return self.AUTHORITY_TEMPLATE.format(tenant_id=self.tenant_id)
    
    def _load_token_cache(self) -> None:
        """Load token cache from file if exists."""
        cache_file = Path(self.TOKEN_CACHE_FILE)
        if cache_file.exists():
            try:
                self._token_cache.deserialize(cache_file.read_text())
            except Exception:
                pass  # Ignore cache read errors
    
    def _save_token_cache(self) -> None:
        """Save token cache to file."""
        if self._token_cache.has_state_changed:
            try:
                Path(self.TOKEN_CACHE_FILE).write_text(self._token_cache.serialize())
            except Exception:
                pass  # Ignore cache write errors
    
    def _get_app(self) -> msal.ConfidentialClientApplication:
        """Get or create MSAL application."""
        if self._app is None:
            if not all([self.tenant_id, self.client_id, self.client_secret]):
                raise AuthenticationError(
                    "Missing Azure AD credentials. Please configure tenant_id, "
                    "client_id, and client_secret in config.yaml"
                )
            
            self._app = msal.ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=self._get_authority(),
                token_cache=self._token_cache,
            )
        
        return self._app
    
    def get_access_token(self) -> str:
        """
        Get access token for Microsoft Graph API.
        
        First tries to get token from cache, then acquires new token if needed.
        
        Returns:
            Access token string
            
        Raises:
            AuthenticationError: If token acquisition fails
        """
        app = self._get_app()
        
        # Try to get token from cache
        result = app.acquire_token_silent(self.SCOPE, account=None)
        
        if not result:
            # No cached token, acquire new one
            result = app.acquire_token_for_client(scopes=self.SCOPE)
        
        if "access_token" in result:
            self._access_token = result["access_token"]
            self._save_token_cache()
            return self._access_token
        
        # Handle error
        error = result.get("error", "unknown_error")
        error_description = result.get("error_description", "No description")
        
        raise AuthenticationError(
            f"Failed to acquire token: {error}\n{error_description}"
        )
    
    def get_auth_headers(self) -> dict:
        """
        Get authorization headers for API requests.
        
        Returns:
            Dictionary with Authorization header
        """
        token = self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    
    def validate_credentials(self) -> bool:
        """
        Validate that credentials are configured and can authenticate.
        
        Returns:
            True if authentication succeeds
            
        Raises:
            AuthenticationError: If credentials are invalid
        """
        self.get_access_token()
        return True
