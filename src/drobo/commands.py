"""
Command handlers for drobo CLI commands.
"""

import logging
import os
from pathlib import Path
from typing import List, Tuple

import click

from drobo.config import AppConfig, ConfigManager
from drobo.dropbox_client import DropboxClient

logger = logging.getLogger(__name__)


def _is_remote_path(path: str) -> bool:
    """Check if path is a remote path (starts with //)."""
    return path.startswith("//")


def _normalize_remote_path(path: str) -> str:
    """Convert remote path from // prefix to Dropbox API format."""
    if path.startswith("//"):
        # Remove // prefix and ensure path starts with / for Dropbox API
        normalized = path[2:]  # Remove //
        if not normalized:
            return ""  # Root directory
        if not normalized.startswith("/"):
            normalized = "/" + normalized
        return normalized
    return path


def _normalize_local_path(path: str) -> str:
    """Expand and normalize local paths (~, ./, ../, etc)."""
    if path.startswith("~/"):
        return os.path.expanduser(path)
    return os.path.abspath(path)


class CommandHandler:
    """Handles all drobo commands."""

    def __init__(self, app_config: AppConfig, verbose: bool = False) -> None:
        self.app_config = app_config
        self.verbose = verbose
        self.config_manager = ConfigManager()
        self.client = DropboxClient(app_config, self.config_manager)

    def ls(self, args: Tuple[str, ...]) -> None:
        """List remote target contents. Mimic Linux ls command."""
        # Parse ls arguments
        path = "/"
        show_hidden = False
        long_format = False

        for arg in args:
            if arg.startswith("-"):
                if "a" in arg:
                    show_hidden = True
                if "l" in arg:
                    long_format = True
            else:
                path = arg

        # Handle remote path convention with // prefix
        if _is_remote_path(path):
            path = _normalize_remote_path(path)
        elif not path or path == "/":
            # Default to remote root when no path given or just "/"
            path = ""
        else:
            # All other paths (including /local/path) are not supported
            raise ValueError(
                f"Local paths not supported in ls command. Use // for "
                f"remote paths. Got: {path}"
            )

        try:
            items = self.client.list_folder(path)

            if not show_hidden:
                items = [
                    item for item in items if not item["name"].startswith(".")
                ]

            # Sort items by name (for backward compatibility)
            items = sorted(items, key=lambda x: x["name"])

            if long_format:
                self._print_long_format(items)
            else:
                self._print_simple_format(items)

        except Exception as e:
            click.echo(f"ls: {e}", err=True)
            raise

    def ls_with_options(
        self,
        path: str = "/",
        show_all: bool = False,
        directory: bool = False,
        long_format: bool = False,
        reverse: bool = False,
        recursive: bool = False,
        sort_by_size: bool = False,
        sort_by_time: bool = False,
    ) -> None:
        """List remote target contents with structured options."""
        # Store original path for display purposes
        original_path = path

        # Handle remote path convention with // prefix
        if _is_remote_path(path):
            path = _normalize_remote_path(path)
        elif not path or path == "/":
            # Default to remote root when no path given or just "/"
            path = ""
        else:
            # All other paths are not supported
            raise ValueError(
                f"Local paths not supported in ls command. Use // for "
                f"remote paths. Got: {path}"
            )

        try:
            if directory:
                # List the directory itself, not its contents
                if _is_remote_path(original_path):
                    display_path = original_path
                elif original_path == "/" or not original_path:
                    display_path = "//"
                else:
                    display_path = "//" + original_path
                click.echo(f"{display_path}/")
                return

            if recursive:
                items = self._list_folder_recursive(path)
            else:
                items = self.client.list_folder(path)

            if not show_all:
                items = [
                    item for item in items if not item["name"].startswith(".")
                ]

            # Apply sorting
            if sort_by_size:
                items = sorted(
                    items, key=lambda x: x.get("size", 0), reverse=True
                )
            elif sort_by_time:
                # Use modified time for sorting, handle both string and datetime
                def get_modified_time(item):
                    modified = item.get("modified", "")
                    if hasattr(modified, "timestamp"):
                        return modified.timestamp()
                    elif isinstance(modified, str):
                        return modified
                    else:
                        return ""

                items = sorted(items, key=get_modified_time, reverse=True)
            else:
                # Default sort by name
                items = sorted(items, key=lambda x: x["name"])

            # Apply reverse only after all other sorting
            if reverse:
                items = items[::-1]

            if long_format:
                self._print_long_format(items)
            else:
                self._print_simple_format(items)

        except Exception as e:
            click.echo(f"ls: {e}", err=True)
            raise

    def _list_folder_recursive(self, path: str) -> List[dict]:
        """List folder contents recursively."""
        all_items = []

        def _collect_items(current_path: str) -> None:
            try:
                items = self.client.list_folder(current_path)
                for item in items:
                    if item["type"] == "file":
                        item = item.copy()
                        item["name"] = item["path"]

                    if not item["name"].startswith("/"):
                        item["name"] = f"/{item['name']}"

                    all_items.append(item)

                    # If it's a folder, recurse into it
                    if item["type"] == "folder":
                        folder_path = item["path"]
                        _collect_items(folder_path)

            except Exception:
                # Skip folders we can't access
                pass

        _collect_items(path)
        return all_items

    def cp_with_options(
        self,
        sources: tuple,
        recursive: bool = False,
        treat_as_file: bool = False,
        target_directory: str = None,
    ) -> None:
        """Copy contents with structured options (like ls_with_options)."""
        if not sources:
            click.echo("cp: missing file operand", err=True)
            raise click.ClickException("cp requires source files")

        # Convert sources tuple to list for easier manipulation
        source_list = list(sources)
        destination = None

        # Handle different cp command forms
        if target_directory is not None:
            # Form: cp -t DIRECTORY SOURCE ...
            destination = target_directory
            if not source_list:
                click.echo("cp: missing file operand", err=True)
                raise click.ClickException("cp: -t requires source files")
        elif treat_as_file:
            # Form: cp -T SOURCE DEST
            if len(source_list) != 2:
                click.echo("cp: -T requires exactly two arguments", err=True)
                raise click.ClickException(
                    "cp: -T requires exactly one source and one destination"
                )
            destination = source_list.pop()
        else:
            # Form: cp SOURCE ... DIRECTORY (traditional form)
            if len(source_list) < 2:
                click.echo("cp: missing file operand", err=True)
                raise click.ClickException("cp requires source and destination")
            destination = source_list.pop()

        # Perform the copy operations
        for source in source_list:
            try:
                self._copy_file_or_folder(
                    source, destination, recursive, treat_as_file
                )
            except Exception as e:
                click.echo(f"cp: {e}", err=True)
                raise

    def cp(self, args: Tuple[str, ...]) -> None:
        """Copy contents from one location to another. Mimic Linux cp."""
        if len(args) < 2:
            click.echo("cp: missing file operand", err=True)
            raise click.ClickException("cp requires source and destination")

        recursive = False
        treat_target_as_file = False  # -T flag
        target_directory = None  # -t flag
        sources = []
        destination = None

        # Parse arguments
        i = 0
        while i < len(args):
            arg = args[i]
            if arg.startswith("-"):
                # Handle flags
                if arg == "-T":
                    treat_target_as_file = True
                elif arg == "-t":
                    # Next argument is the target directory
                    i += 1
                    if i >= len(args):
                        click.echo(
                            "cp: option requires an argument -- 't'", err=True
                        )
                        raise click.ClickException(
                            "cp: -t requires directory argument"
                        )
                    target_directory = args[i]
                elif "r" in arg or "R" in arg:
                    recursive = True
                elif "T" in arg:
                    treat_target_as_file = True
                elif "t" in arg:
                    # Combined flag like -rt, need to get directory next
                    i += 1
                    if i >= len(args):
                        click.echo(
                            "cp: option requires an argument -- 't'", err=True
                        )
                        raise click.ClickException(
                            "cp: -t requires directory argument"
                        )
                    target_directory = args[i]
            else:
                sources.append(arg)
            i += 1

        # Handle different cp command forms
        if target_directory is not None:
            # Form: cp -t DIRECTORY SOURCE ...
            destination = target_directory
            if not sources:
                click.echo("cp: missing file operand", err=True)
                raise click.ClickException("cp: -t requires source files")
        elif treat_target_as_file:
            # Form: cp -T SOURCE DEST
            if len(sources) != 2:
                click.echo("cp: -T requires exactly two arguments", err=True)
                raise click.ClickException(
                    "cp: -T requires exactly one source and one destination"
                )
            destination = sources.pop()
        else:
            # Form: cp SOURCE ... DIRECTORY (traditional form)
            if len(sources) < 2:
                click.echo("cp: missing file operand", err=True)
                raise click.ClickException("cp requires source and destination")
            destination = sources.pop()

        # Perform the copy operations
        for source in sources:
            try:
                self._copy_file_or_folder(
                    source, destination, recursive, treat_target_as_file
                )
            except Exception as e:
                click.echo(f"cp: {e}", err=True)
                raise

    def mv(self, args: Tuple[str, ...]) -> None:
        """Move contents from one location to another. Mimic Linux mv."""
        if len(args) != 2:
            click.echo("mv: requires exactly two arguments", err=True)
            raise click.ClickException("mv requires source and destination")

        source, destination = args

        try:
            # Check if source is local or remote
            if os.path.exists(source):
                # Local to remote
                remote_dest = (
                    destination
                    if destination.startswith("/")
                    else "/" + destination
                )
                self.client.upload_file(source, remote_dest)
                os.remove(source)  # Remove local file after upload
            else:
                # Remote to remote
                remote_source = (
                    source if source.startswith("/") else "/" + source
                )
                remote_dest = (
                    destination
                    if destination.startswith("/")
                    else "/" + destination
                )
                self.client.move_file(remote_source, remote_dest)

        except Exception as e:
            click.echo(f"mv: {e}", err=True)
            raise

    def rm(self, args: Tuple[str, ...]) -> None:
        """Remove remote files and folders. Mimic Linux rm command."""
        if not args:
            click.echo("rm: missing operand", err=True)
            raise click.ClickException("rm requires at least one file")

        force = False

        files_to_remove = []

        for arg in args:
            if arg.startswith("-"):
                if "f" in arg:
                    force = True
            else:
                files_to_remove.append(arg)

        for file_path in files_to_remove:
            try:
                remote_path = (
                    file_path if file_path.startswith("/") else "/" + file_path
                )
                self.client.delete_file(remote_path)
                if self.verbose:
                    click.echo(f"removed '{remote_path}'")

            except Exception as e:
                if not force:
                    click.echo(f"rm: {e}", err=True)
                    raise
                elif self.verbose:
                    click.echo(f"rm: {e}", err=True)

    def _print_simple_format(self, items: List[dict]) -> None:
        """Print items in simple format."""
        for item in items:  # Don't sort here, items are already sorted
            if item["type"] == "folder":
                click.echo(f"{item['name']}/")
            else:
                click.echo(item["name"])

    def _print_long_format(self, items: List[dict]) -> None:
        """Print items in long format."""
        for item in items:  # Don't sort here, items are already sorted
            if item["type"] == "folder":
                click.echo(f"drwxr-xr-x   - -       -  {item['name']}/")
            else:
                size = item.get("size", 0)
                modified = item.get("modified", "unknown")
                if hasattr(modified, "strftime"):
                    modified = modified.strftime("%Y-%m-%d %H:%M")
                click.echo(
                    f"-rw-r--r--   - -   {size:>8}  {modified}  {item['name']}"
                )

    def _copy_file_or_folder(
        self,
        source: str,
        destination: str,
        recursive: bool = False,
        treat_target_as_file: bool = False,
    ) -> None:
        """Copy a file or folder."""
        # Normalize paths based on conventions
        source_is_remote = _is_remote_path(source)
        dest_is_remote = _is_remote_path(destination)

        if source_is_remote:
            source_path = _normalize_remote_path(source)
        else:
            source_path = _normalize_local_path(source)

        if dest_is_remote:
            dest_path = _normalize_remote_path(destination)
        else:
            dest_path = _normalize_local_path(destination)

        # Determine operation type
        if source_is_remote and dest_is_remote:
            # Remote to remote
            self._copy_remote_to_remote(
                source_path, dest_path, recursive, treat_target_as_file
            )
        elif source_is_remote and not dest_is_remote:
            # Remote to local
            self._copy_remote_to_local(
                source_path, dest_path, recursive, treat_target_as_file
            )
        elif not source_is_remote and dest_is_remote:
            # Local to remote
            self._copy_local_to_remote(
                source_path, dest_path, recursive, treat_target_as_file
            )
        else:
            # Both local - this tool is not for local to local copying
            raise ValueError(
                "drobo cp is not used for copying local files to local "
                "destinations"
            )

    def _copy_local_to_remote(
        self,
        source: str,
        destination: str,
        recursive: bool,
        treat_target_as_file: bool,
    ) -> None:
        """Copy from local to remote."""
        if os.path.isfile(source):
            if treat_target_as_file or not self._is_remote_directory(
                destination
            ):
                # Copy to specific file path
                self.client.upload_file(source, destination)
            else:
                # Copy into directory
                filename = os.path.basename(source)
                dest_file = f"{destination.rstrip('/')}/{filename}"
                self.client.upload_file(source, dest_file)
        elif os.path.isdir(source):
            if not recursive:
                raise ValueError(
                    f"'{source}' is a directory (use -r for recursive copy)"
                )
            self._upload_directory_recursive(source, destination)
        else:
            raise ValueError(f"'{source}': No such file or directory")

    def _copy_remote_to_local(
        self,
        source: str,
        destination: str,
        recursive: bool,
        treat_target_as_file: bool,
    ) -> None:
        """Copy from remote to local."""
        try:
            # Check if source is a file or directory by attempting to get
            # its metadata
            metadata = self.client.get_metadata(source)
            if metadata.get("type") == "file":
                if treat_target_as_file:
                    self.client.download_file(source, destination)
                else:
                    # If destination is a directory, copy into it
                    if os.path.isdir(destination):
                        filename = os.path.basename(source)
                        dest_file = os.path.join(destination, filename)
                        self.client.download_file(source, dest_file)
                    else:
                        self.client.download_file(source, destination)
            elif metadata.get("type") == "folder":
                if not recursive:
                    raise ValueError(
                        f"'{source}' is a directory (use -r for recursive copy)"
                    )
                self._download_directory_recursive(source, destination)
            else:
                raise ValueError(f"'{source}': Unknown file type")
        except Exception:
            raise ValueError(f"'{source}': No such file or directory")

    def _copy_remote_to_remote(
        self,
        source: str,
        destination: str,
        recursive: bool,
        treat_target_as_file: bool,
    ) -> None:
        """Copy from remote to remote."""
        try:
            # Check if source is a file or directory
            metadata = self.client.get_metadata(source)
            if metadata.get("type") == "file":
                if treat_target_as_file or not self._is_remote_directory(
                    destination
                ):
                    # Copy to specific file path
                    self.client.copy_file(source, destination)
                else:
                    # Copy into directory
                    filename = os.path.basename(source)
                    dest_file = f"{destination.rstrip('/')}/{filename}"
                    self.client.copy_file(source, dest_file)
            elif metadata.get("type") == "folder":
                if not recursive:
                    raise ValueError(
                        f"'{source}' is a directory (use -r for recursive copy)"
                    )
                self._copy_directory_recursive_remote(source, destination)
            else:
                raise ValueError(f"'{source}': Unknown file type")
        except Exception:
            raise ValueError(f"'{source}': No such file or directory")

    def _is_remote_directory(self, path: str) -> bool:
        """Check if a remote path is a directory."""
        try:
            metadata = self.client.get_metadata(path)
            return metadata.get("type") == "folder"
        except Exception:
            return False

    def _download_directory_recursive(
        self, remote_dir: str, local_base: str
    ) -> None:
        """Download a directory recursively."""
        os.makedirs(local_base, exist_ok=True)

        items = self.client.list_folder(remote_dir)
        for item in items:
            if item["type"] == "file":
                local_path = os.path.join(local_base, item["name"])
                remote_path = item["path"]
                self.client.download_file(remote_path, local_path)
            elif item["type"] == "folder":
                local_subdir = os.path.join(local_base, item["name"])
                remote_subdir = item["path"]
                self._download_directory_recursive(remote_subdir, local_subdir)

    def _copy_directory_recursive_remote(
        self, remote_source: str, remote_dest: str
    ) -> None:
        """Copy a directory recursively within remote storage."""
        items = self.client.list_folder(remote_source)
        for item in items:
            if item["type"] == "file":
                source_file = item["path"]
                dest_file = f"{remote_dest.rstrip('/')}/{item['name']}"
                self.client.copy_file(source_file, dest_file)
            elif item["type"] == "folder":
                source_subdir = item["path"]
                dest_subdir = f"{remote_dest.rstrip('/')}/{item['name']}"
                self._copy_directory_recursive_remote(
                    source_subdir, dest_subdir
                )

    def _upload_directory_recursive(
        self, local_dir: str, remote_base: str
    ) -> None:
        """Upload a directory recursively."""
        local_path = Path(local_dir)
        remote_base = (
            remote_base if remote_base.startswith("/") else "/" + remote_base
        )

        for item in local_path.rglob("*"):
            if item.is_file():
                relative_path = item.relative_to(local_path)
                remote_path = f"{remote_base}/{relative_path}".replace(
                    "\\", "/"
                )
                self.client.upload_file(str(item), remote_path)


def setup_commands(
    app_config: AppConfig, verbose: bool = False
) -> CommandHandler:
    """Setup and return a command handler."""
    return CommandHandler(app_config, verbose)
