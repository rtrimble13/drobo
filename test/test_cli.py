"""
Tests for drobo CLI.
"""

import logging
import logging.handlers

from click.testing import CliRunner

from drobo.cli import cli
from drobo.config import AppConfig
from drobo.dropbox_client import DroboAuthError


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

    def test_ls_without_path_argument_defaults_to_remote_root(self, mocker):
        """`drobo <app> ls` with no PATH must target the remote root.

        Regression: the argument default used to be "/", which
        ls_with_options rejects as a local path, so the bare command
        always exited 1.
        """
        mock_config_manager = mocker.patch("drobo.cli.ConfigManager")
        mock_setup_commands = mocker.patch("drobo.cli.setup_commands")

        mock_manager = mocker.Mock()
        mock_manager.get_app_config.return_value = AppConfig(
            "test_app",
            {
                "app_key": "test_key",
                "app_secret": "test_secret",
                "access_token": "test_token",
            },
        )
        mock_config_manager.return_value = mock_manager
        mock_setup_commands.return_value = mocker.Mock()

        runner = CliRunner()
        result = runner.invoke(cli, ["test_app", "ls"])

        assert result.exit_code == 0
        assert (
            mock_setup_commands.return_value.ls_with_options.call_args.kwargs[
                "path"
            ]
            == "//"
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

    def test_config_option_is_passed_to_the_config_manager(self, mocker):
        """--config must point drobo at an alternate config file."""
        mock_config_manager = mocker.patch("drobo.cli.ConfigManager")
        mock_setup_commands = mocker.patch("drobo.cli.setup_commands")

        mock_manager = mocker.Mock()
        mock_manager.get_app_config.return_value = AppConfig(
            "test_app",
            {
                "app_key": "k",
                "app_secret": "s",
                "access_token": "a",
            },
        )
        mock_config_manager.return_value = mock_manager
        mock_setup_commands.return_value = mocker.Mock()

        runner = CliRunner()
        result = runner.invoke(
            cli, ["--config", "/tmp/alt.droborc", "test_app", "ls", "//"]
        )

        assert result.exit_code == 0
        assert str(mock_config_manager.call_args.args[0]) == "/tmp/alt.droborc"

    def test_config_manager_is_built_once_and_shared(self, mocker):
        """One ConfigManager per invocation, shared with the handler.

        Regression: CommandHandler built a second manager of its own, so
        the config file was read twice and token writes updated a
        different AppConfig object than the client was using.
        """
        mock_config_manager = mocker.patch("drobo.cli.ConfigManager")
        mock_setup_commands = mocker.patch("drobo.cli.setup_commands")

        mock_manager = mocker.Mock()
        mock_manager.get_app_config.return_value = AppConfig(
            "test_app",
            {"app_key": "k", "app_secret": "s", "access_token": "a"},
        )
        mock_config_manager.return_value = mock_manager
        mock_setup_commands.return_value = mocker.Mock()

        runner = CliRunner()
        result = runner.invoke(cli, ["test_app", "ls", "//"])

        assert result.exit_code == 0
        assert mock_config_manager.call_count == 1
        # The same manager instance is handed to the command handler.
        assert mock_setup_commands.call_args.args[1] is mock_manager


class TestLogging:
    """Log configuration."""

    def test_log_file_is_rotated(self, mocker, tmp_path):
        """The log must not grow without bound."""
        mocker.patch("drobo.cli.Path.home", return_value=tmp_path)
        mock_basic = mocker.patch("drobo.cli.logging.basicConfig")

        from drobo.cli import setup_logging

        setup_logging(verbose=False)

        handlers = mock_basic.call_args.kwargs["handlers"]
        rotating = [
            h
            for h in handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(rotating) == 1
        assert rotating[0].maxBytes > 0
        assert rotating[0].backupCount > 0

    def test_verbose_does_not_turn_on_third_party_debug_logging(
        self, mocker, tmp_path
    ):
        """--verbose must scope to drobo, not the root logger.

        Turning the root logger to DEBUG also switches on the Dropbox SDK
        and urllib3, which is noisy and puts request detail in the log file.
        """
        mocker.patch("drobo.cli.Path.home", return_value=tmp_path)
        mocker.patch("drobo.cli.logging.basicConfig")

        from drobo.cli import setup_logging

        setup_logging(verbose=True)

        assert logging.getLogger("drobo").level == logging.DEBUG
        assert logging.getLogger("urllib3").level != logging.DEBUG

    def test_unwritable_home_does_not_break_the_cli(self, mocker):
        """A read-only home should not stop drobo from running."""
        mocker.patch(
            "drobo.cli.logging.handlers.RotatingFileHandler",
            side_effect=OSError("read-only file system"),
        )
        mock_basic = mocker.patch("drobo.cli.logging.basicConfig")

        from drobo.cli import setup_logging

        setup_logging(verbose=False)

        handlers = mock_basic.call_args.kwargs["handlers"]
        assert len(handlers) == 1  # stdout only


class TestAuthCommand:
    """The `auth` command is the only route to the interactive OAuth flow."""

    def _patch_config(self, mocker):
        mock_config_manager = mocker.patch("drobo.cli.ConfigManager")
        mock_manager = mocker.Mock()
        mock_manager.get_app_config.return_value = AppConfig(
            "test_app", {"app_key": "k", "app_secret": "s"}
        )
        mock_config_manager.return_value = mock_manager
        return mock_manager

    def test_auth_saves_the_returned_tokens(self, mocker):
        mock_manager = self._patch_config(mocker)
        mocker.patch(
            "drobo.cli.authorize_interactive",
            return_value=("new_access", "new_refresh"),
        )

        result = CliRunner().invoke(cli, ["test_app", "auth"])

        assert result.exit_code == 0
        mock_manager.save_app_tokens.assert_called_once_with(
            "test_app", "new_access", "new_refresh"
        )

    def test_auth_reports_a_missing_terminal_cleanly(self, mocker):
        """Without a TTY it must exit with a message, not hang."""
        self._patch_config(mocker)
        mocker.patch(
            "drobo.cli.authorize_interactive",
            side_effect=DroboAuthError("requires an interactive terminal"),
        )

        result = CliRunner().invoke(cli, ["test_app", "auth"])

        assert result.exit_code == 1
        assert "interactive terminal" in result.output


class TestCLIMisc:
    """Remaining CLI behaviour."""

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
            path="//",
            long_format=False,
            reverse=True,
            recursive=True,
            sort_by_size=False,
            sort_by_time=False,
        )
