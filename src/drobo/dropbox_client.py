"""
Dropbox API client for drobo.
"""

import logging
import os
import random
import sys
import tempfile
import time
from typing import Callable, List, Optional, Tuple

import dropbox
import requests
from dropbox.exceptions import (
    ApiError,
    AuthError,
    InternalServerError,
    RateLimitError,
)
from dropbox.files import FileMetadata, FolderMetadata
from dropbox.oauth import DropboxOAuth2FlowNoRedirect

from drobo.config import AppConfig, ConfigManager

logger = logging.getLogger(__name__)

# Retry policy for transient failures.  Bulk operations (a recursive copy of
# a directory tree) issue hundreds of sequential calls, so hitting a 429
# partway through is expected rather than exceptional.
MAX_ATTEMPTS = 5
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 32.0

# A 429 is safe to retry for any operation: the server rejected the request
# without acting on it.
RATE_LIMIT_ERRORS = (RateLimitError,)

# These may strike after the server has already acted, so they are only
# retried for operations that are safe to repeat.
TRANSIENT_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    InternalServerError,
    ConnectionError,
    TimeoutError,
)

# Scopes drobo needs to implement ls/cp/mv/rm.
OAUTH_SCOPES = [
    "files.metadata.read",
    "files.content.read",
    "files.content.write",
]


class DroboAuthError(Exception):
    """Raised when drobo cannot obtain or refresh usable credentials."""


def authorize_interactive(
    app_config: AppConfig,
) -> Tuple[str, Optional[str]]:
    """
    Run the interactive OAuth flow and return (access_token, refresh_token).

    This needs a human: the user must visit a URL and paste back an
    authorization code.  It is therefore only ever driven from the explicit
    `drobo <app> auth` command, never from an error path, and it refuses to
    run without a terminal rather than blocking forever on stdin.
    """
    if not app_config.app_key:
        raise DroboAuthError(f"App '{app_config.name}' has no app_key")
    if not app_config.app_secret:
        raise DroboAuthError(f"App '{app_config.name}' has no app_secret")

    if not sys.stdin.isatty():
        raise DroboAuthError(
            "Authorization requires an interactive terminal. Run "
            f"'drobo {app_config.name} auth' from a terminal to authorize."
        )

    flow = DropboxOAuth2FlowNoRedirect(
        app_config.app_key,
        app_config.app_secret,
        token_access_type="offline",
        scope=OAUTH_SCOPES,
        include_granted_scopes="user",
    )

    auth_url = flow.start()
    print("1. Go to: " + auth_url)
    print(
        "2. Click 'Allow', then paste the code here "
        "(You might have to log in)."
    )
    auth_code = input("Enter the code: ").strip()

    oauth_result = flow.finish(auth_code)
    return oauth_result.access_token, oauth_result.refresh_token


