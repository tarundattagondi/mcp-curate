"""SSRF guard tests."""

from __future__ import annotations

import pytest

from mcp_curate.server.safety import UnsafeURLError, assert_safe_url


def test_blocks_cloud_metadata_ip():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://169.254.169.254/latest/meta-data/")


def test_blocks_localhost_by_default():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://127.0.0.1:8080/api")
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://localhost/api")


def test_blocks_private_ranges_by_default():
    for url in ("http://10.0.0.5/x", "http://192.168.1.10/x", "http://172.16.0.1/x"):
        with pytest.raises(UnsafeURLError):
            assert_safe_url(url)


def test_allows_local_when_opted_in():
    # Should not raise.
    assert_safe_url("http://127.0.0.1:8080/api", allow_local=True)
    assert_safe_url("http://10.0.0.5/x", allow_local=True)


def test_metadata_blocked_even_with_allow_local():
    # Link-local/metadata is never allowed, even with the opt-in.
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://169.254.169.254/", allow_local=True)


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("file:///etc/passwd")
    with pytest.raises(UnsafeURLError):
        assert_safe_url("ftp://example.com/x")


def test_allows_public_host():
    # Public IP literal; should not raise (no DNS needed).
    assert_safe_url("https://1.1.1.1/api")
