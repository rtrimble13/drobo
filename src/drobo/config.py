"""
Configuration management for drobo.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from configistate import Config

logger = logging.getLogger(__name__)


class AppConfig:
    """Configuration for a Dropbox app."""

    def __init__(self, name: str, config_data: Dict) -> None:
        self.name = name
        self.app_key = config_data.get("app_key")
        self.app_secret = config_data.get("app_secret")
        self.access_token = config_data.get("access_token")
        self.refresh_token = config_data.get("refresh_token")

        if not all([self.app_key, self.app_secret]):
            raise ValueError(
                f"App '{name}' missing required app_key or app_secret"
            )

        # Check for placeholder values
        if self.app_key == "your_dropbox_app_key_here":
            raise ValueError(
                f"App '{name}' has placeholder app_key - "
                "please configure with real values"
            )

    def has_valid_tokens(self) -> bool:
        """Check if the app has valid access tokens."""
        return bool(self.access_token)

    def update_tokens(
        self, access_token: str, refresh_token: str = None
    ) -> None:
        """Update the access and refresh tokens."""
        self.access_token = access_token
        if refresh_token:
            self.refresh_token = refresh_token


class ConfigManager:
    """Manages drobo configuration using configistate.Config."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or Path.home() / ".droborc"
        # Ensure config_path is a Path object
        if not isinstance(self.config_path, Path):
            self.config_path = Path(self.config_path)
        self._config = Config()
        self._apps = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from .droborc file."""
        if not self.config_path.exists():
            logger.warning(f"Config file {self.config_path} does not exist")
            self._create_default_config()
            # Reload after creating default config
            return self._load_config()

        try:
            self._config.load(self.config_path)

            # Load apps from config
            apps_config = self._config.get("apps", {})
            for app_name, app_data in apps_config.items():
                try:
                    self._apps[app_name] = AppConfig(app_name, app_data)
                    logger.debug(f"Loaded app config: {app_name}")
                except ValueError as e:
                    logger.error(f"Invalid config for app '{app_name}': {e}")

            logger.info(f"Loaded {len(self._apps)} app configurations")

        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            raise

    def _create_default_config(self) -> None:
        """Create a default configuration file."""
        # Set default configuration using configistate
        self._config.set("apps.example.app_key", "your_dropbox_app_key_here")
        self._config.set(
            "apps.example.app_secret", "your_dropbox_app_secret_here"
        )
        self._config.set("apps.example.access_token", "")
        self._config.set("apps.example.refresh_token", "")

        try:
            self._config.save(self.config_path)
            logger.info(f"Created default config at {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to create default config: {e}")
            raise

    def get_app_config(self, app_name: str) -> Optional[AppConfig]:
        """Get configuration for a specific app."""
        return self._apps.get(app_name)

    def list_apps(self) -> Dict[str, AppConfig]:
        """Get all configured apps."""
        return self._apps.copy()

    def save_app_tokens(
        self, app_name: str, access_token: str, refresh_token: str = None
    ) -> None:
        """Save updated tokens for an app."""
        if app_name not in self._apps:
            raise ValueError(f"App '{app_name}' not found")

        # Update in memory
        self._apps[app_name].update_tokens(access_token, refresh_token)

        # Update configuration using configistate
        try:
            self._config.set(f"apps.{app_name}.access_token", access_token)
            if refresh_token:
                self._config.set(
                    f"apps.{app_name}.refresh_token", refresh_token
                )

            self._config.save(self.config_path)
            logger.info(f"Updated tokens for app '{app_name}'")

        except Exception as e:
            logger.error(f"Failed to save tokens for app '{app_name}': {e}")
            raise
