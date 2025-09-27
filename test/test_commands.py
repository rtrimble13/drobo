"""
Tests for drobo command handlers.
"""

import pytest
from unittest.mock import Mock

from drobo.commands import CommandHandler
from drobo.config import AppConfig


class TestCommandHandler:
    """Test CommandHandler class."""

    @pytest.fixture
    def app_config(self):
        """Create test app config."""
        return AppConfig(
            "test_app",
            {
                "app_key": "test_key",
                "app_secret": "test_secret",
                "access_token": "test_token",
            },
        )

    @pytest.fixture
    def command_handler(self, app_config, mocker):
        """Create command handler with mocked client."""
        mocker.patch("drobo.commands.ConfigManager")
        mocker.patch("drobo.commands.DropboxClient")

        handler = CommandHandler(app_config, verbose=False)
        handler.client = Mock()
        return handler

    def test_ls_with_options_basic(self, command_handler, mocker):
        """Test basic ls functionality."""
        mock_items = [
            {
                "name": "file1.txt",
                "type": "file",
                "size": 100,
                "modified": "2023-01-01",
            },
            {"name": "folder1", "type": "folder"},
            {
                "name": ".hidden",
                "type": "file",
                "size": 50,
                "modified": "2023-01-02",
            },
        ]
        command_handler.client.list_folder.return_value = mock_items

        # Mock click.echo to capture output
        mock_echo = mocker.patch("drobo.commands.click.echo")

        command_handler.ls_with_options(path="/")

        # Should show files and folders but not hidden files
        expected_calls = [mocker.call("file1.txt"), mocker.call("folder1/")]
        mock_echo.assert_has_calls(expected_calls, any_order=False)

    def test_ls_with_all_option(self, command_handler, mocker):
        """Test ls with -a/--all option."""
        mock_items = [
            {
                "name": "file1.txt",
                "type": "file",
                "size": 100,
                "modified": "2023-01-01",
            },
            {
                "name": ".hidden",
                "type": "file",
                "size": 50,
                "modified": "2023-01-02",
            },
        ]
        command_handler.client.list_folder.return_value = mock_items

        mock_echo = mocker.patch("drobo.commands.click.echo")

        command_handler.ls_with_options(path="/", show_all=True)

        # Should show all files including hidden ones
        expected_calls = [mocker.call(".hidden"), mocker.call("file1.txt")]
        mock_echo.assert_has_calls(expected_calls, any_order=False)

    def test_ls_with_long_format(self, command_handler, mocker):
        """Test ls with -l option."""
        from datetime import datetime

        mock_modified = datetime(2023, 1, 1, 12, 0)

        mock_items = [
            {
                "name": "file1.txt",
                "type": "file",
                "size": 100,
                "modified": mock_modified,
            },
            {"name": "folder1", "type": "folder"},
        ]
        command_handler.client.list_folder.return_value = mock_items

        mock_echo = mocker.patch("drobo.commands.click.echo")

        command_handler.ls_with_options(path="/", long_format=True)

        # Should show long format
        calls = mock_echo.call_args_list
        assert len(calls) == 2
        # Check that the output contains size and date info
        file_output = calls[0][0][0]
        folder_output = calls[1][0][0]
        assert "100" in file_output
        assert "2023-01-01 12:00" in file_output
        assert "drwxr-xr-x" in folder_output

    def test_ls_with_directory_option(self, command_handler, mocker):
        """Test ls with -d/--directory option."""
        mock_echo = mocker.patch("drobo.commands.click.echo")

        command_handler.ls_with_options(path="/test", directory=True)

        # Should show the directory itself, not contents
        mock_echo.assert_called_once_with("/test/")

    def test_ls_with_reverse_option(self, command_handler, mocker):
        """Test ls with -r/--reverse option."""
        mock_items = [
            {
                "name": "a_file.txt",
                "type": "file",
                "size": 100,
                "modified": "2023-01-01",
            },
            {
                "name": "b_file.txt",
                "type": "file",
                "size": 200,
                "modified": "2023-01-02",
            },
            {
                "name": "z_file.txt",
                "type": "file",
                "size": 300,
                "modified": "2023-01-03",
            },
        ]
        command_handler.client.list_folder.return_value = mock_items

        mock_echo = mocker.patch("drobo.commands.click.echo")

        command_handler.ls_with_options(path="/", reverse=True)

        # Should show files in reverse alphabetical order
        expected_calls = [
            mocker.call("z_file.txt"),
            mocker.call("b_file.txt"),
            mocker.call("a_file.txt"),
        ]
        mock_echo.assert_has_calls(expected_calls, any_order=False)

    def test_ls_with_sort_by_size(self, command_handler, mocker):
        """Test ls with -S option."""
        mock_items = [
            {
                "name": "small.txt",
                "type": "file",
                "size": 100,
                "modified": "2023-01-01",
            },
            {
                "name": "large.txt",
                "type": "file",
                "size": 300,
                "modified": "2023-01-02",
            },
            {
                "name": "medium.txt",
                "type": "file",
                "size": 200,
                "modified": "2023-01-03",
            },
        ]
        command_handler.client.list_folder.return_value = mock_items

        mock_echo = mocker.patch("drobo.commands.click.echo")

        command_handler.ls_with_options(path="/", sort_by_size=True)

        # Should show files sorted by size, largest first
        expected_calls = [
            mocker.call("large.txt"),
            mocker.call("medium.txt"),
            mocker.call("small.txt"),
        ]
        mock_echo.assert_has_calls(expected_calls, any_order=False)

    def test_ls_with_sort_by_time(self, command_handler, mocker):
        """Test ls with -t option."""
        mock_items = [
            {
                "name": "old.txt",
                "type": "file",
                "size": 100,
                "modified": "2023-01-01",
            },
            {
                "name": "newest.txt",
                "type": "file",
                "size": 200,
                "modified": "2023-01-03",
            },
            {
                "name": "newer.txt",
                "type": "file",
                "size": 300,
                "modified": "2023-01-02",
            },
        ]
        command_handler.client.list_folder.return_value = mock_items

        mock_echo = mocker.patch("drobo.commands.click.echo")

        command_handler.ls_with_options(path="/", sort_by_time=True)

        # Should show files sorted by time, newest first
        expected_calls = [
            mocker.call("newest.txt"),  # 2023-01-03
            mocker.call("newer.txt"),  # 2023-01-02
            mocker.call("old.txt"),  # 2023-01-01
        ]
        mock_echo.assert_has_calls(expected_calls, any_order=False)

    def test_ls_with_recursive_option(self, command_handler, mocker):
        """Test ls with -R/--recursive option."""
        # Mock the _list_folder_recursive method
        mock_recursive_items = [
            {
                "name": "file1.txt",
                "type": "file",
                "size": 100,
                "modified": "2023-01-01",
            },
            {
                "name": "subdir/file2.txt",
                "type": "file",
                "size": 200,
                "modified": "2023-01-02",
            },
        ]

        # Mock the recursive method directly
        command_handler._list_folder_recursive = Mock(
            return_value=mock_recursive_items
        )

        mock_echo = mocker.patch("drobo.commands.click.echo")

        command_handler.ls_with_options(path="/", recursive=True)

        # Should show files recursively
        expected_calls = [
            mocker.call("file1.txt"),
            mocker.call("subdir/file2.txt"),
        ]
        mock_echo.assert_has_calls(expected_calls, any_order=False)

    def test_ls_combined_options(self, command_handler, mocker):
        """Test ls with combined options like -la."""
        mock_items = [
            {
                "name": "file1.txt",
                "type": "file",
                "size": 100,
                "modified": "2023-01-01",
            },
            {
                "name": ".hidden",
                "type": "file",
                "size": 50,
                "modified": "2023-01-02",
            },
        ]
        command_handler.client.list_folder.return_value = mock_items

        mock_echo = mocker.patch("drobo.commands.click.echo")

        command_handler.ls_with_options(
            path="/", show_all=True, long_format=True
        )

        # Should show all files in long format
        calls = mock_echo.call_args_list
        assert len(calls) == 2
        # Check that hidden files are shown and in long format
        hidden_output = calls[0][0][0]
        file_output = calls[1][0][0]
        assert ".hidden" in hidden_output
        assert "50" in hidden_output
        assert "file1.txt" in file_output
        assert "100" in file_output

    def test_ls_error_handling(self, command_handler, mocker):
        """Test ls error handling."""
        command_handler.client.list_folder.side_effect = Exception(
            "Access denied"
        )

        mock_echo = mocker.patch("drobo.commands.click.echo")

        with pytest.raises(Exception):
            command_handler.ls_with_options(path="/restricted")

        # Should echo error message
        mock_echo.assert_called_with("ls: Access denied", err=True)
