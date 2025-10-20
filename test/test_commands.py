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

        command_handler.ls_with_options(path="//")

        # Should show files and folders but not hidden files
        expected_calls = [
            mocker.call("file1.txt"),
        ]  # mocker.call("folder1/")]
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

        command_handler.ls_with_options(path="//", long_format=True)

        # Should show long format
        calls = mock_echo.call_args_list
        assert len(calls) == 2
        # Check that the output contains size and date info
        file_output = calls[0][0][0]
        assert "100" in file_output
        assert "2023-01-01 12:00" in file_output

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

        command_handler.ls_with_options(path="//", reverse=True)

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

        command_handler.ls_with_options(path="//", sort_by_size=True)

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

        command_handler.ls_with_options(path="//", sort_by_time=True)

        # Should show files sorted by time, newest first
        expected_calls = [
            mocker.call("newest.txt"),  # 2023-01-03
            mocker.call("newer.txt"),  # 2023-01-02
            mocker.call("old.txt"),  # 2023-01-01
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

        command_handler.ls_with_options(path="//", long_format=True)

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
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_glob = mocker.patch("glob.glob")
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate local to remote copy
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_has_wildcards.return_value = False
        mock_glob.return_value = []
        mock_normalize_remote_path.return_value = "//dest_file"
        mock_normalize_local_path.return_value = "/home/user/source_file"
        mock_expand_source_wildcards.return_value = ["/home/user/source_file"]

        # Mock os.path methods
        mocker.patch("os.path.isfile", return_value=True)
        mock_upload = mocker.patch.object(command_handler.client, "upload_file")

        command_handler.cp_with_options(
            sources=("/home/user/source_file", "//dest_file"),
            treat_as_file=True,
        )

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
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_glob = mocker.patch("glob.glob")
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate local to remote copy
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_has_wildcards.return_value = False
        mock_glob.return_value = []
        mock_normalize_remote_path.return_value = "//target_dir"
        mock_normalize_local_path.side_effect = [
            "/home/user/file1",
            "/home/user/file2",
        ]
        mock_expand_source_wildcards.return_value = [
            "/home/user/file1",
            "/home/user/file2",
        ]

        # Mock os.path methods
        mocker.patch("os.path.isfile", return_value=True)
        mock_upload = mocker.patch.object(command_handler.client, "upload_file")
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=True
        )

        command_handler.cp_with_options(
            sources=("/home/user/file1", "/home/user/file2"),
            target_directory="//target_dir",
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
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_glob = mocker.patch("glob.glob")

        # Test remote to local copy
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_has_wildcards.return_value = False
        mock_glob.return_value = []
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

        command_handler.cp_with_options(
            sources=("//remote/file", "/home/user/local_file")
        )

        mock_download.assert_called_once_with(
            "remote/file", "/home/user/local_file"
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
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_glob = mocker.patch("glob.glob")
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )
        mock_validate_destination = mocker.patch(
            "drobo.commands.CommandHandler."
            "_validate_destination_for_multiple_files"
        )

        # Local directory to remote
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_has_wildcards.return_value = False
        mock_glob.return_value = []
        mock_normalize_local_path.return_value = "/home/user/local_dir"
        mock_normalize_remote_path.return_value = "/remote_dir"

        mocker.patch("os.path.isdir", return_value=True)
        mocker.patch("os.path.isfile", return_value=False)
        mock_upload_recursive = mocker.patch.object(
            command_handler, "_upload_directory_recursive"
        )
        mock_expand_source_wildcards.return_value = [
            "/home/user/local_dir/file1.pdf",
            "/home/user/local_dir/file2.pdf",
        ]
        mock_validate_destination.return_value = None

        command_handler.cp_with_options(
            sources=("/home/user/local_dir", "//remote_dir"), recursive=True
        )

        assert mock_upload_recursive.call_count == 2
        mock_upload_recursive.assert_called_with(
            "/home/user/local_dir", "remote_dir"
        )

    def test_cp_local_to_local_error(self, command_handler, mocker):
        """Test cp rejects local to local operations."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_glob = mocker.patch("glob.glob")
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Both paths are local
        mock_is_remote_path.return_value = False
        mock_has_wildcards.return_value = False
        mock_glob.return_value = []
        mock_normalize_local_path.side_effect = [
            "/home/user/file1",
            "/home/user/file2",
        ]
        mock_expand_source_wildcards.return_value = [
            "/home/user/file1",
        ]

        with pytest.raises(Exception) as exc_info:
            command_handler.cp_with_options(
                sources=("/home/user/file1", "/home/user/file2")
            )

        assert "not used for copying local files to local destinations" in str(
            exc_info.value
        )

    def test_cp_with_local_wildcard(self, command_handler, mocker):
        """Test cp with local file wildcards."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_glob = mocker.patch("glob.glob")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )

        # Simulate local wildcard to remote copy
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_has_wildcards.side_effect = lambda x: "*" in x
        mock_glob.return_value = [
            "/home/user/file1.pdf",
            "/home/user/file2.pdf",
        ]
        mock_normalize_remote_path.return_value = "/remote_dir"
        mock_normalize_local_path.side_effect = [
            "/home/user/file1.pdf",
            "/home/user/file2.pdf",
        ]

        # Mock os.path and client methods
        mocker.patch("os.path.isfile", return_value=True)
        mocker.patch("os.path.isdir", return_value=False)
        mock_upload = mocker.patch.object(command_handler.client, "upload_file")
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=True
        )

        command_handler.cp_with_options(
            sources=("/home/user/*.pdf", "//remote_dir")
        )

        # Should upload both matched files
        assert mock_upload.call_count == 2

    def test_cp_with_remote_wildcard(self, command_handler, mocker):
        """Test cp with remote file wildcards."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )
        mock_list_folder = mocker.patch.object(
            command_handler.client, "list_folder"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote wildcard to local copy
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_has_wildcards.side_effect = lambda x: "*" in x
        mock_normalize_local_path.side_effect = [
            "/local_dir",
            "/subdir/file1.pdf",
            "/subdir/file2.pdf",
        ]

        # Mock list_folder to return pdf files
        mock_list_folder.return_value = [
            {
                "name": "file1.pdf",
                "type": "file",
                "path": "/subdir/file1.pdf",
            },
            {
                "name": "file2.pdf",
                "type": "file",
                "path": "/subdir/file2.pdf",
            },
        ]

        mock_expand_source_wildcards.return_value = [
            "//subdir/file1.pdf",
            "//subdir/file2.pdf",
        ]

        # Mock os.path and client methods
        mocker.patch("os.path.isdir", return_value=True)
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.return_value = {"type": "file"}
        mock_download = mocker.patch.object(
            command_handler.client, "download_file"
        )

        command_handler.cp_with_options(
            sources=("//subdir/*.pdf", "/local_dir")
        )

        # Should download both matched files
        assert mock_download.call_count == 2

    def test_cp_mixed_source_types_error(self, command_handler, mocker):
        """Test cp rejects mixed remote and local sources."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_expanded_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )
        mock_glob = mocker.patch("glob.glob")

        # Mix of remote and local
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_has_wildcards.return_value = False
        mock_glob.return_value = []
        mock_expanded_wildcards.return_value = [
            "/home/user/file1",
            "//remote/file2",
        ]

        with pytest.raises(Exception) as exc_info:
            command_handler.cp_with_options(
                sources=("/home/user/file1", "//remote/file2", "/dest")
            )

        assert "cannot mix remote and local source files" in str(exc_info.value)

    def test_cp_multiple_files_non_directory_dest_error(
        self, command_handler, mocker
    ):
        """Test cp rejects multiple files to non-directory destination."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_glob = mocker.patch("glob.glob")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )
        mock_expanded_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate multiple local files to remote non-directory
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_has_wildcards.return_value = False
        mock_glob.return_value = []
        mock_normalize_local_path.side_effect = [
            "/home/user/file1",
            "/home/user/file2",
        ]
        mock_normalize_remote_path.return_value = "/remote_file"

        # Mock destination as non-directory
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=False
        )

        mock_expanded_wildcards.return_value = [
            "/home/user/file1",
            "/home/user/file2",
        ]

        with pytest.raises(Exception) as exc_info:
            command_handler.cp_with_options(
                sources=(
                    "/home/user/file1",
                    "/home/user/file2",
                    "//remote_file",
                )
            )

        assert "is not a directory" in str(exc_info.value)

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
        command_handler.client.list_folder.assert_called_with(
            "/subdir", recursive=False
        )
        expected_calls = [
            mocker.call("file1.txt"),
        ]  # mocker.call("folder1/", fg="yellow", bold=True)]
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
        command_handler.client.list_folder.assert_called_with(
            "", recursive=False
        )

        # Test with / (default remote root)
        command_handler.ls_with_options(path="//")
        command_handler.client.list_folder.assert_called_with(
            "", recursive=False
        )

    def test_ls_rejects_local_paths(self, command_handler):
        """Test ls rejects local paths that don't start with //."""
        with pytest.raises(Exception) as exc_info:
            command_handler.ls_with_options(path="/local/path")

        # check for exception raised for local paths
        assert "ls requires a remote path" in str(exc_info.value)

        with pytest.raises(Exception) as exc_info:
            command_handler.ls_with_options(path="/etc")

        assert "ls requires a remote path" in str(exc_info.value)

    def test_mv_with_t_flag(self, command_handler, mocker):
        """Test mv with -t flag (target directory)."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate local to remote move
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.return_value = "//target_dir"
        mock_normalize_local_path.side_effect = [
            "/home/user/file1",
            "/home/user/file2",
        ]
        mock_expand_source_wildcards.return_value = [
            "/home/user/file1",
            "/home/user/file2",
        ]

        # Mock methods
        mocker.patch("os.path.exists", return_value=True)
        mocker.patch("os.path.isdir", return_value=True)
        mocker.patch("os.remove")
        mock_upload = mocker.patch.object(command_handler.client, "upload_file")
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.side_effect = Exception("not found")
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=True
        )

        command_handler.mv_with_options(
            sources=("/home/user/file1", "/home/user/file2"),
            target_directory="//target_dir",
        )

        # Should upload both files to target directory
        assert mock_upload.call_count == 2
        mock_upload.assert_any_call("/home/user/file1", "/target_dir/file1")
        mock_upload.assert_any_call("/home/user/file2", "/target_dir/file2")

    def test_mv_with_force_flag(self, command_handler, mocker):
        """Test mv with -f flag (force overwrite)."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote to remote move
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.side_effect = [
            "//source_file",
            "//dest_file",
        ]
        mock_expand_source_wildcards.return_value = ["//source_file"]

        # Mock destination exists
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.return_value = {
            "type": "file",
            "modified": "2023-01-01",
        }
        mock_move = mocker.patch.object(command_handler.client, "move_file")
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=False
        )

        command_handler.mv_with_options(
            sources=("//source_file", "//dest_file"), force=True
        )

        # Should move even though destination exists
        mock_move.assert_called_once_with("/source_file", "/dest_file")

    def test_mv_without_force_flag_dest_exists(self, command_handler, mocker):
        """Test mv without -f flag raises error when destination exists."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote to remote move
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.side_effect = [
            "//source_file",
            "//dest_file",
        ]
        mock_expand_source_wildcards.return_value = ["//source_file"]

        # Mock destination exists
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.return_value = {
            "type": "file",
            "modified": "2023-01-01",
        }
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=False
        )

        with pytest.raises(Exception) as exc_info:
            command_handler.mv_with_options(
                sources=("//source_file", "//dest_file"), force=False
            )

        assert "destination file exists" in str(exc_info.value)

    def test_mv_with_update_flag_newer_source(self, command_handler, mocker):
        """Test mv with -u flag moves when source is newer."""
        from datetime import datetime

        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote to remote move
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.side_effect = [
            "//source_file",
            "//dest_file",
        ]
        mock_expand_source_wildcards.return_value = ["//source_file"]

        # Mock metadata with newer source
        source_time = datetime(2023, 1, 2)
        dest_time = datetime(2023, 1, 1)
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.side_effect = [
            {"type": "file", "modified": dest_time},
            {"type": "file", "modified": source_time},
        ]

        mock_move = mocker.patch.object(command_handler.client, "move_file")
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=False
        )

        command_handler.mv_with_options(
            sources=("//source_file", "//dest_file"), update=True
        )

        # Should move because source is newer
        mock_move.assert_called_once_with("/source_file", "/dest_file")

    def test_mv_with_update_flag_older_source(self, command_handler, mocker):
        """Test mv with -u flag skips when source is older."""
        from datetime import datetime

        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote to remote move
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.side_effect = [
            "//source_file",
            "//dest_file",
        ]
        mock_expand_source_wildcards.return_value = ["//source_file"]

        # Mock metadata with older source
        source_time = datetime(2023, 1, 1)
        dest_time = datetime(2023, 1, 2)
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.side_effect = [
            {"type": "file", "modified": dest_time},
            {"type": "file", "modified": source_time},
        ]

        mock_move = mocker.patch.object(command_handler.client, "move_file")
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=False
        )

        command_handler.mv_with_options(
            sources=("//source_file", "//dest_file"), update=True
        )

        # Should not move because source is older
        mock_move.assert_not_called()

    def test_mv_with_wildcards(self, command_handler, mocker):
        """Test mv with wildcard expansion."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_list_folder = mocker.patch.object(
            command_handler.client, "list_folder"
        )

        # Simulate remote wildcard to remote directory
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_has_wildcards.side_effect = lambda x: "*" in x

        # Return normalized paths for source and destination
        def normalize_side_effect(path):
            if "*.pdf" in path:
                return "//subdir/*.pdf"
            elif "target_dir" in path:
                return "//target_dir"
            elif "file1.pdf" in path:
                return "//subdir/file1.pdf"
            elif "file2.pdf" in path:
                return "//subdir/file2.pdf"
            else:
                return path

        mock_normalize_remote_path.side_effect = normalize_side_effect

        # Mock list_folder to return pdf files
        mock_list_folder.return_value = [
            {
                "name": "file1.pdf",
                "type": "file",
                "path": "/subdir/file1.pdf",
            },
            {
                "name": "file2.pdf",
                "type": "file",
                "path": "/subdir/file2.pdf",
            },
        ]

        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.side_effect = Exception("not found")
        mock_move = mocker.patch.object(command_handler.client, "move_file")
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=True
        )

        command_handler.mv_with_options(
            sources=("//subdir/*.pdf", "//target_dir")
        )

        # Should move both matched files
        assert mock_move.call_count == 2

    def test_mv_multiple_sources_to_directory(self, command_handler, mocker):
        """Test mv with multiple sources to a directory."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_has_wildcards = mocker.patch("drobo.commands._has_wildcards")
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote to remote move
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_has_wildcards.return_value = False

        # Return normalized paths for all calls
        def normalize_side_effect(path):
            if "file1" in path:
                return "//file1"
            elif "file2" in path:
                return "//file2"
            elif "target_dir" in path:
                return "//target_dir"
            else:
                return path

        mock_normalize_remote_path.side_effect = normalize_side_effect
        mock_expand_source_wildcards.return_value = ["//file1", "//file2"]

        # Mock methods
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.side_effect = Exception("not found")
        mock_move = mocker.patch.object(command_handler.client, "move_file")
        mocker.patch.object(
            command_handler, "_is_remote_directory", return_value=True
        )

        command_handler.mv_with_options(
            sources=("//file1", "//file2", "//target_dir")
        )

        # Should move both files to target directory
        assert mock_move.call_count == 2
        mock_move.assert_any_call("/file1", "/target_dir/file1")
        mock_move.assert_any_call("/file2", "/target_dir/file2")

    def test_mv_local_to_local_error(self, command_handler, mocker):
        """Test mv rejects local to local operations."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_local_path = mocker.patch(
            "drobo.commands._normalize_local_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Both paths are local
        mock_is_remote_path.return_value = False
        mock_normalize_local_path.side_effect = [
            "/home/user/file1",
            "/home/user/file2",
        ]
        mock_expand_source_wildcards.return_value = ["/home/user/file1"]

        with pytest.raises(Exception) as exc_info:
            command_handler.mv_with_options(
                sources=("/home/user/file1", "/home/user/file2")
            )

        assert "not used for moving local files to local destinations" in str(
            exc_info.value
        )

    def test_mv_mixed_source_types_error(self, command_handler, mocker):
        """Test mv rejects mixed remote and local sources."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Mix of remote and local
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_expand_source_wildcards.return_value = [
            "/home/user/file1",
            "//remote/file2",
        ]

        with pytest.raises(Exception) as exc_info:
            command_handler.mv_with_options(
                sources=("/home/user/file1", "//remote/file2", "//dest")
            )

        assert "cannot mix remote and local source files" in str(exc_info.value)

    def test_rm_basic(self, command_handler, mocker):
        """Test basic rm functionality."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote file removal
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.return_value = "//file1"
        mock_expand_source_wildcards.return_value = ["//file1"]

        # Mock client methods
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.return_value = {"type": "file"}
        mock_delete = mocker.patch.object(command_handler.client, "delete_file")

        command_handler.rm_with_options(sources=("//file1",))

        # Should delete the file
        mock_delete.assert_called_once_with("/file1")

    def test_rm_multiple_files(self, command_handler, mocker):
        """Test rm with multiple files."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote file removal
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.side_effect = [
            "//file1",
            "//file2",
        ]
        mock_expand_source_wildcards.return_value = ["//file1", "//file2"]

        # Mock client methods
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.return_value = {"type": "file"}
        mock_delete = mocker.patch.object(command_handler.client, "delete_file")

        command_handler.rm_with_options(sources=("//file1", "//file2"))

        # Should delete both files
        assert mock_delete.call_count == 2
        mock_delete.assert_any_call("/file1")
        mock_delete.assert_any_call("/file2")

    def test_rm_with_wildcard(self, command_handler, mocker):
        """Test rm with wildcard expansion."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote wildcard expansion
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.side_effect = [
            "//subdir/file1.pdf",
            "//subdir/file2.pdf",
        ]

        # Mock expand_source_wildcards to return expanded files
        mock_expand_source_wildcards.return_value = [
            "//subdir/file1.pdf",
            "//subdir/file2.pdf",
        ]

        # Mock client methods
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.return_value = {"type": "file"}
        mock_delete = mocker.patch.object(command_handler.client, "delete_file")

        command_handler.rm_with_options(sources=("//subdir/*.pdf",))

        # Should delete both matched files
        assert mock_delete.call_count == 2

    def test_rm_directory_without_recursive_flag(self, command_handler, mocker):
        """Test rm rejects directory without -r flag."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote directory
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.return_value = "//directory"
        mock_expand_source_wildcards.return_value = ["//directory"]

        # Mock client methods
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.return_value = {"type": "folder"}

        with pytest.raises(Exception) as exc_info:
            command_handler.rm_with_options(sources=("//directory",))

        assert "Is a directory" in str(exc_info.value)

    def test_rm_directory_with_recursive_flag(self, command_handler, mocker):
        """Test rm with -r flag for recursive directory removal."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote directory
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.return_value = "//directory"
        mock_expand_source_wildcards.return_value = ["//directory"]

        # Mock client methods
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.return_value = {"type": "folder"}
        mock_delete = mocker.patch.object(command_handler.client, "delete_file")

        command_handler.rm_with_options(
            sources=("//directory",), recursive=True
        )

        # Should delete the directory
        mock_delete.assert_called_once_with("/directory")

    def test_rm_with_force_flag(self, command_handler, mocker):
        """Test rm with -f flag suppresses errors."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote file that doesn't exist
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.return_value = "//nonexistent"
        mock_expand_source_wildcards.return_value = ["//nonexistent"]

        # Mock client methods to raise exception
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.side_effect = Exception("not_found")

        # Should not raise exception with force flag
        command_handler.rm_with_options(sources=("//nonexistent",), force=True)

    def test_rm_without_force_flag_raises_error(self, command_handler, mocker):
        """Test rm without -f flag raises error on missing file."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_normalize_remote_path = mocker.patch(
            "drobo.commands._normalize_remote_path"
        )
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate remote file that doesn't exist
        mock_is_remote_path.side_effect = lambda x: x.startswith("//")
        mock_normalize_remote_path.return_value = "//nonexistent"
        mock_expand_source_wildcards.return_value = ["//nonexistent"]

        # Mock client methods to raise exception
        mock_get_metadata = mocker.patch.object(
            command_handler.client, "get_metadata"
        )
        mock_get_metadata.side_effect = Exception("not_found")

        with pytest.raises(Exception):
            command_handler.rm_with_options(sources=("//nonexistent",))

    def test_rm_rejects_local_paths(self, command_handler, mocker):
        """Test rm rejects local paths."""
        mock_is_remote_path = mocker.patch("drobo.commands._is_remote_path")
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate local path
        mock_is_remote_path.return_value = False
        mock_expand_source_wildcards.return_value = ["/local/file"]

        with pytest.raises(Exception) as exc_info:
            command_handler.rm_with_options(sources=("/local/file",))

        assert "rm requires remote paths" in str(exc_info.value)

    def test_rm_no_files_matched(self, command_handler, mocker):
        """Test rm with no matched files."""
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate no matched files
        mock_expand_source_wildcards.return_value = []

        with pytest.raises(Exception) as exc_info:
            command_handler.rm_with_options(sources=("//nonexistent*.pdf",))

        assert "no files matched" in str(exc_info.value)

    def test_rm_no_files_matched_with_force(self, command_handler, mocker):
        """Test rm with no matched files and force flag."""
        mock_expand_source_wildcards = mocker.patch(
            "drobo.commands.CommandHandler._expand_source_wildcards"
        )

        # Simulate no matched files
        mock_expand_source_wildcards.return_value = []

        # Should not raise exception with force flag
        command_handler.rm_with_options(
            sources=("//nonexistent*.pdf",), force=True
        )
