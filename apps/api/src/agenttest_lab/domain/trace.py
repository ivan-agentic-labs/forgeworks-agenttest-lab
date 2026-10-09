"""Defensive JSONL trace validation and redaction.

This module deliberately only parses data. It never imports, evaluates, or executes
values from a trace. The returned digest is always computed over the redacted form.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

_REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?:pass(?:word|phrase)?|secret|token|api[_-]?key|authorization|cookie|credential|private[_-]?key|access[_-]?key|refresh[_-]?token)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_HEX_SECRET = re.compile(r"\b(?:sk|rk|pk)_[A-Za-z0-9_-]{12,}\b")


class TraceValidationError(ValueError):
    """A trace validation failure with a stable code and source line."""

    def __init__(self, line_number: int, code: str, detail: str):
        self.line_number = line_number
        self.code = code
        self.detail = detail
        super().__init__(f"line {line_number}: {code}: {detail}")


@dataclass(frozen=True)
class TraceValidationResult:
    records: tuple[dict[str, Any], ...]
    redacted_jsonl: str
    sha256: str
    redaction_count: int
    line_count: int


def _redact_string(value: str) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return _REDACTED

    for pattern in (_BEARER, _JWT, _HEX_SECRET, _EMAIL):
        value = pattern.sub(replace, value)
    return value, count


def redact_trace_value(value: Any, *, _sensitive: bool = False) -> tuple[Any, int]:
    """Recursively redact secret-shaped keys and common secret/PII string forms."""
    if _sensitive:
        return _REDACTED, 1
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        count = 0
        for key, item in value.items():
            key_text = str(key)
            clean, changed = redact_trace_value(item, _sensitive=bool(_SENSITIVE_KEY.search(key_text)))
            out[key_text] = clean
            count += changed
        return out, count
    if isinstance(value, list):
        out_list = []
        count = 0
        for item in value:
            clean, changed = redact_trace_value(item)
            out_list.append(clean)
            count += changed
        return out_list, count
    if isinstance(value, str):
        return _redact_string(value)
    return value, 0


def validate_and_redact_jsonl(content: str | bytes, *, require_case_key: bool = True) -> TraceValidationResult:
    """Parse JSONL, enforce data-only object records, redact, and hash the result.

    Blank lines are ignored. Every nonblank line must be a JSON object. A case_key is
    required by default so traces cannot be detached from a dataset case. No code is
    executed and no original unredacted representation is retained in the result.
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="strict")
    if not isinstance(content, str):
        raise TypeError("content must be str or UTF-8 bytes")

    records: list[dict[str, Any]] = []
    redacted_lines: list[str] = []
    redactions = 0
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            parsed = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise TraceValidationError(line_number, "INVALID_JSON", exc.msg) from exc
        if not isinstance(parsed, dict):
            raise TraceValidationError(line_number, "INVALID_RECORD", "each JSONL record must be an object")
        if require_case_key and (not isinstance(parsed.get("case_key"), str) or not parsed["case_key"].strip()):
            raise TraceValidationError(line_number, "MISSING_CASE_KEY", "case_key must be a non-empty string")
        redacted, count = redact_trace_value(parsed)
        assert isinstance(redacted, dict)
        records.append(redacted)
        redactions += count
        redacted_lines.append(json.dumps(redacted, sort_keys=True, separators=(",", ":"), ensure_ascii=False))

    if not records:
        raise TraceValidationError(1, "EMPTY_TRACE", "trace must contain at least one JSON object")
    redacted_jsonl = "\n".join(redacted_lines) + "\n"
    digest = hashlib.sha256(redacted_jsonl.encode("utf-8")).hexdigest()
    return TraceValidationResult(tuple(records), redacted_jsonl, digest, redactions, len(records))
