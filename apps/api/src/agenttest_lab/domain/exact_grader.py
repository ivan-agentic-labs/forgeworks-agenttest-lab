"""Data-only exact JSON grading; no agent execution or fuzzy comparison."""
import hashlib
import json
import math
from pathlib import Path

MODE = "exact-json-v1"
# Implementation identity follows the executable grader bytes, not a caller label.
GRADER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def validate_output(value):
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > 20000 or depth > 32:
            raise ValueError("OUTPUT_STRUCTURE_BUDGET_EXCEEDED")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("OUTPUT_JSON_INVALID")
            pending.extend((key, depth + 1) for key in item)
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            item.encode("utf-8", errors="strict")
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("OUTPUT_NONFINITE_NUMBER")
        elif item is not None and type(item) not in (bool, int):
            raise ValueError("OUTPUT_JSON_INVALID")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > 1048576:
        raise ValueError("OUTPUT_BYTE_BUDGET_EXCEEDED")
    return encoded


def equal_json(left, right):
    """JSON numbers compare numerically; booleans are distinct from numbers."""
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(equal_json(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(equal_json(a, b) for a, b in zip(left, right))
    return left == right


def grade(expected, observed):
    validate_output(expected)
    validate_output(observed)
    matched = equal_json(expected, observed)
    return ("PASS", 1.0) if matched else ("FAIL", 0.0)
