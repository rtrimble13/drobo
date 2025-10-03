"""
Tests for drobo CLI.
"""

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

    def test_verbose_flag(self, mocker):
        """Test --verbose flag."""
        mock_setup = mocker.patch("drobo.cli.setup_logging")
        runner = CliRunner()
        # Need to provide required arguments but expect it to fail
        # due to missing config
        runner.invoke(cli, ["--verbose", "test_app", "ls"])
        mock_setup.assert_called_once_with(True)

    def test_app_command_ls(self, mocker):
        """Test app command execution."""
        # Mock config manager
        mock_config_manager = mocker.patch("drobo.cli.ConfigManager")
        mock_setup_commands = mocker.patch("drobo.cli.setup_commands")

        mock_manager = mocker.Mock()
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
        mock_handler = mocker.Mock()
        mock_setup_commands.return_value = mock_handler

        runner = CliRunner()
        result = runner.invoke(cli, ["test_app", "ls", "/"])

        assert result.exit_code == 0
        mock_handler.ls_with_options.assert_called_once_with(
            path="/",
            long_format=False,
            reverse=False,
            recursive=False,
            sort_by_size=False,
            sort_by_time=False,
        )

    def test_app_command_nonexistent_app(self, mocker):
        """Test app command with non-existent app."""
        mock_config_manager = mocker.patch("drobo.cli.ConfigManager")
        mock_manager = mocker.Mock()
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

    def test_ls_option_parsing(self, mocker):
        """Test ls command option parsing."""
        # Mock config manager
        mock_config_manager = mocker.patch("drobo.cli.ConfigManager")
        mock_setup_commands = mocker.patch("drobo.cli.setup_commands")

        mock_manager = mocker.Mock()
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
        mock_handler = mocker.Mock()
        mock_setup_commands.return_value = mock_handler

        runner = CliRunner()
        result = runner.invoke(cli, ["test_app", "ls", "-l", "/test"])

        assert result.exit_code == 0
        mock_handler.ls_with_options.assert_called_once_with(
            path="/test",
            long_format=True,
            reverse=False,
            recursive=False,
            sort_by_size=False,
            sort_by_time=False,
        )

    def test_ls_all_options(self, mocker):
        """Test ls with all options enabled."""
        mock_config_manager = mocker.patch("drobo.cli.ConfigManager")
        mock_setup_commands = mocker.patch("drobo.cli.setup_commands")

        mock_manager = mocker.Mock()
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

        mock_handler = mocker.Mock()
        mock_setup_commands.return_value = mock_handler

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "test_app",
                "ls",
                "-l",
                "-r",
                "-R",
                "-S",
                "-t",
                "/test",
            ],
        )

        assert result.exit_code == 0
        mock_handler.ls_with_options.assert_called_once_with(
            path="/test",
            long_format=True,
            reverse=True,
            recursive=True,
            sort_by_size=True,
            sort_by_time=True,
        )

    def test_ls_long_options(self, mocker):
        """Test ls with long option names."""
        mock_config_manager = mocker.patch("drobo.cli.ConfigManager")
        mock_setup_commands = mocker.patch("drobo.cli.setup_commands")

        mock_manager = mocker.Mock()
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

        mock_handler = mocker.Mock()
        mock_setup_commands.return_value = mock_handler

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "test_app",
                "ls",
                "--reverse",
                "--recursive",
            ],
        )

        assert result.exit_code == 0
        mock_handler.ls_with_options.assert_called_once_with(
            path="/",
            long_format=False,
            reverse=True,
            recursive=True,
            sort_by_size=False,
            sort_by_time=False,
        )
