"""Strict bounded JSONL dataset input; never execute dataset content."""
import hashlib
import json
import math
import re

MAX_BYTES = 1_048_576


def parse_dataset(source: str, expected_sha: str, expected_count: int) -> list[dict]:
    raw = source.encode("utf-8")
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("DATASET_SOURCE_BUDGET_EXCEEDED")
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("DATASET_SOURCE_DIGEST_MISMATCH")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DATASET_DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("DATASET_NONFINITE_NUMBER")
    lines = source.split("\n")
    if lines[-1] == "":
        lines.pop()
    if not 1 <= len(lines) <= 1000 or len(lines) != expected_count:
        raise ValueError("DATASET_CASE_COUNT_MISMATCH")
    cases, keys, nodes = [], set(), 0
    for line in lines:
        try:
            case = json.loads(line, object_pairs_hook=unique, parse_constant=constant)
        except (json.JSONDecodeError, RecursionError) as error:
            raise ValueError("DATASET_JSONL_INVALID") from error
        if not isinstance(case, dict) or set(case) != {"case_key", "input", "expected"}:
            raise ValueError("DATASET_CASE_SCHEMA_INVALID")
        key = case["case_key"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", key) or key in keys:
            raise ValueError("DATASET_CASE_KEY_INVALID")
        keys.add(key)
        pending = [(case, 0)]
        while pending:
            value, depth = pending.pop(); nodes += 1
            if nodes > 20000 or depth > 32:
                raise ValueError("DATASET_STRUCTURE_BUDGET_EXCEEDED")
            if isinstance(value, dict):
                pending.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                pending.extend((item, depth + 1) for item in value)
            elif isinstance(value, float) and not math.isfinite(value):
                raise ValueError("DATASET_NONFINITE_NUMBER")
        cases.append(case)
    return cases
