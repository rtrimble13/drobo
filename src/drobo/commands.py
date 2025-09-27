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

        # Ensure path does not start with /
        if path.startswith("/") and len(path) == 1:
            path = ""

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
        # Ensure path does not start with /
        if path.startswith("/") and len(path) == 1:
            path = ""

        try:
            if directory:
                # List the directory itself, not its contents
                # This is a simplified implementation - just show the path
                click.echo(f"{path}/")
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

        def _collect_items(current_path: str, prefix: str = ""):
            try:
                items = self.client.list_folder(current_path)
                for item in items:
                    # Add prefix for nested items
                    if prefix:
                        item = item.copy()
                        item["name"] = f"{prefix}{item['name']}"
                    all_items.append(item)

                    # If it's a folder, recurse into it
                    if item["type"] == "folder":
                        folder_path = (
                            f"{current_path}/{item['name']}"
                            if current_path
                            else item["name"]
                        )
                        folder_path = folder_path.replace(
                            prefix, ""
                        )  # Remove prefix from path
                        _collect_items(folder_path, f"{prefix}{item['name']}/")
            except Exception:
                # Skip folders we can't access
                pass

        _collect_items(path)
        return all_items

    def cp(self, args: Tuple[str, ...]) -> None:
        """Copy contents from one location to another. Mimic Linux cp."""
        if len(args) < 2:
            click.echo("cp: missing file operand", err=True)
            raise click.ClickException("cp requires source and destination")

        recursive = False
        sources = []
        destination = None

        # Parse arguments
        for arg in args:
            if arg.startswith("-"):
                if "r" in arg or "R" in arg:
                    recursive = True
            else:
                if destination is None:
                    sources.append(arg)
                else:
                    sources.append(destination)
                    destination = arg

        if not destination:
            destination = sources.pop()

        for source in sources:
            try:
                self._copy_file_or_folder(source, destination, recursive)
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
        self, source: str, destination: str, recursive: bool = False
    ) -> None:
        """Copy a file or folder."""
        # Determine if source is local or remote
        if os.path.exists(source):
            # Local to remote
            if os.path.isfile(source):
                remote_dest = (
                    destination
                    if destination.startswith("/")
                    else "/" + destination
                )
                self.client.upload_file(source, remote_dest)
            elif os.path.isdir(source) and recursive:
                # Upload directory recursively
                self._upload_directory_recursive(source, destination)
            else:
                raise ValueError(
                    f"'{source}' is a directory (use -r for recursive copy)"
                )
        else:
            # Remote to local or remote to remote
            remote_source = source if source.startswith("/") else "/" + source

            if destination.startswith("/"):
                # Remote to remote
                self.client.move_file(remote_source, destination)
            else:
                # Remote to local
                destination = os.path.abspath(destination)
                self.client.download_file(remote_source, destination)

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
