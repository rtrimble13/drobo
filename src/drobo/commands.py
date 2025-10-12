"""
Command handlers for drobo CLI commands.
"""

import logging
import os
import re
from pathlib import Path
from typing import List, Tuple

import click

from drobo.config import AppConfig, ConfigManager
from drobo.dropbox_client import DropboxClient

logger = logging.getLogger(__name__)


def _is_remote_path(path: str) -> bool:
    """Check if path is a remote path (starts with //)."""
    return path.startswith("//")


def _normalize_remote_path(path: str) -> Tuple[str, str]:
    """
    Convert remote path from // prefix to Dropbox API format.
    Dropbox API paths start with / and do not have // prefix.
    returns: (normalized_path, wildcard_pattern or None)
    """
    if not path or path in ["//", "/"]:
        return ("", None)  # Empty path means root in Dropbox API

    base, mask = "", None
    if _has_wildcards(path):
        # Split into base and wildcard part
        base, mask = os.path.split(path)
    else:
        base = path

    # standardize to single leading /
    base = "/" + re.sub(r"^/+", "", base)

#    if base:
#        base = "/" + base  # Ensure leading / for non-root path.
    return (base, _get_wildcard_regex(mask))


def _normalize_local_path(path: str) -> Tuple[str, str]:
    """Expand and normalize local paths (~, ./, ../, etc)."""
    if not path:
        # Empty path is current directory
        return (os.path.abspath(os.getcwd()), None)

    base, mask = "", None
    if _has_wildcards(path):
        base, mask = os.path.split(path)
    else:
        base = path

    if base.startswith("~/"):
        base = os.path.expanduser(base)
    else:
        base = os.path.abspath(base)

    return (base, _get_wildcard_regex(mask))


def _has_wildcards(path: str) -> bool:
    """Check if the path contains wildcard characters."""
    return bool(re.search(r"[\*\?\[\]]", path))


def _get_wildcard_regex(pattern: str) -> str:
    """Convert a wildcard pattern to a regex pattern."""
    if not pattern:
        return None
    escaped = re.escape(pattern)
    regex_pattern = (
        escaped.replace(r"\*", ".*")
        .replace(r"\?", ".")
        .replace(r"\[", "[")
        .replace(r"\]", "]")
        .replace(r"\-", "-")
    )
    return f"^{regex_pattern}$"

