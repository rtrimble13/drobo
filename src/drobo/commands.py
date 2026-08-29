"""
Command handlers for drobo CLI commands.
"""

import fnmatch
import glob
import logging
import os
import posixpath
import re
from datetime import datetime
from typing import List

import click

from drobo.config import AppConfig, ConfigManager
from drobo.dropbox_client import DropboxClient

logger = logging.getLogger(__name__)


def _is_remote_path(path: str) -> bool:
    """Check if path is a remote path (starts with //)."""
    return path.startswith("//")


def _normalize_remote_path(path: str) -> str:
    """
    Convert remote path from // prefix to Dropbox API format.
    Dropbox API paths start with / and do not have // prefix.

    Remote paths are POSIX-shaped whatever the host OS is, so this uses
    posixpath rather than os.path -- on Windows the latter would hand back
    backslash separators and corrupt the path. posixpath.normpath is also
    independent of the working directory, which os.path.abspath is not.
    """
    if not path or path == "//":
        return "//"  # root path

    # format with // prefix
    normalized_path = posixpath.normpath("//" + re.sub(r"^/+", "", path))
    return normalized_path


def _normalize_local_path(path: str) -> str:
    """Expand and normalize local paths (~, ./, ../, etc)."""
    if not path:
        # Empty path is current directory
        return os.path.abspath(os.getcwd())
    else:
        return os.path.abspath(path)


def _has_wildcards(path: str) -> bool:
    """Check if the path contains wildcard characters."""
    return bool(re.search(r"[\*\?\[\]]", path))


def _modified_epoch(item: dict) -> float:
    """
    Sort key for 'ls -t'.

    Normalizes an item's "modified" value to a single numeric epoch so that
    entries of differing shapes remain mutually comparable.  Folders carry no
    "modified" key at all (see DropboxClient.list_folder), and files carry a
    datetime; returning a mix of types makes sorted() raise TypeError.
    Entries without a usable timestamp sort oldest.
    """
    modified = item.get("modified")

    if hasattr(modified, "timestamp"):
        return modified.timestamp()

    if isinstance(modified, str) and modified:
        try:
            return datetime.fromisoformat(modified).timestamp()
        except ValueError:
            return 0.0

    return 0.0


