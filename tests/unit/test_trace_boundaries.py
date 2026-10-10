import json
import pytest
from agenttest_lab.domain.trace import TraceValidationError, validate_and_redact_jsonl


@pytest.mark.parametrize("source,code", [
    ('{"case_key":"case-1","case_key":"case-2"}', "DUPLICATE_JSON_KEY"),
    ('{"case_key":"case-1","score":NaN}', "NONFINITE_NUMBER"),
    ('{"case_key":"case-1","score":Infinity}', "NONFINITE_NUMBER"),
    ('{"case_key":"case-1","score":1e999}', "NONFINITE_NUMBER"),
    ('{"case_key":"case-1","text":"\\ud800"}', "INVALID_UNICODE"),
    (b'\xff', "INVALID_UNICODE"),
])
def test_invalid_trace_has_stable_failure(source, code):
    with pytest.raises(TraceValidationError) as error:
        validate_and_redact_jsonl(source)
    assert error.value.code == code


def test_trace_byte_budget():
    source = json.dumps({"case_key": "case-1", "output": "x" * 1_048_576})
    with pytest.raises(TraceValidationError) as error:
        validate_and_redact_jsonl(source)
    assert error.value.code == "TRACE_BUDGET_EXCEEDED"


def test_trace_depth_budget():
    value = 0
    for _ in range(40): value = [value]
    with pytest.raises(TraceValidationError) as error:
        validate_and_redact_jsonl(json.dumps({"case_key": "case-1", "output": value}))
    assert error.value.code == "TRACE_STRUCTURE_BUDGET_EXCEEDED"


def test_trace_node_budget():
    with pytest.raises(TraceValidationError) as error:
        validate_and_redact_jsonl(json.dumps({"case_key": "case-1", "output": [0] * 20_001}))
    assert error.value.code == "TRACE_STRUCTURE_BUDGET_EXCEEDED"


def test_trace_record_budget():
    with pytest.raises(TraceValidationError) as error:
        validate_and_redact_jsonl('{"case_key":"case-1"}\n' * 1001)
    assert error.value.code == "TRACE_RECORD_BUDGET_EXCEEDED"


def test_wrong_case_trace_is_rejected():
    with pytest.raises(TraceValidationError) as error:
        validate_and_redact_jsonl('{"case_key":"case-2"}', expected_case_key="case-1")
    assert error.value.code == "TRACE_CASE_BINDING_MISMATCH"


def test_multiple_records_for_same_case_remain_supported():
    result = validate_and_redact_jsonl('{"case_key":"case-1","event":"start"}\n{"case_key":"case-1","event":"end"}', expected_case_key="case-1")
    assert result.line_count == 2


@pytest.mark.parametrize("case_key", [
    "contact@example.invalid",
    "case key",
    "case/key",
    "case\\\\key",
    "x" * 129,
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
])
def test_trace_case_identity_cannot_be_rewritten_by_redaction(case_key):
    source = json.dumps({"case_key": case_key, "event": "synthetic"})
    with pytest.raises(TraceValidationError) as error:
        validate_and_redact_jsonl(source)
    assert error.value.code == "INVALID_CASE_KEY"


def test_valid_case_identity_is_preserved_for_dataset_binding():
    source = json.dumps({"case_key": "batch.2026:case-1", "event": "synthetic"})
    result = validate_and_redact_jsonl(source, expected_case_key="batch.2026:case-1")
    assert result.records[0]["case_key"] == "batch.2026:case-1"
    assert result.redaction_count == 0


def test_optional_case_key_still_permits_generic_event_without_identity():
    result = validate_and_redact_jsonl('{"event":"synthetic"}', require_case_key=False)
    assert result.records[0] == {"event": "synthetic"}
