"""
Tests for drobo CLI.
"""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from drobo.cli import cli
from drobo.config import AppConfig


class TestCLI:
    """Test CLI functionality."""

    def test_version_flag(self):
        """Test --version flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0
        assert "drobo version" in result.output

    def test_help(self):
        """Test CLI help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "Drobo - A Dropbox CLI" in result.output
        assert "Usage: drobo <app name> <command> [options]" in result.output

    @patch("drobo.cli.setup_logging")
    def test_verbose_flag(self, mock_setup):
        """Test --verbose flag."""
        runner = CliRunner()
        # Need to provide required arguments but expect it to fail due to missing config
        runner.invoke(cli, ["--verbose", "test_app", "ls"])
        mock_setup.assert_called_once_with(True)

    @patch("drobo.cli.ConfigManager")
    @patch("drobo.cli.setup_commands")
    def test_app_command_ls(self, mock_setup_commands, mock_config_manager):
        """Test app command execution."""
        # Mock config manager
        mock_manager = Mock()
        mock_config = AppConfig(
            "test_app",
            {
                "app_key": "test_key",
                "app_secret": "test_secret",
                "access_token": "test_token",
            },
        )
        mock_manager.get_app_config.return_value = mock_config
        mock_config_manager.return_value = mock_manager

        # Mock command handler
        mock_handler = Mock()
        mock_setup_commands.return_value = mock_handler

        runner = CliRunner()
        result = runner.invoke(cli, ["test_app", "ls", "/"])

        assert result.exit_code == 0
        mock_handler.ls.assert_called_once_with(("/",))

    @patch("drobo.cli.ConfigManager")
    def test_app_command_nonexistent_app(self, mock_config_manager):
        """Test app command with non-existent app."""
        mock_manager = Mock()
        mock_manager.get_app_config.return_value = None
        mock_config_manager.return_value = mock_manager

        runner = CliRunner()
        result = runner.invoke(cli, ["nonexistent", "ls", "/"])

        assert result.exit_code == 1
        assert "App 'nonexistent' not found" in result.output

    def test_invalid_command(self):
        """Test invalid command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["test_app", "invalid", "/"])

        assert result.exit_code == 2  # Click error for invalid choice
