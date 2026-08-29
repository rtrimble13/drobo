"""
Tests for the Dropbox API client.
"""

import os
from unittest.mock import Mock

import pytest

from drobo.dropbox_client import DropboxClient


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
        response = Mock()
        response.content = b"hello from dropbox"
        client._client.files_download.return_value = (Mock(), response)

        client.download_file("/remote.txt", str(dest))

        assert dest.read_bytes() == b"hello from dropbox"
        assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]

    def test_successful_download_overwrites_existing_file(self, tmp_path):
        """Overwriting on success still works."""
        dest = tmp_path / "out.txt"
        dest.write_text("old contents")

        client = _client()
        response = Mock()
        response.content = b"new contents"
        client._client.files_download.return_value = (Mock(), response)

        client.download_file("/remote.txt", str(dest))

        assert dest.read_bytes() == b"new contents"

    def test_downloaded_file_respects_umask(self, tmp_path):
        """Downloads follow the user's umask, not mkstemp's private 0600."""
        dest = tmp_path / "out.txt"

        client = _client()
        response = Mock()
        response.content = b"data"
        client._client.files_download.return_value = (Mock(), response)

        old_umask = os.umask(0o022)
        try:
            client.download_file("/remote.txt", str(dest))
        finally:
            os.umask(old_umask)

        assert oct(dest.stat().st_mode & 0o777) == oct(0o644)
