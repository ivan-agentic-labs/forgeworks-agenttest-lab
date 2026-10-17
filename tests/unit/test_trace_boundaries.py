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
    "contact" + chr(64) + "example.invalid",
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


def test_nested_structured_pii_fields_are_redacted_before_hashing():
    private_email = "synthetic" + chr(64) + "example.invalid"
    source = json.dumps({
        "case_key": "case-1",
        "metadata": {
            "customer_phone_number": "+628123456789",
            "national_id": 123456789,
            "date_of_birth": "2001-01-02",
            "email_address": private_email,
            "microphone_level": 0.5,
        },
        "event": "completed",
    })
    result = validate_and_redact_jsonl(source, expected_case_key="case-1")
    record = result.records[0]
    metadata = record["metadata"]
    assert record["case_key"] == "case-1"
    assert record["event"] == "completed"
    for key in ("customer_phone_number", "national_id", "date_of_birth", "email_address"):
        assert metadata[key] == "[REDACTED]"
    assert metadata["microphone_level"] == 0.5
    assert result.redaction_count == 4
    for secret in ("+628123456789", "123456789", "2001-01-02", private_email):
        assert secret not in result.redacted_jsonl
    import hashlib
    assert result.sha256 == hashlib.sha256(result.redacted_jsonl.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("field", [
    "ssn",
    "passport_number",
    "mobile_number",
    "contact-email",
    "billing_phone",
])
def test_structured_pii_key_is_redacted_even_if_value_has_no_known_pattern(field):
    source = json.dumps({"case_key": "case-1", "attributes": {field: "opaquevalue123"}})
    result = validate_and_redact_jsonl(source)
    assert result.records[0]["attributes"][field] == "[REDACTED]"
    assert "opaquevalue123" not in result.redacted_jsonl


def test_dynamic_sensitive_json_keys_do_not_leak_or_collide():
    email1 = "alpha" + chr(64) + "example.invalid"
    email2 = "beta" + chr(64) + "example.invalid"
    # Explicit placeholder is intentionally present to expose key collisions.
    original = {
        "case_key": "case-1",
        "contacts": {
            "[REDACTED_KEY_1]": "safe-existing-entry",
            email1: "first-value",
            email2: "second-value",
        },
    }
    result = validate_and_redact_jsonl(json.dumps(original))
    contacts = result.records[0]["contacts"]
    assert len(contacts) == 3
    assert contacts["[REDACTED_KEY_1]"] == "safe-existing-entry"
    assert set(contacts.values()) == {"safe-existing-entry", "first-value", "second-value"}
    assert all(key not in contacts for key in (email1, email2))
    assert email1 not in result.redacted_jsonl and email2 not in result.redacted_jsonl
    assert result.redaction_count == 2


@pytest.mark.parametrize("field", [
    "phoneNumber", "customerPhone", "nationalId", "dateOfBirth",
    "passportNo", "emailAddress", "mobileNumber",
])
def test_camel_case_pii_field_values_are_redacted(field):
    source = json.dumps({"case_key": "case-1", "metadata": {field: 123456789}})
    result = validate_and_redact_jsonl(source)
    assert result.records[0]["metadata"][field] == "[REDACTED]"
    assert "123456789" not in result.redacted_jsonl
    assert result.redaction_count == 1


def test_redacted_dynamic_key_hash_is_deterministic_without_raw_identifier():
    from hashlib import sha256
    email = "name" + chr(64) + "example.invalid"
    source = json.dumps({"case_key": "case-1", "metadata": {email: "safe"}})
    first = validate_and_redact_jsonl(source)
    second = validate_and_redact_jsonl(source)
    assert first.sha256 == second.sha256
    assert first.sha256 == sha256(first.redacted_jsonl.encode("utf-8")).hexdigest()
    assert email not in first.redacted_jsonl


@pytest.mark.parametrize("credential", [
    "ghp_" + "A" * 36,
    "gho_" + "B" * 36,
    "ghs_" + "C" * 36,
    "github_pat_" + "D" * 26 + "_" + "E" * 26,
    "glpat-" + "F" * 20,
    "AKIA" + "G" * 16,
    "ASIA" + "H" * 16,
    "AIza" + "I" * 35,
])
def test_provider_credentials_are_redacted_in_neutral_trace_fields(credential):
    original = {"case_key": "case-1", "observation": "received " + credential + " in a tool result"}
    result = validate_and_redact_jsonl(json.dumps(original))
    assert credential not in result.redacted_jsonl
    assert result.records[0]["observation"] == "received [REDACTED] in a tool result"
    assert result.redaction_count == 1


@pytest.mark.parametrize("credential", [
    "ghp_" + "A" * 36,
    "glpat-" + "B" * 20,
    "AKIA" + "C" * 16,
    "AIza" + "D" * 35,
])
def test_provider_credentials_used_as_json_object_keys_are_not_persisted(credential):
    original = {"case_key": "case-1", "tool_output": {credential: "opaque observation"}}
    result = validate_and_redact_jsonl(json.dumps(original))
    keys = list(result.records[0]["tool_output"])
    assert len(keys) == 1 and keys[0].startswith("[REDACTED_KEY_")
    assert credential not in result.redacted_jsonl
    assert result.redaction_count == 1


def test_multiple_provider_patterns_and_sha_are_stable():
    from hashlib import sha256
    tokens = ["ghp_" + "A" * 36, "glpat-" + "B" * 20, "AKIA" + "C" * 16, "AIza" + "D" * 35]
    source = json.dumps({"case_key": "case-1", "events": [{"observation": item} for item in tokens]})
    first = validate_and_redact_jsonl(source)
    second = validate_and_redact_jsonl(source)
    assert first.redaction_count == len(tokens)
    assert all(item not in first.redacted_jsonl for item in tokens)
    assert first.sha256 == second.sha256 == sha256(first.redacted_jsonl.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("ordinary", [
    "ghp_" + "A" * 12,
    "glpat-" + "B" * 8,
    "AKIA" + "C" * 8,
    "AIza" + "D" * 12,
    "trace_request_id_2026",
])
def test_short_provider_like_strings_and_benign_ids_are_retained(ordinary):
    result = validate_and_redact_jsonl(json.dumps({"case_key": "case-1", "observation": ordinary}))
    assert result.records[0]["observation"] == ordinary
    assert result.redaction_count == 0


@pytest.mark.parametrize("secret_identity", [
    "ghp_" + "A" * 36,
    "github_pat_" + "B" * 26,
    "glpat-" + "C" * 20,
    "AKIA" + "D" * 16,
    "ASIA" + "E" * 16,
    "AIza" + "F" * 35,
])
def test_provider_credential_is_never_accepted_as_trace_case_identity(secret_identity):
    # A case identity must remain byte-for-byte stable after trace redaction.
    # If the redactor would mask it, reject rather than detach evidence from
    # the dataset case by silently changing "case_key" to "[REDACTED]".
    source = json.dumps({"case_key": secret_identity, "observation": "safe"})
    with pytest.raises(TraceValidationError) as error:
        validate_and_redact_jsonl(source, expected_case_key=secret_identity)
    assert error.value.code == "INVALID_CASE_KEY"


def test_provider_like_but_safe_case_identity_remains_unchanged():
    case_key = "audit-AKIA-not-a-real-key"
    result = validate_and_redact_jsonl(json.dumps({"case_key": case_key, "event": "safe"}),
                                       expected_case_key=case_key)
    assert result.records[0]["case_key"] == case_key
    assert result.redaction_count == 0


@pytest.mark.parametrize("field", [
    "client_ip", "remoteIp", "ip_address", "ipAddress",
    "source_ip", "customer_ip", "userIp",
])
def test_structured_network_identifiers_are_redacted_from_persisted_traces(field):
    source = json.dumps({
        "case_key": "case-1",
        "metadata": {field: "203.0.113.42", "ip_version": 4},
    })
    result = validate_and_redact_jsonl(source, expected_case_key="case-1")
    assert result.records[0]["metadata"][field] == "[REDACTED]"
    assert result.records[0]["metadata"]["ip_version"] == 4
    assert "203.0.113.42" not in result.redacted_jsonl
    assert result.redaction_count == 1


@pytest.mark.parametrize("field", [
    "firstName", "last_name", "fullName", "legal_name",
    "streetAddress", "mailing_address", "billingAddress", "shipping_address",
    "residential_address", "postalCode", "zip_code",
    "bankAccount", "bank_account_number", "creditCardNumber", "card_number",
    "iban", "swiftBic", "routing_number", "taxId",
])
def test_nested_personal_and_payment_identifiers_never_persist(field):
    sensitive_value = "opaque-synthetic-identifier-123456"
    original = {"case_key": "case-1", "observation": {
        "nested": [{field: sensitive_value, "event_count": 2}]
    }}
    result = validate_and_redact_jsonl(json.dumps(original))
    fields = result.records[0]["observation"]["nested"][0]
    assert fields[field] == "[REDACTED]"
    assert fields["event_count"] == 2
    assert sensitive_value not in result.redacted_jsonl
    assert result.redaction_count == 1


def test_trace_redaction_of_extended_pii_stays_deterministic_and_keeps_evaluation_fields():
    import hashlib
    source = json.dumps({
        "case_key": "case-1",
        "event": "graded",
        "latency_ms": 12,
        "customer": {
            "billingAddress": "Synthetic Road 123",
            "bankAccount": 123456789,
            "result_status": "PASS"
        }
    })
    first = validate_and_redact_jsonl(source, expected_case_key="case-1")
    second = validate_and_redact_jsonl(source, expected_case_key="case-1")
    assert first.sha256 == second.sha256 == hashlib.sha256(first.redacted_jsonl.encode()).hexdigest()
    assert first.records[0]["latency_ms"] == 12
    assert first.records[0]["customer"]["result_status"] == "PASS"
    assert first.redaction_count == 2
    assert "Synthetic Road" not in first.redacted_jsonl and "123456789" not in first.redacted_jsonl

def _synthetic_check_digit_sequence():
    # Build a checksum-valid synthetic identifier without storing real data.
    prefix = "7" + "0" * 14
    def check(value):
        total = 0
        for index, char in enumerate(reversed(value)):
            digit = int(char)
            if index % 2:
                digit = digit * 2
                if digit > 9:
                    digit -= 9
            total += digit
        return total % 10 == 0
    return next(prefix + digit for digit in "0123456789" if check(prefix + digit))


def test_sensitive_numeric_id_in_neutral_trace_observations_is_redacted():
    sequence = _synthetic_check_digit_sequence()
    source = json.dumps({"case_key": "case-1", "observation": "synthetic sequence: " + sequence})
    result = validate_and_redact_jsonl(source)
    assert sequence not in result.redacted_jsonl
    assert result.records[0]["observation"] == "synthetic sequence: [REDACTED]"
    assert result.redaction_count == 1


def test_spaced_sensitive_numeric_identifier_and_dynamic_key_are_redacted():
    sequence = _synthetic_check_digit_sequence()
    formatted = " ".join(sequence[index:index + 4] for index in range(0, 16, 4))
    result = validate_and_redact_jsonl(json.dumps({"case_key": "case-1", "values": {formatted: "synthetic"}}))
    assert formatted not in result.redacted_jsonl
    assert next(iter(result.records[0]["values"])).startswith("[REDACTED_KEY_")
    assert result.redaction_count == 1


def test_nearly_identical_nonmatching_numeric_string_is_not_redacted():
    valid = _synthetic_check_digit_sequence()
    invalid = valid[:-1] + str((int(valid[-1]) + 1) % 10)
    result = validate_and_redact_jsonl(json.dumps({"case_key": "case-1", "counter": invalid}))
    assert result.records[0]["counter"] == invalid
    assert result.redaction_count == 0


@pytest.mark.parametrize("url", [
    "https://token-only@hooks.example.invalid/events",
    "postgresql://user:password@db.example.invalid/app",
    "redis://percent%40encoded@cache.example.invalid/0",
])
def test_url_userinfo_is_never_persisted_even_without_password_separator(url):
    result = validate_and_redact_jsonl(json.dumps({"case_key": "case-1", "observation": url}))
    assert result.redaction_count >= 1
    assert "[REDACTED]@" in result.redacted_jsonl
    assert url not in result.redacted_jsonl