class CommandHandler:
    """Handles all drobo commands."""

    def __init__(self, app_config: AppConfig, verbose: bool = False) -> None:
        self.app_config = app_config
        self.verbose = verbose
        self.config_manager = ConfigManager()
        self.client = DropboxClient(app_config, self.config_manager)

    def _filter_by_mask(
        self, items: List[dict], mask: str = None, show_all: bool = False
    ) -> List[dict]:
        """
        Filter items by wildcard mask.
        items: list of item dicts with 'name' key
        mask: wildcard pattern (e.g. *.txt)
        show_all: if True, include hidden files (starting with .)
        returns: filtered list of items
        """
        if mask:
            regex = re.compile(mask)
            filtered = [item for item in items if regex.match(item["name"])]
        if not show_all:
            filtered = [
                item for item in items if not item["name"].startswith(".")
            ]
        return filtered

    def ls_with_options(
        self,
        path: str = "//",
        long_format: bool = False,
        reverse: bool = False,
        recursive: bool = False,
        sort_by_size: bool = False,
        sort_by_time: bool = False,
    ) -> None:
        """List remote target contents with structured options."""
        # Store original path for display purposes
        mask = None
        # Handle remote path convention with // prefix
        if _is_remote_path(path):
            path, mask = _normalize_remote_path(path)
        elif not path or path in ["/", "//"]:
            # Default to remote root when no path given or just "/"
            path = ""
        else:
            # All other paths are not supported
            raise ValueError(
                f"Local paths not supported in ls command. Use // for "
                f"remote paths. Got: {path}"
            )

        try:
            # Fetch items from remote
            items = self.client.list_folder(
                path, mask=mask, recursive=recursive
            )

            if recursive:
                tree = self._build_recursive_tree(items)
                self._print_recursive_format(tree)

            else:

                # Apply sorting
                if sort_by_size:
                    items = sorted(
                        items, key=lambda x: x.get("size", 0), reverse=True
                    )
                elif sort_by_time:
                    # Use modified time for sorting,
                    # handle both string and datetime
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

    def _build_recursive_tree(self, items: List[dict]) -> dict:
        """Build a tree structure for recursive listing."""
        tree = {}
        for item in items:
            dir_path = item["dir"] if item["dir"] else "/"
            if dir_path not in tree:
                tree[dir_path] = []
            if item["type"] == "file":
                tree[dir_path].append(item)
        return tree

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

        # Expand wildcards in sources
        expanded_sources = self._expand_source_wildcards(source_list)

        if not expanded_sources:
            click.echo("cp: no files matched", err=True)
            raise click.ClickException("cp: no files matched")

        # Validate all sources are either remote or local
        self._validate_source_consistency(expanded_sources)

        # Check if we need to validate destination directory existence
        # (when copying multiple files, destination must be a directory)
        if len(expanded_sources) > 1 and not treat_as_file:
            self._validate_destination_for_multiple_files(
                expanded_sources, destination, recursive
            )

        # Perform the copy operations
        for source in expanded_sources:
            try:
                self._copy_file_or_folder(
                    source, destination, recursive, treat_as_file
                )
            except Exception as e:
                click.echo(f"cp: {e}", err=True)
                raise

    def mv_with_options(self, source: str, destination: str) -> None:
        """Move contents with structured options (like ls_with_options)."""
        if not source or not destination:
            click.echo("mv: missing operand", err=True)
            raise click.ClickException("mv requires source and destination")

        try:
            # Normalize paths based on conventions
            source_is_remote = _is_remote_path(source)
            dest_is_remote = _is_remote_path(destination)

            if source_is_remote:
                source_path, _ = _normalize_remote_path(source)
            else:
                source_path, _ = _normalize_local_path(source)

            if dest_is_remote:
                dest_path, _ = _normalize_remote_path(destination)
            else:
                dest_path, _ = _normalize_local_path(destination)

            # Handle different move operations
            if source_is_remote and dest_is_remote:
                # Remote to remote
                self.client.move_file(source_path, dest_path)
            elif not source_is_remote and dest_is_remote:
                # Local to remote (upload then delete local)
                self.client.upload_file(source_path, dest_path)
                os.remove(source_path)
            elif source_is_remote and not dest_is_remote:
                # Remote to local (download then delete remote)
                self.client.download_file(source_path, dest_path)
                self.client.delete_file(source_path)
            else:
                # Both local - not supported
                raise ValueError(
                    "drobo mv is not used for moving local files to local "
                    "destinations"
                )

        except Exception as e:
            click.echo(f"mv: {e}", err=True)
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

    def rm_with_options(
        self, files: tuple, force: bool = False, recursive: bool = False
    ) -> None:
        """Remove files with structured options (like ls_with_options)."""
        if not files:
            click.echo("rm: missing operand", err=True)
            raise click.ClickException("rm requires at least one file")

        for file_path in files:
            try:
                # Normalize path based on conventions
                if _is_remote_path(file_path):
                    remote_path, _ = _normalize_remote_path(file_path)
                else:
                    # rm only works on remote files
                    raise ValueError(
                        f"rm: cannot remove '{file_path}': Only remote files "
                        f"(starting with //) can be removed"
                    )

                self.client.delete_file(remote_path)
                if self.verbose:
                    click.echo(f"removed '{file_path}'")

            except Exception as e:
                if not force:
                    click.echo(f"rm: {e}", err=True)
                    raise
                elif self.verbose:
                    click.echo(f"rm: {e}", err=True)

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
                text = click.style(f"{item['name']}/", fg="yellow", bold=True)
                click.echo(text)
            else:
                click.echo(item["name"])

    def _print_recursive_format(self, items: dict) -> None:
        """Print items in recursive format."""
        for dir_path in sorted(items.keys()):
            dir_name = os.path.basename(dir_path) if dir_path != "/" else "/"
            space = " | " * (dir_path.count("/") - 1)
            click.echo(f"{space}{dir_name}:")
            dir_items = items[dir_path]
            if dir_items:
                space = " | " * (dir_path.count("/"))
                for item in sorted(dir_items, key=lambda x: x["name"]):
                    click.echo(f"{space}{item['name']}")

    def _print_long_format(self, items: List[dict]) -> None:
        """Print items in long format."""
        for item in items:  # Don't sort here, items are already sorted
            if item["type"] == "folder":
                text = click.style(f"{item['name']}/", fg="yellow", bold=True)
                click.echo(text)
            else:
                size = item.get("size", 0)
                modified = item.get("modified", "unknown")
                if hasattr(modified, "strftime"):
                    modified = modified.strftime("%Y-%m-%d %H:%M")
                click.echo(f"{item['name']}\t{size:>8}\t{modified}")

    def _expand_source_wildcards(self, sources: list) -> list:
        """Expand wildcards in source paths."""
        import glob

        expanded = []
        for source in sources:
            if _is_remote_path(source):
                # Handle remote wildcards
                base_path, mask = _normalize_remote_path(source)
                if mask:
                    # List files in the directory and filter by mask
                    try:
                        items = self.client.list_folder(base_path, mask=mask)
                        for item in items:
                            # Add the full path with // prefix
                            expanded.append("//" + item["path"].lstrip("/"))
                    except Exception as e:
                        raise ValueError(
                            f"Cannot expand wildcard '{source}': {e}"
                        )
                else:
                    # No wildcard, add as-is
                    expanded.append(source)
            else:
                # expand local sources
                matches = glob.glob(source)
                if matches:
                    expanded.extend(matches)
