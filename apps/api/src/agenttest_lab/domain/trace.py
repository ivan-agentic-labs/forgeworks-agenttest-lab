"""Defensive JSONL trace validation and redaction.

This module deliberately only parses data. It never imports, evaluates, or executes
values from a trace. The returned digest is always computed over the redacted form.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any

_REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?:pass(?:word|phrase)?|secret|token|api[_-]?key|authorization|cookie|credential|private[_-]?key|access[_-]?key|refresh[_-]?token)",
    re.IGNORECASE,
)
# PII may be an opaque value (for example a numeric identifier) that cannot
# be discovered safely with a regex over the value itself. Redact structured
# PII field names at any nesting level without treating every numeric trace
# field as sensitive.
_PII_KEY = re.compile(
    r"(?:^|[_-])(?:ssn|social[_-]?security(?:[_-]?(?:number|id))?|national[_-]?id|"
    r"phone(?:[_-]?number)?|mobile(?:[_-]?number)?|email(?:[_-]?address)?|"
    r"date[_-]?of[_-]?birth|dob|passport(?:[_-]?(?:number|no))?|"\n    r"ip[_-]?address|(?:client|customer|source|remote|user)[_-]?ip)(?:$|[_-])",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_HEX_SECRET = re.compile(r"\b(?:sk|rk|pk)_[A-Za-z0-9_-]{12,}\b")
# Recognizable provider credential formats can appear in otherwise neutral
# fields such as "message", "observation", or even arbitrary map keys.
# These deliberately match provider-specific shapes rather than all long
# alphanumeric strings, which would destroy benign trace observations.
_GITHUB_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,})\b")
_GITLAB_TOKEN = re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")
_AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_GOOGLE_API_KEY = re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b")


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

    for pattern in (
        _BEARER, _JWT, _HEX_SECRET, _EMAIL,
        _GITHUB_TOKEN, _GITLAB_TOKEN, _AWS_ACCESS_KEY, _GOOGLE_API_KEY,
    ):
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
            # JSON object *keys* can themselves contain customer identifiers.
            # Never persist the original key when it matches a sensitive
            # literal. Use unique positional names to preserve entries if
            # multiple email addresses were used as map keys.
            _, key_redactions = _redact_string(key_text)
            safe_key = key_text
            if key_redactions:
                suffix = len(out) + 1
                safe_key = f"[REDACTED_KEY_{suffix}]"
                while safe_key in out or safe_key in value:
                    suffix += 1
                    safe_key = f"[REDACTED_KEY_{suffix}]"
            # Normalize common camelCase field names before matching PII
            # markers such as phoneNumber, nationalId, and dateOfBirth.
            canonical_key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key_text)
            clean, changed = redact_trace_value(
                item,
                _sensitive=bool(_SENSITIVE_KEY.search(key_text) or _PII_KEY.search(canonical_key)),
            )
            out[safe_key] = clean
            count += changed + key_redactions
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


def validate_and_redact_jsonl(content: str | bytes, *, require_case_key: bool = True, expected_case_key: str | None = None) -> TraceValidationResult:
    """Parse JSONL, enforce data-only object records, redact, and hash the result.

    Blank lines are ignored. Every nonblank line must be a JSON object. A case_key is
    required by default so traces cannot be detached from a dataset case. No code is
    executed and no original unredacted representation is retained in the result.
    """
    if not isinstance(content, (str, bytes)):
        raise TypeError("content must be str or UTF-8 bytes")
    if len(content) > 1_048_576:
        raise TraceValidationError(1, "TRACE_BUDGET_EXCEEDED", "trace exceeds 1 MiB")
    try:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="strict")
        if len(content.encode("utf-8", errors="strict")) > 1_048_576:
            raise TraceValidationError(1, "TRACE_BUDGET_EXCEEDED", "trace exceeds 1 MiB")
    except UnicodeError as error:
        raise TraceValidationError(1, "INVALID_UNICODE", "trace must be valid UTF-8") from error

    nodes = 0
    records: list[dict[str, Any]] = []
    redacted_lines: list[str] = []
    redactions = 0
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if not raw_line.strip():
            continue
        if len(records) >= 1000:
            raise TraceValidationError(line_number, "TRACE_RECORD_BUDGET_EXCEEDED", "trace exceeds 1000 records")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise TraceValidationError(line_number, "DUPLICATE_JSON_KEY", "duplicate JSON keys are forbidden")
                result[key] = value
            return result
        def constant(_):
            raise TraceValidationError(line_number, "NONFINITE_NUMBER", "trace numbers must be finite")
        try:
            parsed = json.loads(raw_line, object_pairs_hook=unique, parse_constant=constant)
        except TraceValidationError:
            raise
        except (ValueError, RecursionError) as exc:
            raise TraceValidationError(line_number, "INVALID_JSON", "record is invalid or excessively nested JSON") from exc
        pending = [(parsed, 0)]
        while pending:
            value, depth = pending.pop()
            nodes += 1
            if nodes > 20000 or depth > 32:
                raise TraceValidationError(line_number, "TRACE_STRUCTURE_BUDGET_EXCEEDED", "trace exceeds structural limits")
            if isinstance(value, dict):
                pending.extend((key, depth + 1) for key in value)
                pending.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                pending.extend((item, depth + 1) for item in value)
            elif isinstance(value, float) and not math.isfinite(value):
                raise TraceValidationError(line_number, "NONFINITE_NUMBER", "trace numbers must be finite")
            elif isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                raise TraceValidationError(line_number, "INVALID_UNICODE", "unpaired Unicode surrogates are forbidden")
        if not isinstance(parsed, dict):
            raise TraceValidationError(line_number, "INVALID_RECORD", "each JSONL record must be an object")
        case_key = parsed.get("case_key")
        if require_case_key and (not isinstance(case_key, str) or not case_key.strip()):
            raise TraceValidationError(line_number, "MISSING_CASE_KEY", "case_key must be a non-empty string")
        # The dataset parser uses this exact identity profile. Reject PII,
        # whitespace and oversized identities before redaction could alter the
        # key used to bind a trace to its dataset case.
        if case_key is not None and (
            not isinstance(case_key, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", case_key) is None
            or _JWT.fullmatch(case_key) is not None
            or _HEX_SECRET.fullmatch(case_key) is not None
            or any(pattern.fullmatch(case_key) is not None for pattern in (
                _GITHUB_TOKEN, _GITLAB_TOKEN, _AWS_ACCESS_KEY, _GOOGLE_API_KEY,
            ))
        ):
            raise TraceValidationError(line_number, "INVALID_CASE_KEY", "case_key must match the dataset identity profile")
        if expected_case_key is not None and case_key != expected_case_key:
            raise TraceValidationError(line_number, "TRACE_CASE_BINDING_MISMATCH", "trace record belongs to another case")
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