class DropboxClient:
    """Dropbox API client with token management."""

    def __init__(
        self, app_config: AppConfig, config_manager: ConfigManager
    ) -> None:
        self._refresh_attempted = False
        self.app_config = app_config
        self.config_manager = config_manager
        self._client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the Dropbox client."""
        if not self.app_config.has_valid_tokens():
            raise DroboAuthError(
                f"App '{self.app_config.name}' has no access_token and no "
                f"refresh_token. Run 'drobo {self.app_config.name} auth' "
                "to authorize."
            )

        self._client = dropbox.Dropbox(
            oauth2_access_token=self.app_config.access_token,
            app_key=self.app_config.app_key,
            app_secret=self.app_config.app_secret,
            oauth2_refresh_token=self.app_config.refresh_token,
        )

        logger.debug(
            f"Initialized Dropbox client for app '{self.app_config.name}'"
        )

    def _retry(self, thunk: Callable, retry_transient: bool):
        """
        Run thunk, retrying transient failures with exponential backoff.

        Honours the server's own backoff hint when it supplies one.  Errors
        that are not transient -- a missing file, a bad path, an expired
        token -- are raised immediately; retrying those only wastes time.
        """
        delay = INITIAL_BACKOFF
        last = MAX_ATTEMPTS - 1

        for attempt in range(MAX_ATTEMPTS):
            try:
                return thunk()
            except RATE_LIMIT_ERRORS as e:
                if attempt == last:
                    raise
                # Dropbox tells us how long to wait; prefer its hint.
                wait = getattr(e, "backoff", None) or delay
                reason = "rate limited by Dropbox"
            except TRANSIENT_ERRORS:
                if not retry_transient or attempt == last:
                    raise
                wait = delay
                reason = "transient network error"

            # Jitter keeps concurrent runs from retrying in lockstep.
            wait += random.uniform(0, 0.25 * wait)
            logger.warning(
                f"{reason}; retrying in {wait:.1f}s "
                f"(attempt {attempt + 2} of {MAX_ATTEMPTS})"
            )
            time.sleep(wait)
            delay = min(delay * 2, MAX_BACKOFF)

    def _read(self, fn: Callable, *args, **kwargs):
        """Call a read-only route, retrying rate limits and network errors."""
        return self._retry(lambda: fn(*args, **kwargs), retry_transient=True)

    def _write(self, fn: Callable, *args, **kwargs):
        """
        Call a mutating route, retrying rate limits only.

        A dropped connection on a write may already have been applied
        server-side, so repeating it is not safe without confirming what
        landed.
        """
        return self._retry(lambda: fn(*args, **kwargs), retry_transient=False)

    def _handle_auth_error(self, error: AuthError) -> None:
        """Handle authentication errors and attempt token refresh."""
        logger.warning(f"Authentication error: {error}")

        if (
            error.error.is_expired_access_token()
            and not self._refresh_attempted
        ):
            try:
                self.refresh_access_token()
                self.save_tokens()
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                raise DroboAuthError(
                    f"Could not refresh credentials for app "
                    f"'{self.app_config.name}': {e}"
                ) from e
        else:
            raise error

    def refresh_access_token(self) -> None:
        """
        Refresh the access token using the stored refresh token.

        The SDK performs the exchange itself given app_key, app_secret and
        the refresh token -- no user interaction is involved.  (It also does
        this automatically before each request; this method exists so an
        expired-token error can be recovered from explicitly and the new
        token persisted.)
        """
        if not self.app_config.refresh_token:
            raise DroboAuthError(
                f"App '{self.app_config.name}' has no refresh_token. Run "
                f"'drobo {self.app_config.name} auth' to authorize."
            )
        if not self.app_config.app_key:
            raise DroboAuthError("No app key available")
        if not self.app_config.app_secret:
            raise DroboAuthError("No app secret available")

        self._refresh_attempted = True

        self._client.refresh_access_token()

        # Copy the SDK's newly issued token back so it can be persisted.
        new_token = getattr(self._client, "_oauth2_access_token", None)
        if new_token:
            self.app_config.update_tokens(
                new_token, self.app_config.refresh_token
            )

        logger.info("Access token refreshed")

    def save_tokens(self) -> None:
        """Save the current access and refresh tokens."""
        try:
            self.config_manager.save_app_tokens(
                self.app_config.name,
                self.app_config.access_token,
                self.app_config.refresh_token,
            )
            logger.info("Saved refreshed tokens to config")
        except Exception as e:
            logger.error(f"Failed to save refreshed tokens: {e}")
            raise

    def list_folder(self, path: str = "", *args, **kwargs) -> List[dict]:
        """
        List contents of a folder.
        Supports pagination and returns a list of items with metadata.
        If 'recursive' is passed in kwargs, it will list all subfolders
        recursively.
        """
        try:
            result = self._read(
                self._client.files_list_folder, path, *args, **kwargs
            )
            entries = list(result.entries)
            while result.has_more:
                result = self._read(
                    self._client.files_list_folder_continue, result.cursor
                )
                entries.extend(result.entries)

            items = []

            for entry in entries:

                item = {
                    "name": os.path.basename(entry.name),
                    "dir": os.path.dirname(entry.path_display),
                    "path": entry.path_display,
                    "type": (
                        "folder"
                        if isinstance(entry, FolderMetadata)
                        else "file"
                    ),
                }

                if isinstance(entry, FileMetadata):
                    item["size"] = entry.size
                    item["modified"] = entry.client_modified

                items.append(item)

            return items

        except AuthError as e:
            self._handle_auth_error(e)
            # Retry after token refresh, preserving the caller's arguments
            # (dropping them here silently downgraded `ls -R` to a
            # single-level listing).
            return self.list_folder(path, *args, **kwargs)
        except ApiError as e:
            logger.error(f"API error listing folder '{path}': {e}")
            raise

    def download_file(self, remote_path: str, local_path: str) -> None:
        """
        Download a file from Dropbox.

        Writes to a temporary file alongside the destination and renames it
        into place only once the transfer has completed, so that a failed
        download cannot destroy an existing local file.  The temporary file
        is created in the destination directory to keep the rename atomic.
        """
        try:
            dest_dir = os.path.dirname(os.path.abspath(local_path)) or "."
            fd, tmp_path = tempfile.mkstemp(
                dir=dest_dir, prefix=".drobo-", suffix=".part"
            )
            try:
                with os.fdopen(fd, "wb") as f:
                    metadata, response = self._read(
                        self._client.files_download, remote_path
                    )
                    f.write(response.content)

                # mkstemp creates 0600; downloaded files should follow the
                # user's umask the way a normal write would.
                umask = os.umask(0)
                os.umask(umask)
                os.chmod(tmp_path, 0o666 & ~umask)

                os.replace(tmp_path, local_path)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            logger.info(f"Downloaded {remote_path} to {local_path}")

        except AuthError as e:
            self._handle_auth_error(e)
            # Retry after token refresh
            self.download_file(remote_path, local_path)
        except ApiError as e:
            logger.error(f"API error downloading file '{remote_path}': {e}")
            raise

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a file to Dropbox."""
        try:
            with open(local_path, "rb") as f:
                self._write(
                    self._client.files_upload,
                    f.read(),
                    remote_path,
                    mode=dropbox.files.WriteMode.overwrite,
                )

            logger.info(f"Uploaded {local_path} to {remote_path}")

        except AuthError as e:
            self._handle_auth_error(e)
            # Retry after token refresh
            self.upload_file(local_path, remote_path)
        except ApiError as e:
            logger.error(f"API error uploading file '{local_path}': {e}")
            raise

    def copy_file(self, from_path: str, to_path: str) -> None:
        """Copy a file or folder."""
        try:
            self._write(
                self._client.files_copy_v2,
                from_path,
                to_path,
                autorename=False,
            )
            logger.info(f"Copied {from_path} to {to_path}")

        except AuthError as e:
            self._handle_auth_error(e)
            # Retry after token refresh
            self.copy_file(from_path, to_path)
        except ApiError as e:
            if isinstance(e.error, dropbox.files.RelocationError):
                if e.error.is_from_lookup():
                    if e.error.get_from_lookup().is_not_found():
                        logger.error(f"Source '{from_path}' not found")
                    raise FileNotFoundError(f"'{from_path}' not found")
                if e.error.is_to():
                    if e.error.get_to().is_conflict():
                        self._client.files_delete_v2(to_path)
                        self._client.files_copy_v2(
                            from_path, to_path, autorename=False
                        )
                        logger.info(
                            f"Overwrote existing '{to_path}' with '{from_path}'"
                        )
                        return

            logger.error(f"API error copying '{from_path}' to '{to_path}': {e}")
            raise

    def get_metadata(self, path: str) -> dict:
        """Get metadata for a file or folder."""
        try:
            metadata = self._read(self._client.files_get_metadata, path)
            return {
                "name": metadata.name,
                "path": metadata.path_display,
                "type": (
                    "folder" if isinstance(metadata, FolderMetadata) else "file"
                ),
                "size": getattr(metadata, "size", None),
                "modified": getattr(metadata, "client_modified", None),
            }

        except AuthError as e:
            self._handle_auth_error(e)
            # Retry after token refresh
            return self.get_metadata(path)
        except ApiError as e:
            logger.warning(f"API error getting metadata for '{path}': {e}")
            raise

    def move_file(self, from_path: str, to_path: str) -> None:
        """Move/rename a file or folder."""
        try:
            self._write(self._client.files_move_v2, from_path, to_path)
            logger.info(f"Moved {from_path} to {to_path}")

        except AuthError as e:
            self._handle_auth_error(e)
            # Retry after token refresh
            self.move_file(from_path, to_path)
        except ApiError as e:
            logger.error(f"API error moving '{from_path}' to '{to_path}': {e}")
            raise

    def delete_file(self, path: str) -> None:
        """Delete a file or folder."""
        try:
            self._write(self._client.files_delete_v2, path)
            logger.info(f"Deleted {path}")

        except AuthError as e:
            self._handle_auth_error(e)
            # Retry after token refresh
            self.delete_file(path)
        except ApiError as e:
            logger.error(f"API error deleting '{path}': {e}")
            raise

    def create_folder(self, path: str) -> None:
        """Create a folder."""
        try:
            self._write(self._client.files_create_folder_v2, path)
            logger.info(f"Created folder {path}")

        except AuthError as e:
            self._handle_auth_error(e)
            # Retry after token refresh
            self.create_folder(path)
        except ApiError as e:
            logger.error(f"API error creating folder '{path}': {e}")
            raise
