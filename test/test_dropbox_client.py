"""
Tests for the Dropbox API client.
"""

import os
from datetime import datetime
from unittest.mock import Mock, patch

import dropbox
import pytest
import requests
from dropbox.exceptions import AuthError, RateLimitError
from dropbox.files import FileMetadata, FolderMetadata

from drobo.config import AppConfig
from drobo.dropbox_client import (
    MAX_ATTEMPTS,
    DroboAuthError,
    DropboxClient,
    authorize_interactive,
)


def _client() -> DropboxClient:
    """Build a DropboxClient with the SDK stubbed out.

    __init__ validates tokens and constructs a real dropbox.Dropbox, neither
    of which is wanted here, so the instance is built directly.
    """
    client = DropboxClient.__new__(DropboxClient)
    client._refresh_attempted = False
    client._client = Mock()
    return client


class TestDownloadFile:
    """Local-file handling in download_file."""

    def test_failed_download_leaves_existing_file_intact(self, tmp_path):
        """A download that raises must not destroy the destination.

        Regression: the destination was opened "wb" — and so truncated —
        before the API call was made, so any transient failure emptied a
        file the user never asked to modify.
        """
        dest = tmp_path / "precious.txt"
        dest.write_text("IRREPLACEABLE LOCAL DATA")

        client = _client()
        client._client.files_download.side_effect = ConnectionError(
            "network died mid-transfer"
        )

        with pytest.raises(ConnectionError):
            client.download_file("/remote.txt", str(dest))

        assert dest.read_text() == "IRREPLACEABLE LOCAL DATA"

    def test_failed_download_leaves_no_partial_files_behind(self, tmp_path):
        """The temporary file must be cleaned up on failure."""
        dest = tmp_path / "out.txt"

        client = _client()
        client._client.files_download.side_effect = ConnectionError("boom")

        with pytest.raises(ConnectionError):
            client.download_file("/remote.txt", str(dest))

        assert list(tmp_path.iterdir()) == []

    def test_successful_download_writes_content(self, tmp_path):
        """The happy path is unchanged."""
        dest = tmp_path / "out.txt"

        client = _client()
        response = _streaming_response(b"hello from dropbox")
        client._client.files_download.return_value = (Mock(), response)

        client.download_file("/remote.txt", str(dest))

        assert dest.read_bytes() == b"hello from dropbox"
        assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]
        # The caller owns the streamed response and must close it.
        response.close.assert_called_once()

    def test_large_download_is_streamed_in_chunks(self, tmp_path):
        """A big download must not be buffered whole in memory."""
        dest = tmp_path / "big.bin"
        payload = b"x" * (3 * 1024)

        client = _client()
        response = _streaming_response(payload, chunks=3)
        client._client.files_download.return_value = (Mock(), response)

        client.download_file("/big.bin", str(dest))

        assert dest.read_bytes() == payload
        # Consumed via iter_content, never via .content
        response.iter_content.assert_called_once()

    def test_successful_download_overwrites_existing_file(self, tmp_path):
        """Overwriting on success still works."""
        dest = tmp_path / "out.txt"
        dest.write_text("old contents")

        client = _client()
        response = _streaming_response(b"new contents")
        client._client.files_download.return_value = (Mock(), response)

        client.download_file("/remote.txt", str(dest))

        assert dest.read_bytes() == b"new contents"

    def test_downloaded_file_respects_umask(self, tmp_path):
        """Downloads follow the user's umask, not mkstemp's private 0600."""
        dest = tmp_path / "out.txt"

        client = _client()
        response = _streaming_response(b"data")
        client._client.files_download.return_value = (Mock(), response)

        old_umask = os.umask(0o022)
        try:
            client.download_file("/remote.txt", str(dest))
        finally:
            os.umask(old_umask)

        assert oct(dest.stat().st_mode & 0o777) == oct(0o644)


