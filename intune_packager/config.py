"""
Configuration management for Intune Packager.

Handles loading and validation of configuration from YAML files.
"""

import os
from pathlib import Path
from typing import Any, Optional
import yaml


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


class Config:
    """Configuration manager for Intune Packager."""
    
    DEFAULT_CONFIG_PATHS = [
        "./config.yaml",
        "./config.yml",
        "~/.intune_packager/config.yaml",
    ]
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Optional path to configuration file.
                        If not provided, searches default locations.
        """
        self._config: dict = {}
        self._config_path: Optional[Path] = None
        
        if config_path:
            self._load_config(Path(config_path))
        else:
            self._find_and_load_config()
    
    def _find_and_load_config(self) -> None:
        """Find configuration file in default locations."""
        for path_str in self.DEFAULT_CONFIG_PATHS:
            path = Path(path_str).expanduser()
            if path.exists():
                self._load_config(path)
                return
        
        # No config found, use defaults
        self._config = self._get_defaults()
    
    def _load_config(self, path: Path) -> None:
        """Load configuration from YAML file."""
        if not path.exists():
            raise ConfigurationError(f"Configuration file not found: {path}")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
            self._config_path = path
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in configuration: {e}")
        
        # Merge with defaults
        defaults = self._get_defaults()
        self._config = self._deep_merge(defaults, self._config)
    
    def _get_defaults(self) -> dict:
        """Get default configuration values."""
        return {
            "azure": {
                "tenant_id": "",
                "client_id": "",
                "client_secret": "",
            },
            "intune": {
                "graph_endpoint": "https://graph.microsoft.com/beta",
                "scope": "https://graph.microsoft.com/.default",
            },
            "packaging": {
                "output_dir": "./output",
                "intune_win_util_path": "./tools/IntuneWinAppUtil.exe",
                "auto_download_util": True,
            },
            "app_defaults": {
                "publisher": "IT Department",
                "install_experience": "system",
                "restart_behavior": "suppress",
            },
            "reporting": {
                "output_dir": "./reports",
                "template_dir": "./templates",
                "history_file": "./deployment_history.json",
            },
        }
    
    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        
        Args:
            key: Configuration key (e.g., "azure.tenant_id")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def validate_azure_config(self) -> bool:
        """Validate Azure AD configuration is present."""
        required = ["azure.tenant_id", "azure.client_id", "azure.client_secret"]
        missing = [key for key in required if not self.get(key)]
        
        if missing:
            raise ConfigurationError(
                f"Missing required Azure configuration: {', '.join(missing)}\n"
                "Please configure these values in config.yaml"
            )
        return True
    
    @property
    def azure(self) -> dict:
        """Get Azure configuration section."""
        return self._config.get("azure", {})
    
    @property
    def intune(self) -> dict:
        """Get Intune configuration section."""
        return self._config.get("intune", {})
    
    @property
    def packaging(self) -> dict:
        """Get packaging configuration section."""
        return self._config.get("packaging", {})
    
    @property
    def app_defaults(self) -> dict:
        """Get app defaults configuration section."""
        return self._config.get("app_defaults", {})
    
    @property
    def reporting(self) -> dict:
        """Get reporting configuration section."""
        return self._config.get("reporting", {})


# Global configuration instance
_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """Get or create global configuration instance."""
    global _config
    if _config is None or config_path:
        _config = Config(config_path)
    return _config