#                base_path, mask = _normalize_local_path(source)
                # Handle local wildcards
#                if mask:
#                    base_path = base_path + "/" + mask
#                    matches = glob.glob(base_path)
#                    if matches:
#                        expanded.extend(matches)
                    # If no matches, the error will be caught later
#                else:
                    # No wildcard, add as-is
#                    expanded.append(base_path)

        return expanded

    def _validate_source_consistency(self, sources: list) -> None:
        """Validate that all sources are either remote or local."""
        if not sources:
            return

        first_is_remote = _is_remote_path(sources[0])
        for source in sources[1:]:
            if _is_remote_path(source) != first_is_remote:
                raise ValueError("cp: cannot mix remote and local source files")

    def _validate_destination_for_multiple_files(
        self, sources: list, destination: str, recursive: bool
    ) -> None:
        """Validate destination when copying multiple files."""
        dest_is_remote = _is_remote_path(destination)

        if dest_is_remote:
            # Check if remote destination is a directory
            dest_path, _ = _normalize_remote_path(destination)
            if not self._is_remote_directory(dest_path.rstrip("/")):
                raise ValueError(
                    f"cp: target '{destination}' is not a directory"
                )
        else:
            # Check if local destination is a directory
            dest_path, _ = _normalize_local_path(destination)
            if not os.path.isdir(dest_path):
                raise ValueError(
                    f"cp: target '{destination}' is not a directory"
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
            source_path, _ = _normalize_remote_path(source)
        else:
            source_path, _ = _normalize_local_path(source)

        if dest_is_remote:
            dest_path, _ = _normalize_remote_path(destination)
        else:
            dest_path, _ = _normalize_local_path(destination)

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
                # Handle directory copy based on use case 2
                source_dir_name = os.path.basename(source.rstrip("/"))
                if os.path.exists(destination):
                    # Destination exists, create subdirectory with source's name
                    actual_dest = os.path.join(destination, source_dir_name)
                else:
                    # Destination doesn't exist, create it and copy directly
                    actual_dest = destination

                self._download_directory_contents(source, actual_dest)
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

    def _download_directory_contents(
        self, remote_dir: str, local_dest: str
    ) -> None:
        """Download directory contents recursively into local_dest."""
        os.makedirs(local_dest, exist_ok=True)

        items = self.client.list_folder(remote_dir)
        for item in items:
            if item["type"] == "file":
                local_path = os.path.join(local_dest, item["name"])
                remote_path = item["path"]
                self.client.download_file(remote_path, local_path)
            elif item["type"] == "folder":
                local_subdir = os.path.join(local_dest, item["name"])
                remote_subdir = item["path"]
                self._download_directory_contents(remote_subdir, local_subdir)

    def _download_directory_recursive(
        self, remote_dir: str, local_base: str
    ) -> None:
        """Download a directory recursively (legacy wrapper)."""
        self._download_directory_contents(remote_dir, local_base)

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
        remote_base = (
            remote_base if remote_base.startswith("/") else "/" + remote_base
        )
        # get the base directory name to create under remote_base
        target_dir_name = os.path.basename(os.path.normpath(local_dir))
        remote_base = os.path.join(remote_base, target_dir_name).replace("\\", "/")

        if not self._is_remote_directory(remote_base):
            self.client.create_folder(remote_base)

        for root, dirs, files in os.walk(local_dir):
            # Create corresponding remote directory
            for dir_name in dirs:
                rel_dir = os.path.relpath(os.path.join(root, dir_name), local_dir)
                remote_subdir = os.path.join(remote_base, rel_dir).replace("\\", "/")
                if not self._is_remote_directory(remote_subdir):
                    self.client.create_folder(remote_subdir)

            for file in files:
                local_file_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_file_path, local_dir)
                remote_path = os.path.join(remote_base, relative_path).replace("\\", "/")
                self.client.upload_file(local_file_path, remote_path)
        
def setup_commands(
    app_config: AppConfig, verbose: bool = False
) -> CommandHandler:
    """Setup and return a command handler."""
    return CommandHandler(app_config, verbose)
