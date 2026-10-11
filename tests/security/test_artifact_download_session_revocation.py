"""Offline, signed session-revocation proof for download capabilities."""
from types import SimpleNamespace
from uuid import uuid4
import time

import jwt
import pytest
from fastapi import HTTPException

from agenttest_lab.infrastructure.artifact_downloads import issue_download, verify_download

SECRET = "synthetic-separate-artifact-download-key-long-enough"


@pytest.fixture(autouse=True)
def staging_identity(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ARTIFACT_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("DEV_AUTH_SECRET", "some-other-development-test-key")


def identifiers():
    return (str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()))


def assert_denied(call, code, status):
    with pytest.raises(HTTPException) as exc:
        call()
    assert exc.value.status_code == status
    assert exc.value.detail["code"] == code


def test_valid_download_is_bound_to_live_supabase_session():
    tenant, actor, artifact, sid = identifiers()
    sha = "a" * 64
    token, expires_at = issue_download(tenant, actor, artifact, sha, sid)
    store = SimpleNamespace(session_active=lambda t, a, s: (t, a, s) == (tenant, actor, sid))
    result = verify_download(token, artifact, store)
    assert result["tenant_id"] == tenant
    assert result["actor"] == actor
    assert result["session_id"] == sid
    assert result["sha256"] == sha
    assert expires_at > int(time.time())


def test_revoked_session_rejects_even_unexpired_correctly_signed_download():
    tenant, actor, artifact, sid = identifiers()
    token, expires_at = issue_download(tenant, actor, artifact, "a" * 64, sid)
    assert expires_at > int(time.time())
    store = SimpleNamespace(session_active=lambda t, a, s: False)
    assert_denied(lambda: verify_download(token, artifact, store), "ARTIFACT_SESSION_REVOKED", 403)


def test_session_lookup_error_or_missing_adapter_fails_closed():
    tenant, actor, artifact, sid = identifiers()
    token, _ = issue_download(tenant, actor, artifact, "a" * 64, sid)
    assert_denied(lambda: verify_download(token, artifact, object()), "ARTIFACT_SESSION_CHECK_UNAVAILABLE", 503)
    def unavailable(*_):
        raise RuntimeError("synthetic Supabase session lookup outage")
    assert_denied(
        lambda: verify_download(token, artifact, SimpleNamespace(session_active=unavailable)),
        "ARTIFACT_SESSION_CHECK_UNAVAILABLE", 503
    )


@pytest.mark.parametrize("bad_session", [None, "", "not-a-uuid", {}, 123])
def test_supabase_capability_cannot_be_issued_without_verified_session(bad_session):
    tenant, actor, artifact, _ = identifiers()
    assert_denied(
        lambda: issue_download(tenant, actor, artifact, "a" * 64, bad_session),
        "ARTIFACT_SESSION_BINDING_REQUIRED", 503
    )


def test_legacy_signed_link_without_session_cannot_bypass_supabase_revalidation():
    tenant, actor, artifact, sid = identifiers()
    claims = {"iss": "forgeworks-artifacts", "aud": "artifact-download",
              "sub": artifact, "tenant_id": tenant, "actor": actor,
              "sha256": "a" * 64, "exp": int(time.time()) + 300}
    token = jwt.encode(claims, SECRET, algorithm="HS256")
    called = []
    store = SimpleNamespace(session_active=lambda *_: called.append(True) or True)
    assert_denied(lambda: verify_download(token, artifact, store), "INVALID_ARTIFACT_CAPABILITY", 403)
    assert called == []


def test_download_capability_is_immutable_to_different_artifact():
    tenant, actor, artifact, sid = identifiers()
    token, _ = issue_download(tenant, actor, artifact, "a" * 64, sid)
    called = []
    assert_denied(
        lambda: verify_download(token, str(uuid4()), SimpleNamespace(session_active=lambda *_: called.append(True))),
        "INVALID_ARTIFACT_CAPABILITY", 403
    )
    assert called == []


def test_local_dev_download_capability_keeps_existing_non_supabase_behavior(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    tenant, actor, artifact, _ = identifiers()
    token, _ = issue_download(tenant, actor, artifact, "a" * 64)
    claims = verify_download(token, artifact)
    assert claims["session_id"] is None