def _streaming_response(payload: bytes, chunks: int = 1) -> Mock:
    """Model a streamed download response.

    The SDK opens download routes with stream=True and leaves closing the
    response to the caller, so iter_content is what the client consumes.
    """
    size = max(1, -(-len(payload) // chunks))
    parts = []
    for start in range(0, len(payload), size):
        parts.append(payload[start:][:size])
    if not parts:
        parts = [b""]
    response = Mock()
    response.iter_content.return_value = iter(parts)
    return response


def _app_config(**overrides) -> AppConfig:
    data = {
        "app_key": "key",
        "app_secret": "secret",
        "access_token": "access",
        "refresh_token": "refresh",
    }
    data.update(overrides)
    return AppConfig("test_app", data)


class TestInitialization:
    """Which credential combinations are accepted."""

    def test_refresh_token_only_config_initializes(self):
        """A refresh token with no access token must be accepted.

        Regression: has_valid_tokens() checked only the access token, so
        this configuration was rejected even though the SDK is given
        everything it needs to mint one.
        """
        config = _app_config(access_token="")

        with patch("drobo.dropbox_client.dropbox.Dropbox") as sdk:
            client = DropboxClient(config, Mock())

        assert client._client is sdk.return_value
        assert sdk.call_args.kwargs["oauth2_refresh_token"] == "refresh"

    def test_no_credentials_at_all_is_rejected(self):
        """With neither token there is nothing to authenticate with."""
        config = _app_config(access_token="", refresh_token="")

        with patch("drobo.dropbox_client.dropbox.Dropbox"):
            with pytest.raises(DroboAuthError, match="no access_token"):
                DropboxClient(config, Mock())


class TestTokenRefresh:
    """Refreshing must be silent and must not fabricate SDK exceptions."""

    def test_refresh_uses_the_sdk_and_never_prompts(self, monkeypatch):
        """Refresh must not require a human.

        Regression: refresh_access_token() ran a full interactive OAuth
        flow and blocked on input(), which hangs any non-interactive run.
        """

        def _boom(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("refresh must not prompt for input")

        monkeypatch.setattr("builtins.input", _boom)

        client = _client()
        client.app_config = _app_config()
        client._client._oauth2_access_token = "freshly_minted"

        client.refresh_access_token()

        client._client.refresh_access_token.assert_called_once()
        assert client.app_config.access_token == "freshly_minted"

    def test_refresh_without_a_refresh_token_is_a_clear_error(self):
        client = _client()
        client.app_config = _app_config(refresh_token="")

        with pytest.raises(DroboAuthError, match="no refresh_token"):
            client.refresh_access_token()

    def test_failed_refresh_raises_drobo_auth_error_not_typeerror(self):
        """A failed refresh must report itself.

        Regression: this path raised AuthError("...") with one argument,
        but the SDK's AuthError takes (request_id, error), so the raise
        itself failed with TypeError and masked the real cause.
        """
        client = _client()
        client.app_config = _app_config()
        client.config_manager = Mock()

        error = Mock()
        error.error.is_expired_access_token.return_value = True
        cause = RuntimeError("refresh endpoint unreachable")
        client._client.refresh_access_token.side_effect = cause

        with pytest.raises(DroboAuthError, match="Could not refresh"):
            client._handle_auth_error(error)

    def test_failed_refresh_preserves_the_original_cause(self):
        client = _client()
        client.app_config = _app_config()
        client.config_manager = Mock()

        error = Mock()
        error.error.is_expired_access_token.return_value = True
        cause = RuntimeError("refresh endpoint unreachable")
        client._client.refresh_access_token.side_effect = cause

        with pytest.raises(DroboAuthError) as excinfo:
            client._handle_auth_error(error)

        assert excinfo.value.__cause__ is cause


class TestInteractiveAuthorization:
    """The OAuth flow is opt-in and needs a terminal."""

    def test_returns_the_tokens_from_a_completed_flow(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *a: "  pasted-code  ")

        with patch(
            "drobo.dropbox_client.DropboxOAuth2FlowNoRedirect"
        ) as flow_cls:
            flow = flow_cls.return_value
            flow.start.return_value = "https://dropbox.example/authorize"
            flow.finish.return_value = Mock(
                access_token="new_access", refresh_token="new_refresh"
            )

            tokens = authorize_interactive(_app_config())

        assert tokens == ("new_access", "new_refresh")
        # The pasted code is stripped before use.
        flow.finish.assert_called_once_with("pasted-code")
        # Offline access is required for a refresh token to be issued.
        assert flow_cls.call_args.kwargs["token_access_type"] == "offline"

    def test_requires_app_credentials(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        config = _app_config()
        config.app_secret = None

        with pytest.raises(DroboAuthError, match="app_secret"):
            authorize_interactive(config)

    def test_refuses_to_run_without_a_tty(self, monkeypatch):
        """Without a terminal it must fail fast, not block on stdin."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        with pytest.raises(DroboAuthError, match="interactive terminal"):
            authorize_interactive(_app_config())


class TestListFolder:
    """Entry mapping, pagination, and retry behaviour."""

    def _entries(self):
        file_entry = FileMetadata(
            name="report.pdf",
            path_display="/docs/report.pdf",
            size=1024,
            client_modified=datetime(2024, 5, 1),
        )
        folder_entry = FolderMetadata(
            name="images", path_display="/docs/images"
        )
        return [file_entry, folder_entry]

    def test_maps_files_and_folders_into_the_expected_shape(self):
        """Folders carry no size or modified key; files carry both.

        commands.py sorts on these keys, so the shape is a real contract.
        """
        client = _client()
        result = Mock(entries=self._entries(), has_more=False)
        client._client.files_list_folder.return_value = result

        items = client.list_folder("/docs")

        by_name = {i["name"]: i for i in items}
        assert by_name["report.pdf"]["type"] == "file"
        assert by_name["report.pdf"]["size"] == 1024
        assert by_name["report.pdf"]["modified"] == datetime(2024, 5, 1)
        assert by_name["images"]["type"] == "folder"
        assert "size" not in by_name["images"]
        assert "modified" not in by_name["images"]

    def test_follows_pagination(self):
        client = _client()
        first = Mock(entries=self._entries(), has_more=True, cursor="c1")
        second = Mock(entries=self._entries(), has_more=False)
        client._client.files_list_folder.return_value = first
        client._client.files_list_folder_continue.return_value = second

        items = client.list_folder("/docs")

        assert len(items) == 4
        client._client.files_list_folder_continue.assert_called_once_with("c1")

    def test_retry_after_refresh_preserves_caller_arguments(self):
        """The retry must keep recursive=True.

        Regression: the retry called list_folder(path) without the
        caller's kwargs, so a token expiring during `ls -R` silently
        produced a top-level-only listing presented as a full one.
        """
        client = _client()
        expired = Mock()
        expired.is_expired_access_token.return_value = True

        ok = Mock(entries=self._entries(), has_more=False)
        client._client.files_list_folder.side_effect = [
            AuthError("request-1", expired),
            ok,
        ]
        # The refresh itself is covered separately; here only the retry
        # arguments are under test.
        client._handle_auth_error = Mock()

        client.list_folder("/docs", recursive=True)

        second_call = client._client.files_list_folder.call_args_list[1]
        assert second_call.kwargs.get("recursive") is True


class TestFileOperations:
    """The remaining API wrappers and their error translation."""

    def test_upload_reads_the_local_file_and_overwrites(self, tmp_path):
        source = tmp_path / "up.txt"
        source.write_bytes(b"payload")
        client = _client()

        client.upload_file(str(source), "/remote/up.txt")

        args = client._client.files_upload.call_args
        assert args.args[0] == b"payload"
        assert args.args[1] == "/remote/up.txt"

    def test_get_metadata_maps_a_file(self):
        client = _client()
        client._client.files_get_metadata.return_value = FileMetadata(
            name="a.txt",
            path_display="/a.txt",
            size=7,
            client_modified=datetime(2024, 1, 2),
        )

        meta = client.get_metadata("/a.txt")

        assert meta == {
            "name": "a.txt",
            "path": "/a.txt",
            "type": "file",
            "size": 7,
            "modified": datetime(2024, 1, 2),
        }

    def test_get_metadata_maps_a_folder(self):
        client = _client()
        client._client.files_get_metadata.return_value = FolderMetadata(
            name="docs", path_display="/docs"
        )

        meta = client.get_metadata("/docs")

        assert meta["type"] == "folder"
        assert meta["size"] is None

    def test_move_delete_and_create_folder_delegate_to_the_sdk(self):
        client = _client()

        client.move_file("/a", "/b")
        client.delete_file("/a")
        client.create_folder("/new")

        client._client.files_move_v2.assert_called_once_with("/a", "/b")
        client._client.files_delete_v2.assert_called_once_with("/a")
        client._client.files_create_folder_v2.assert_called_once_with("/new")

    def test_copy_delegates_without_autorename(self):
        client = _client()

        client.copy_file("/a", "/b")

        client._client.files_copy_v2.assert_called_once_with(
            "/a", "/b", autorename=False
        )

    def test_copy_resolves_a_destination_conflict_by_replacing(self):
        """A conflicting destination is replaced, not auto-renamed.

        This is deliberate: autorename would silently produce "file (1)".
        """
        from dropbox.exceptions import ApiError

        client = _client()
        relocation = Mock(spec=dropbox.files.RelocationError)
        relocation.is_from_lookup.return_value = False
        relocation.is_to.return_value = True
        relocation.get_to.return_value.is_conflict.return_value = True

        error = ApiError("req", relocation, "msg", None)
        client._client.files_copy_v2.side_effect = [error, None]

        client.copy_file("/a", "/b")

        client._client.files_delete_v2.assert_called_once_with("/b")
        assert client._client.files_copy_v2.call_count == 2

    def test_copy_reports_a_missing_source_as_file_not_found(self):
        from dropbox.exceptions import ApiError

        client = _client()
        relocation = Mock(spec=dropbox.files.RelocationError)
        relocation.is_from_lookup.return_value = True
        relocation.get_from_lookup.return_value.is_not_found.return_value = True

        client._client.files_copy_v2.side_effect = ApiError(
            "req", relocation, "msg", None
        )

        with pytest.raises(FileNotFoundError, match="/missing"):
            client.copy_file("/missing", "/b")


class TestAuthErrorPropagation:
    """Errors that are not an expired token must not be swallowed."""

    def test_non_expired_auth_error_is_reraised(self):
        client = _client()
        not_expired = Mock()
        not_expired.is_expired_access_token.return_value = False
        error = AuthError("request-1", not_expired)

        with pytest.raises(AuthError):
            client._handle_auth_error(error)

    def test_refresh_is_attempted_only_once(self):
        """_refresh_attempted must stop a refresh loop."""
        client = _client()
        client._refresh_attempted = True
        expired = Mock()
        expired.is_expired_access_token.return_value = True
        error = AuthError("request-1", expired)

        with pytest.raises(AuthError):
            client._handle_auth_error(error)

        client._client.refresh_access_token.assert_not_called()


class TestAuthRetryOnEveryOperation:
    """Every operation recovers from an expired token the same way."""

    @pytest.mark.parametrize(
        "method, sdk_attr, args",
        [
            ("upload_file", "files_upload", ("LOCAL", "/remote.txt")),
            ("copy_file", "files_copy_v2", ("/a", "/b")),
            ("move_file", "files_move_v2", ("/a", "/b")),
            ("delete_file", "files_delete_v2", ("/a",)),
            ("create_folder", "files_create_folder_v2", ("/new",)),
            ("get_metadata", "files_get_metadata", ("/a",)),
        ],
    )
    def test_expired_token_triggers_refresh_then_retry(
        self, method, sdk_attr, args, tmp_path
    ):
        client = _client()

        # upload_file reads from disk, so give it a real file.
        if args and args[0] == "LOCAL":
            local = tmp_path / "up.txt"
            local.write_bytes(b"x")
            args = (str(local),) + args[1:]

        expired = Mock()
        expired.is_expired_access_token.return_value = True

        success = FolderMetadata(name="a", path_display="/a")
        getattr(client._client, sdk_attr).side_effect = [
            AuthError("request-1", expired),
            success,
        ]
        client._handle_auth_error = Mock()

        getattr(client, method)(*args)

        client._handle_auth_error.assert_called_once()
        assert getattr(client._client, sdk_attr).call_count == 2


class TestRetryPolicy:
    """Transient failures back off and retry; real errors do not."""

    def _rate_limited(self, backoff=None):
        return RateLimitError("request-1", None, backoff)

    def test_rate_limit_is_retried_and_then_succeeds(self, no_real_sleeping):
        client = _client()
        client._client.files_get_metadata.side_effect = [
            self._rate_limited(),
            FolderMetadata(name="docs", path_display="/docs"),
        ]

        meta = client.get_metadata("/docs")

        assert meta["type"] == "folder"
        assert client._client.files_get_metadata.call_count == 2
        assert len(no_real_sleeping) == 1

    def test_servers_backoff_hint_is_honoured(self, no_real_sleeping):
        """Dropbox says how long to wait; that wins over our own schedule."""
        client = _client()
        client._client.files_get_metadata.side_effect = [
            self._rate_limited(backoff=17.0),
            FolderMetadata(name="docs", path_display="/docs"),
        ]

        client.get_metadata("/docs")

        # Jitter adds up to 25%, so check the band rather than equality.
        assert 17.0 <= no_real_sleeping[0] <= 17.0 * 1.25

    def test_backoff_grows_exponentially(self, no_real_sleeping):
        client = _client()
        client._client.files_get_metadata.side_effect = [
            self._rate_limited(),
            self._rate_limited(),
            self._rate_limited(),
            FolderMetadata(name="docs", path_display="/docs"),
        ]

        client.get_metadata("/docs")

        assert len(no_real_sleeping) == 3
        assert no_real_sleeping[0] < no_real_sleeping[1] < no_real_sleeping[2]

    def test_retries_are_capped_and_the_error_survives(self, no_real_sleeping):
        client = _client()
        client._client.files_get_metadata.side_effect = self._rate_limited()

        with pytest.raises(RateLimitError):
            client.get_metadata("/docs")

        assert client._client.files_get_metadata.call_count == MAX_ATTEMPTS

    def test_transient_network_error_is_retried_for_reads(
        self, no_real_sleeping
    ):
        client = _client()
        client._client.files_get_metadata.side_effect = [
            requests.exceptions.ConnectionError("reset"),
            FolderMetadata(name="docs", path_display="/docs"),
        ]

        client.get_metadata("/docs")

        assert client._client.files_get_metadata.call_count == 2

    def test_transient_network_error_is_not_retried_for_writes(
        self, no_real_sleeping
    ):
        """A dropped connection on a write may already have been applied.

        Repeating it blindly could duplicate or re-apply the change, so
        writes retry rate limits only.
        """
        client = _client()
        client._client.files_delete_v2.side_effect = (
            requests.exceptions.ConnectionError("reset")
        )

        with pytest.raises(requests.exceptions.ConnectionError):
            client.delete_file("/a")

        assert client._client.files_delete_v2.call_count == 1
        assert no_real_sleeping == []

    def test_rate_limit_is_still_retried_for_writes(self, no_real_sleeping):
        """A 429 was rejected without being acted on, so it is safe."""
        client = _client()
        client._client.files_delete_v2.side_effect = [
            self._rate_limited(),
            None,
        ]

        client.delete_file("/a")

        assert client._client.files_delete_v2.call_count == 2

    def test_ordinary_api_errors_are_not_retried(self, no_real_sleeping):
        """A missing file will not become present; do not waste time."""
        from dropbox.exceptions import ApiError

        client = _client()
        client._client.files_get_metadata.side_effect = ApiError(
            "req", Mock(), "not_found", None
        )

        with pytest.raises(ApiError):
            client.get_metadata("/missing")

        assert client._client.files_get_metadata.call_count == 1
        assert no_real_sleeping == []


class TestChunkedUpload:
    """Large uploads go through an upload session.

    files_upload is capped at 150 MB by Dropbox, so anything larger has to
    be chunked. The offsets are the risky part: getting them wrong corrupts
    the upload silently rather than failing, so they are asserted directly.
    """

    def _small_client(self, monkeypatch, chunk=16):
        """Shrink the chunk size so tests stay fast and readable."""
        monkeypatch.setattr("drobo.dropbox_client.CHUNK_SIZE", chunk)
        monkeypatch.setattr(
            "drobo.dropbox_client.UPLOAD_SESSION_THRESHOLD", chunk
        )
        client = _client()
        client._client.files_upload_session_start.return_value = Mock(
            session_id="session-1"
        )
        return client

    def test_small_file_uses_a_single_request(self, tmp_path, monkeypatch):
        client = self._small_client(monkeypatch)
        source = tmp_path / "small.bin"
        source.write_bytes(b"a" * 10)

        client.upload_file(str(source), "/small.bin")

        client._client.files_upload.assert_called_once()
        client._client.files_upload_session_start.assert_not_called()

    def test_file_exactly_at_the_threshold_uses_a_single_request(
        self, tmp_path, monkeypatch
    ):
        """The boundary is inclusive; only larger files need a session."""
        client = self._small_client(monkeypatch, chunk=16)
        source = tmp_path / "edge.bin"
        source.write_bytes(b"a" * 16)

        client.upload_file(str(source), "/edge.bin")

        client._client.files_upload.assert_called_once()
        client._client.files_upload_session_start.assert_not_called()

    def test_large_file_is_uploaded_in_a_session(self, tmp_path, monkeypatch):
        client = self._small_client(monkeypatch, chunk=16)
        payload = bytes(range(64))  # 64 bytes = 4 chunks of 16
        source = tmp_path / "big.bin"
        source.write_bytes(payload)

        client.upload_file(str(source), "/big.bin")

        client._client.files_upload.assert_not_called()
        client._client.files_upload_session_start.assert_called_once()

        # start(16) + append(16) + append(16) + finish(16) == 64 bytes
        sent = client._client.files_upload_session_start.call_args.args[0]
        for (
            call
        ) in client._client.files_upload_session_append_v2.call_args_list:
            sent += call.args[0]
        sent += client._client.files_upload_session_finish.call_args.args[0]

        assert sent == payload, "reassembled upload must match the source"

    def test_session_cursor_offsets_advance_correctly(
        self, tmp_path, monkeypatch
    ):
        """Each append must be told the offset it is writing at."""
        client = self._small_client(monkeypatch, chunk=16)
        source = tmp_path / "big.bin"
        source.write_bytes(b"a" * 64)

        offsets = []
        client._client.files_upload_session_append_v2.side_effect = (
            lambda data, cursor: offsets.append(cursor.offset)
        )

        client.upload_file(str(source), "/big.bin")

        # start consumes 0-16, so the appends land at 16 and 32; the final
        # 16 bytes go to finish.
        assert offsets == [16, 32]

    def test_session_commits_to_the_right_path_and_overwrites(
        self, tmp_path, monkeypatch
    ):
        client = self._small_client(monkeypatch, chunk=16)
        source = tmp_path / "big.bin"
        source.write_bytes(b"a" * 40)

        client.upload_file(str(source), "/remote/big.bin")

        commit = client._client.files_upload_session_finish.call_args.args[2]
        assert commit.path == "/remote/big.bin"
        assert commit.mode == dropbox.files.WriteMode.overwrite

    def test_uneven_final_chunk_is_handled(self, tmp_path, monkeypatch):
        """A file that is not a whole multiple of the chunk size."""
        client = self._small_client(monkeypatch, chunk=16)
        payload = b"b" * 37  # 16 + 16 + 5
        source = tmp_path / "odd.bin"
        source.write_bytes(payload)

        client.upload_file(str(source), "/odd.bin")

        sent = client._client.files_upload_session_start.call_args.args[0]
        for (
            call
        ) in client._client.files_upload_session_append_v2.call_args_list:
            sent += call.args[0]
        sent += client._client.files_upload_session_finish.call_args.args[0]

        assert sent == payload
        assert len(sent) == 37
