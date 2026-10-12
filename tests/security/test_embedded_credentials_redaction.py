"""Regression tests for credentials embedded in otherwise neutral trace text."""
import hashlib
import json

import pytest

from agenttest_lab.domain.trace import validate_and_redact_jsonl


@pytest.mark.parametrize(
    "observation,private_value,expected",
    [
        (
            "GET https://api.example.invalid/run?access_token=synthetic-password&limit=5",
            "synthetic-password",
            "GET https://api.example.invalid/run?access_token=[REDACTED]&limit=5",
        ),
        (
            "postgresql://app:synthetic-pw" + chr(64) + "db.internal:5432/app",
            "synthetic-pw",
            "postgresql://[REDACTED]" + chr(64) + "db.internal:5432/app",
        ),
        (
            "Authorization: Basic YWxpY2U6c2VjcmV0",
            "YWxpY2U6c2VjcmV0",
            "Authorization: [REDACTED]",
        ),
        (
            "tool arguments: client_secret=abc123XYZ; step=4",
            "abc123XYZ",
            "tool arguments: client_secret=[REDACTED]; step=4",
        ),
        (
            "redis://worker:fake-redis-password" + chr(64) + "cache.example.invalid:6379/0",
            "fake-redis-password",
            "redis://[REDACTED]" + chr(64) + "cache.example.invalid:6379/0",
        ),
    ],
)
def test_embedded_credentials_never_appear_in_trace_artifacts(observation, private_value, expected):
    source = json.dumps({"case_key": "case-1", "observation": observation, "latency_ms": 12})
    result = validate_and_redact_jsonl(source, expected_case_key="case-1")
    assert result.records[0]["observation"] == expected
    assert result.records[0]["latency_ms"] == 12
    assert private_value not in result.redacted_jsonl
    assert result.redaction_count == 1
    assert result.sha256 == hashlib.sha256(result.redacted_jsonl.encode("utf-8")).hexdigest()


def test_sensitive_assignment_used_as_object_key_is_redacted():
    private_key = "https://example.invalid/?api_key=synthetic-secret"
    source = json.dumps({"case_key": "case-1", "messages": {private_key: "public"}})
    result = validate_and_redact_jsonl(source)
    assert private_key not in result.redacted_jsonl
    assert list(result.records[0]["messages"]) == ["[REDACTED_KEY_1]"]


def test_noncredential_debug_query_is_preserved():
    source = json.dumps({
        "case_key": "case-1",
        "observation": "GET https://example.invalid/events?offset=7&limit=5",
    })
    result = validate_and_redact_jsonl(source)
    assert result.records[0]["observation"].endswith("?offset=7&limit=5")
    assert result.redaction_count == 0