class CommandHandler:
    """Handles all drobo commands."""

    def __init__(
        self,
        app_config: AppConfig,
        config_manager: ConfigManager,
        verbose: bool = False,
    ) -> None:
        self.app_config = app_config
        self.verbose = verbose
        # The manager is injected rather than rebuilt: constructing a second
        # one here re-read the config file and left token writes updating a
        # different AppConfig object than the client was using.
        self.config_manager = config_manager
        self.client = DropboxClient(app_config, config_manager)
        # Remote directory lookups are network round-trips and the recursive
        # helpers repeat them heavily -- _upload_directory_recursive asks
        # about every directory it has just created.  Cache within the run.
        self._remote_dir_cache = {}

    def _filter_remote_paths(self, items: List[dict], mask: str) -> List[dict]:
        """Filter items by mask using fnmatch."""
        if not mask:
            return items
        return [item for item in items if fnmatch.fnmatch(item["name"], mask)]

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
        # First check to make sure it is not a local path
        if not _is_remote_path(path):
            click.echo(
                "ls: local paths are not supported.  "
                "Use standard 'ls' for local paths."
                "\nUse drobo 'ls' for remote paths only (starting with //)",
                err=True,
            )
            raise click.ClickException("ls requires a remote path")
        # Store original path for display purposes
        mask = None
        path = _normalize_remote_path(path)

        if path:
            if path == "//":
                path = ""  # keep empty for root with ls
            else:
                path = path[1:]  # remove leading /

        # check for wildcards in the last path component
        if _has_wildcards(path):
            path, mask = posixpath.split(path)

        try:
            # Fetch items from remote
            items = self.client.list_folder(path, recursive=recursive)

            if mask:
                items = self._filter_remote_paths(items, mask)

            if recursive:
                tree = self._build_recursive_tree(items)
                self._print_recursive_format(tree)

            else:

                # Apply sorting.  GNU ls lets the last of -S/-t win; click
                # cannot tell us the order, so -t takes precedence as the
                # more specific request.
                if sort_by_size and not sort_by_time:
                    items = sorted(
                        items, key=lambda x: x.get("size", 0), reverse=True
                    )
                elif sort_by_time:
                    items = sorted(items, key=_modified_epoch, reverse=True)
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
        """
        Build a tree structure for recursive listing.

        Folders get an entry of their own as well as being grouped under
        their parent, so a directory containing no files is still listed
        rather than vanishing from the output.
        """
        tree = {}
        for item in items:
            dir_path = item["dir"] if item["dir"] else "/"
            tree.setdefault(dir_path, [])

            if item["type"] == "file":
                tree[dir_path].append(item)
            else:
                # Ensure the folder itself appears, even when empty.
                tree.setdefault(item["path"], [])
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

    def mv_with_options(
        self,
        sources: tuple,
        force: bool = False,
        update: bool = False,
        target_directory: str = None,
    ) -> None:
        """Move contents with structured options (like cp_with_options)."""
        if not sources:
            click.echo("mv: missing file operand", err=True)
            raise click.ClickException("mv requires source files")

        # Convert sources tuple to list for easier manipulation
        source_list = list(sources)
        destination = None

        # Handle different mv command forms
        if target_directory is not None:
            # Form: mv -t DIRECTORY SOURCE ...
            destination = target_directory
            if not source_list:
                click.echo("mv: missing file operand", err=True)
                raise click.ClickException("mv: -t requires source files")
        else:
            # Form: mv SOURCE ... DIRECTORY (traditional form)
            if len(source_list) < 2:
                click.echo("mv: missing file operand", err=True)
                raise click.ClickException("mv requires source and destination")
            destination = source_list.pop()

        # Expand wildcards in sources
        expanded_sources = self._expand_source_wildcards(source_list)

        if not expanded_sources:
            click.echo("mv: no files matched", err=True)
            raise click.ClickException("mv: no files matched")

        # Validate all sources are either remote or local
        self._validate_source_consistency(expanded_sources, "mv")

        # Check if we need to validate destination directory existence
        # (when moving multiple files, destination must be a directory)
        if len(expanded_sources) > 1:
            self._validate_destination_for_multiple_files(
                expanded_sources, destination, False, "mv"
            )

        # Perform the move operations
        for source in expanded_sources:
            try:
                self._move_file(source, destination, force, update)
            except Exception as e:
                click.echo(f"mv: {e}", err=True)
                raise

    def _move_file(
        self, source: str, destination: str, force: bool, update: bool
    ) -> None:
        """Move a single file with force and update options."""
        # Normalize paths based on conventions
        source_is_remote = _is_remote_path(source)
        dest_is_remote = _is_remote_path(destination)

        if source_is_remote:
            source_path = _normalize_remote_path(source)
            if source_path:
                source_path = source_path[1:]  # remove leading /
        else:
            source_path = _normalize_local_path(source)

        if dest_is_remote:
            dest_path = _normalize_remote_path(destination)
            if dest_path:
                dest_path = dest_path[1:]  # remove leading /
        else:
            dest_path = _normalize_local_path(destination)

        # If destination is a directory, move file into it.  The basename
        # comes from whichever flavour of path the source is.
        filename = (
            posixpath.basename(source_path)
            if source_is_remote
            else os.path.basename(source_path)
        )

        if dest_is_remote:
            if self._is_remote_directory(dest_path):
                dest_path = posixpath.join(dest_path, filename)
        else:
            if os.path.isdir(dest_path):
                dest_path = os.path.join(dest_path, filename)

        # Check if destination exists and handle force/update flags
        dest_exists = False
        dest_mtime = None

        if source_is_remote and dest_is_remote:
            try:
                metadata = self.client.get_metadata(dest_path)
                dest_exists = True
                dest_mtime = metadata.get("modified")
            except Exception:
                dest_exists = False
        elif not dest_is_remote:
            if os.path.exists(dest_path):
                dest_exists = True
                dest_mtime = os.path.getmtime(dest_path)
        elif dest_is_remote:
            try:
                metadata = self.client.get_metadata(dest_path)
                dest_exists = True
                dest_mtime = metadata.get("modified")
            except Exception:
                dest_exists = False

        # Handle destination exists scenario
        if dest_exists:
            if not force and not update:
                raise ValueError(
                    f"cannot move '{source}' to '{destination}': "
                    f"destination file exists"
                )
            elif update:
                # Get source modification time
                source_mtime = None
                if source_is_remote:
                    try:
                        metadata = self.client.get_metadata(source_path)
                        source_mtime = metadata.get("modified")
                    except Exception:
                        pass
                else:
                    if os.path.exists(source_path):
                        source_mtime = os.path.getmtime(source_path)

                # Compare modification times
                if source_mtime and dest_mtime:
                    # Handle datetime objects
                    if hasattr(source_mtime, "timestamp"):
                        source_mtime = source_mtime.timestamp()
                    if hasattr(dest_mtime, "timestamp"):
                        dest_mtime = dest_mtime.timestamp()

                    # Skip if source is not newer
                    if source_mtime <= dest_mtime:
                        return

        # Perform the actual move operation
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

    def rm_with_options(
        self, sources: tuple, force: bool = False, recursive: bool = False
    ) -> None:
        """Remove remote files with structured options."""
        if not sources:
            click.echo("rm: missing operand", err=True)
            raise click.ClickException("rm requires at least one file")

        # Convert sources tuple to list for easier manipulation
        source_list = list(sources)

        # Expand wildcards in sources
        expanded_sources = self._expand_source_wildcards(source_list)

        if not expanded_sources:
            if not force:
                click.echo("rm: no files matched", err=True)
                raise click.ClickException("rm: no files matched")
            return

        # Validate all sources are remote paths only
        for source in expanded_sources:
            if not _is_remote_path(source):
                click.echo(
                    f"rm: cannot remove '{source}': Only remote files "
                    f"(starting with //) can be removed",
                    err=True,
                )
                raise click.ClickException("rm requires remote paths")

        # Perform the remove operations
        for source in expanded_sources:
            try:
                self._remove_file_or_folder(source, recursive)
            except Exception as e:
                if not force:
                    click.echo(f"rm: {e}", err=True)
                    raise
                elif self.verbose:
                    click.echo(f"rm: {e}", err=True)

    def _remove_file_or_folder(
        self, source: str, recursive: bool = False
    ) -> None:
        """Remove a remote file or folder."""
        # Normalize remote path
        source_path = _normalize_remote_path(source)
        if source_path:
            source_path = source_path[1:]  # remove leading /

        try:
            # Check if source is a file or directory
            metadata = self.client.get_metadata(source_path)
            if metadata.get("type") == "folder":
                if not recursive:
                    raise ValueError(
                        f"cannot remove '{source}': Is a directory "
                        f"(use -r for recursive removal)"
                    )
                # Delete directory recursively
                self.client.delete_file(source_path)
                if self.verbose:
                    click.echo(f"removed directory '{source}'")
            else:
                # Delete file
                self.client.delete_file(source_path)
                if self.verbose:
                    click.echo(f"removed '{source}'")
        except Exception as e:
            # Re-raise with more informative message if file doesn't exist
            if "not_found" in str(e).lower():
                raise ValueError(
                    f"cannot remove '{source}': No such file or directory"
                )
            raise

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
            dir_name = posixpath.basename(dir_path) if dir_path != "/" else "/"
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

        expanded = []
        for source in sources:
            if _is_remote_path(source):
                # Handle remote wildcards
                path = _normalize_remote_path(source)
                if _has_wildcards(path):
                    # List files in the directory and filter by mask
                    try:
                        dir_name, mask = posixpath.split(path[1:])
                        items = self._filter_remote_paths(
                            self.client.list_folder(dir_name), mask
                        )
                        for item in items:
                            # Add the full path with // prefix
                            expanded.append(
                                _normalize_remote_path(item["path"])
                            )
                    except Exception as e:
                        raise ValueError(
                            f"Cannot expand wildcard '{source}': {e}"
                        )
                else:
                    # No wildcard, add as-is
                    expanded.append(source)
            else:
                # expand local sources
                if _has_wildcards(source):
                    # A glob that matches nothing is not an error; it simply
                    # contributes no sources, as the shell would do.
                    expanded.extend(sorted(glob.glob(source)))
                else:
                    # A literal path that is absent is an error worth
                    # naming, rather than being silently dropped and
                    # reported later as "no files matched".
                    if not os.path.exists(_normalize_local_path(source)):
                        raise ValueError(
                            f"cannot stat '{source}': "
                            "No such file or directory"
                        )
                    expanded.append(source)

        return expanded

    def _validate_source_consistency(
        self, sources: list, command: str = "cp"
    ) -> None:
        """Validate that all sources are either remote or local."""
        if not sources:
            return

        first_is_remote = _is_remote_path(sources[0])
        for source in sources[1:]:
            if _is_remote_path(source) != first_is_remote:
                raise ValueError(
                    f"{command}: cannot mix remote and local source files"
                )

    def _validate_destination_for_multiple_files(
        self,
        sources: list,
        destination: str,
        recursive: bool,
        command: str = "cp",
    ) -> None:
        """Validate destination when copying multiple files."""
        dest_is_remote = _is_remote_path(destination)

        if dest_is_remote:
            # Check if remote destination is a directory
            dest_path = _normalize_remote_path(destination)
            is_dir = self._is_remote_directory(dest_path[1:])
        else:
            # Check if local destination is a directory
            dest_path = _normalize_local_path(destination)
            is_dir = os.path.isdir(dest_path)

        if not is_dir:
            raise ValueError(
                f"{command}: target '{destination}' is not a directory"
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
            if source_path:
                source_path = source_path[1:]  # remove leading /
        else:
            source_path = _normalize_local_path(source)

        if dest_is_remote:
            dest_path = _normalize_remote_path(destination)
            if dest_path:
                dest_path = dest_path[1:]  # remove leading /
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

    def _require_metadata(self, source: str) -> dict:
        """
        Fetch metadata for a remote source, treating a lookup failure as
        "no such file".  Any other failure is left alone so it reaches the
        user as itself rather than as a bogus missing-file error.
        """
        try:
            return self.client.get_metadata(source)
        except Exception as e:
            raise ValueError(f"'{source}': No such file or directory") from e

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
                # Copy into directory (destination is remote)
                filename = os.path.basename(source)
                dest_file = posixpath.join(destination, filename)
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
        # Only a failed metadata lookup means "source not found".  Keep the
        # try narrow: wrapping the transfer below would relabel auth, rate
        # limit and network failures as a missing file.
        metadata = self._require_metadata(source)

        if metadata.get("type") == "file":
            if treat_target_as_file:
                self.client.download_file(source, destination)
            else:
                # If destination is a directory, copy into it
                if os.path.isdir(destination):
                    filename = posixpath.basename(source)
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
            source_dir_name = posixpath.basename(source.rstrip("/"))
            if os.path.exists(destination):
                # Destination exists, create subdirectory with source's name
                actual_dest = os.path.join(destination, source_dir_name)
            else:
                # Destination doesn't exist, create it and copy directly
                actual_dest = destination

            self._download_directory_contents(source, actual_dest)
        else:
            raise ValueError(f"'{source}': Unknown file type")

    def _copy_remote_to_remote(
        self,
        source: str,
        destination: str,
        recursive: bool,
        treat_target_as_file: bool,
    ) -> None:
        """Copy from remote to remote."""
        metadata = self._require_metadata(source)

        if metadata.get("type") == "file":
            if treat_target_as_file or not self._is_remote_directory(
                destination
            ):
                # Copy to specific file path
                self.client.copy_file(source, destination)
            else:
                # Copy into directory (both sides remote)
                filename = posixpath.basename(source)
                dest_file = posixpath.join(destination, filename)
                self.client.copy_file(source, dest_file)
        elif metadata.get("type") == "folder":
            if not recursive:
                raise ValueError(
                    f"'{source}' is a directory (use -r for recursive copy)"
                )
            self._copy_directory_recursive_remote(source, destination)
        else:
            raise ValueError(f"'{source}': Unknown file type")

    def _is_remote_directory(self, path: str) -> bool:
        """Check if a remote path is a directory."""
        if path in ["/", "//"]:
            return True  # root is a directory

        if path in self._remote_dir_cache:
            return self._remote_dir_cache[path]

        try:
            metadata = self.client.get_metadata(path)
            is_dir = metadata.get("type") == "folder"
        except Exception:
            is_dir = False

        self._remote_dir_cache[path] = is_dir
        return is_dir

    def _note_remote_directory(self, path: str) -> None:
        """Record a directory drobo has just created."""
        self._remote_dir_cache[path] = True

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
        remote_base = posixpath.join(remote_base, target_dir_name)

        if not self._is_remote_directory(remote_base):
            self.client.create_folder(remote_base)
            self._note_remote_directory(remote_base)

        for root, dirs, files in os.walk(local_dir):
            # Create corresponding remote directory
            for dir_name in dirs:
                rel_dir = os.path.relpath(
                    os.path.join(root, dir_name), local_dir
                )
                # rel_dir comes from the local filesystem, so normalise
                # its separators before using it as a remote path.
                remote_subdir = posixpath.join(
                    remote_base, rel_dir.replace(os.sep, "/")
                )
                if not self._is_remote_directory(remote_subdir):
                    self.client.create_folder(remote_subdir)
                    self._note_remote_directory(remote_subdir)

            for file in files:
                local_file_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_file_path, local_dir)
                remote_path = posixpath.join(
                    remote_base, relative_path.replace(os.sep, "/")
                )
                self.client.upload_file(local_file_path, remote_path)


def setup_commands(
    app_config: AppConfig,
    config_manager: ConfigManager,
    verbose: bool = False,
) -> CommandHandler:
    """Setup and return a command handler."""
    return CommandHandler(app_config, config_manager, verbose)
