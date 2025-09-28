"""
Tests for drobo command handlers.
"""

from unittest.mock import Mock

import pytest

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

        command_handler.ls_with_options(path="//test", directory=True)

        # Should show the directory itself, not contents
        mock_echo.assert_called_once_with("//test/")

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
            command_handler.ls_with_options(path="//restricted")

        # Should echo error message
        mock_echo.assert_called_with("ls: Access denied", err=True)

    def test_cp_with_T_flag(self, command_handler, mocker):
        """Test cp with -T flag (treat destination as file)."""
        # Mock methods used by cp
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )

        # Simulate local to remote copy
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.return_value = "/dest_file"
        mock_normalize_local_path.return_value = "/home/user/source_file"

        # Mock os.path methods
        mocker.patch("os.path.isfile", return_value=True)
        mock_upload = mocker.patch.object(command_handler.client, "upload_file")

        command_handler.cp(("-T", "/home/user/source_file", "//dest_file"))

        # Should upload to exact destination path
        mock_upload.assert_called_once_with(
            "/home/user/source_file", "/dest_file"
        )

    def test_cp_with_t_flag(self, command_handler, mocker):
        """Test cp with -t flag (target directory)."""
        # Mock methods used by cp
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )

        # Simulate local to remote copy
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.return_value = "/target_dir"
        mock_normalize_local_path.side_effect = [
            "/home/user/file1",
            "/home/user/file2",
        ]

        # Mock os.path methods
        mocker.patch("os.path.isfile", return_value=True)
        mock_upload = mocker.patch.object(command_handler.client, "upload_file")
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=True
        )

        command_handler.cp(
            ("-t", "//target_dir", "/home/user/file1", "/home/user/file2")
        )

        # Should upload both files to target directory
        assert mock_upload.call_count == 2
        mock_upload.assert_any_call("/home/user/file1", "/target_dir/file1")
        mock_upload.assert_any_call("/home/user/file2", "/target_dir/file2")

    def test_cp_remote_path_convention(self, command_handler, mocker):
        """Test cp with // remote path convention."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )

        # Test remote to local copy
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.return_value = "/remote/file"
        mock_normalize_local_path.return_value = "/home/user/local_file"

        # Mock client methods
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.return_value = {"type": "file", "name": "file"}
        mock_download = mocker.patch.object(
            command_handler.client, "download_file"
        )
        mocker.patch("os.path.isdir", return_value=False)

        command_handler.cp(("//remote/file", "/home/user/local_file"))

        mock_download.assert_called_once_with(
            "/remote/file", "/home/user/local_file"
        )

    def test_cp_recursive_flag(self, command_handler, mocker):
        """Test cp with -r flag for recursive directory copy."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )

        # Local directory to remote
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_local_path.return_value = "/home/user/local_dir"
        mock_normalize_remote_path.return_value = "/remote_dir"

        mocker.patch("os.path.isdir", return_value=True)
        mocker.patch("os.path.isfile", return_value=False)
        mock_upload_recursive = mocker.patch.object(
            command_handler, "_upload_directory_recursive"
        )

        command_handler.cp(("-r", "/home/user/local_dir", "//remote_dir"))

        mock_upload_recursive.assert_called_once_with(
            "/home/user/local_dir", "/remote_dir"
        )

    def test_cp_local_to_local_error(self, command_handler, mocker):
        """Test cp rejects local to local operations."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )

        # Both paths are local
        mock_is_remote_path.return_value = False
        mock_normalize_local_path.side_effect = [
            "/home/user/file1",
            "/home/user/file2",
        ]

        with pytest.raises(Exception) as exc_info:
            command_handler.cp(("/home/user/file1", "/home/user/file2"))

        assert "not used for copying local files to local destinations" in str(
            exc_info.value
        )

    def test_ls_remote_path_convention(self, command_handler, mocker):
        """Test ls with // remote path convention."""
        mock_items = [
            {
                "name": "file1.txt",
                "type": "file",
                "size": 100,
                "modified": "2023-01-01",
            },
            {"name": "folder1", "type": "folder"},
        ]
        command_handler.client.list_folder.return_value = mock_items

        mock_echo = mocker.patch("drobo.commands.click.echo")

        # Test with // prefix
        command_handler.ls_with_options(path="//subdir")

        # Should call list_folder with normalized path
        command_handler.client.list_folder.assert_called_with("/subdir")
        expected_calls = [mocker.call("file1.txt"), mocker.call("folder1/")]
        mock_echo.assert_has_calls(expected_calls, any_order=False)

    def test_ls_root_directory_variants(self, command_handler, mocker):
        """Test ls with different root directory representations."""
        mock_items = [
            {
                "name": "file1.txt",
                "type": "file",
                "size": 100,
                "modified": "2023-01-01",
            },
        ]
        command_handler.client.list_folder.return_value = mock_items

        # Test with // (explicit remote root)
        command_handler.ls_with_options(path="//")
        command_handler.client.list_folder.assert_called_with("")

        # Test with / (default remote root)
        command_handler.ls_with_options(path="/")
        command_handler.client.list_folder.assert_called_with("")

    def test_ls_rejects_local_paths(self, command_handler):
        """Test ls rejects local paths that don't start with //."""
        with pytest.raises(ValueError) as exc_info:
            command_handler.ls_with_options(path="/local/path")

        assert "Local paths not supported in ls command" in str(exc_info.value)
        assert "Use // for remote paths" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            command_handler.ls_with_options(path="/etc")

        assert "Local paths not supported in ls command" in str(exc_info.value)
