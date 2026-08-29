"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    """Never actually sleep during the retry backoff.

    The client retries transient failures with exponential backoff, so any
    test that provokes one would otherwise stall the suite for ~15s. Tests
    that care about the backoff assert on the recorded delays instead.
    """
    slept = []
    monkeypatch.setattr(
        "drobo.dropbox_client.time.sleep", lambda s: slept.append(s)
    )
    return slept
