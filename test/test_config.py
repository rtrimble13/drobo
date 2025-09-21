"""
Tests for drobo configuration management.
"""

import pytest

from drobo.config import AppConfig, ConfigManager


class TestAppConfig:
    """Test AppConfig class."""

    def test_app_config_creation(self):
        """Test creating an AppConfig instance."""
        config_data = {
            "app_key": "test_key",
            "app_secret": "test_secret",
            "access_token": "test_token",
            "refresh_token": "test_refresh",
        }

        app_config = AppConfig("test_app", config_data)

        assert app_config.name == "test_app"
        assert app_config.app_key == "test_key"
        assert app_config.app_secret == "test_secret"
        assert app_config.access_token == "test_token"
        assert app_config.refresh_token == "test_refresh"

    def test_app_config_missing_required(self):
        """Test AppConfig with missing required fields."""
        config_data = {
            "app_key": "test_key"
            # Missing app_secret
        }

        with pytest.raises(
            ValueError, match="missing required app_key or app_secret"
        ):
            AppConfig("test_app", config_data)

    def test_has_valid_tokens(self):
        """Test token validation."""
        config_data = {
            "app_key": "test_key",
            "app_secret": "test_secret",
            "access_token": "test_token",
        }

        app_config = AppConfig("test_app", config_data)
        assert app_config.has_valid_tokens()

        app_config.access_token = None
        assert not app_config.has_valid_tokens()

    def test_update_tokens(self):
        """Test token updates."""
        config_data = {"app_key": "test_key", "app_secret": "test_secret"}

        app_config = AppConfig("test_app", config_data)
        app_config.update_tokens("new_access", "new_refresh")

        assert app_config.access_token == "new_access"
        assert app_config.refresh_token == "new_refresh"


class TestConfigManager:
    """Test ConfigManager class."""

    def test_config_manager_creation(self, tmp_path):
        """Test creating a ConfigManager instance."""
        config_path = tmp_path / ".droborc"
        ConfigManager(config_path)

        # Should create default config
        assert config_path.exists()

    def test_load_existing_config(self, tmp_path):
        """Test loading an existing config file."""
        config_path = tmp_path / ".droborc"

        # Create test config using configistate
        from configistate import Config

        test_config = Config()
        test_config.set("apps.myapp.app_key", "test_key")
        test_config.set("apps.myapp.app_secret", "test_secret")
        test_config.set("apps.myapp.access_token", "test_token")
        test_config.save(config_path)

        manager = ConfigManager(config_path)
        app_config = manager.get_app_config("myapp")

        assert app_config is not None
        assert app_config.name == "myapp"
        assert app_config.app_key == "test_key"

    def test_get_nonexistent_app(self, tmp_path):
        """Test getting a non-existent app."""
        config_path = tmp_path / ".droborc"
        manager = ConfigManager(config_path)

        app_config = manager.get_app_config("nonexistent")
        assert app_config is None

    def test_save_app_tokens(self, tmp_path):
        """Test saving app tokens."""
        config_path = tmp_path / ".droborc"

        # Create test config using configistate
        from configistate import Config

        test_config = Config()
        test_config.set("apps.myapp.app_key", "test_key")
        test_config.set("apps.myapp.app_secret", "test_secret")
        test_config.set("apps.myapp.access_token", "old_token")
        test_config.save(config_path)

        manager = ConfigManager(config_path)
        manager.save_app_tokens("myapp", "new_token", "new_refresh")

        # Verify tokens were saved
        app_config = manager.get_app_config("myapp")
        assert app_config.access_token == "new_token"
        assert app_config.refresh_token == "new_refresh"

        # Verify file was updated by loading it fresh
        fresh_config = Config()
        fresh_config.load(config_path)
        assert fresh_config.get("apps.myapp.access_token") == "new_token"
        assert fresh_config.get("apps.myapp.refresh_token") == "new_refresh"
