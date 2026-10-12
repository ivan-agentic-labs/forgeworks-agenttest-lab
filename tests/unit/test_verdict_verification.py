"""Synthetic keys and independently configured bindings for the offline CI gate."""
import base64
import hashlib
import json
from copy import deepcopy
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from agenttest_lab.domain.verdict_verification import REQUIRED_BINDINGS, VerdictVerificationError, strict_document, verify_verdict


@pytest.fixture
def signed():
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    binding = {name: "synthetic-" + name for name in REQUIRED_BINDINGS - {"threshold"}}
    binding["threshold"] = 0.2
    document = {"binding": deepcopy(binding), "paired": 1, "missing": 0, "delta": 0.0, "verdict": "PASS"}
    def sign(doc):
        raw = json.dumps(doc, sort_keys=True, separators=(",", ":"))
        return {"signature_algorithm": "Ed25519", "signing_key_id": hashlib.sha256(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).hexdigest(), "signature": base64.urlsafe_b64encode(key.sign(raw.encode())).decode(), "signed_payload": raw, "signed_artifact_sha256": hashlib.sha256(raw.encode()).hexdigest(), "verdict": doc["verdict"]}
    return public, binding, document, sign


def test_valid_pass(signed):
    public, binding, doc, sign = signed
    assert verify_verdict(sign(doc), public, binding) == doc


@pytest.mark.parametrize("field,value", [("verdict", "FAIL"), ("signed_payload", "{}"), ("signed_artifact_sha256", "0" * 64), ("signature_algorithm", "HS256"), ("signing_key_id", "0" * 64), ("signature", "A" * 88)])
def test_tampered_envelope_rejected(signed, field, value):
    public, binding, doc, sign = signed
    envelope = sign(doc)
    envelope[field] = value
    with pytest.raises(VerdictVerificationError): verify_verdict(envelope, public, binding)


@pytest.mark.parametrize("field", sorted(REQUIRED_BINDINGS))
def test_independent_binding_prevents_replay(signed, field):
    public, binding, doc, sign = signed
    binding[field] = 0.5 if field == "threshold" else "another-" + field
    with pytest.raises(VerdictVerificationError, match="VERDICT_BINDING_MISMATCH"):
        verify_verdict(sign(doc), public, binding)


def test_untrusted_signing_key_rejected(signed):
    _, binding, doc, sign = signed
    other = Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    with pytest.raises(VerdictVerificationError, match="VERDICT_KEY_ID_MISMATCH"):
        verify_verdict(sign(doc), other, binding)


def test_incomplete_binding_rejected(signed):
    public, _, doc, sign = signed
    with pytest.raises(VerdictVerificationError, match="EXPECTED_BINDING_INCOMPLETE"):
        verify_verdict(sign(doc), public, {})


@pytest.mark.parametrize("changes", [{"missing": 1}, {"delta": -0.3}, {"paired": 0}, {"delta": float("inf")}, {"paired": True}])
def test_signed_inconsistent_pass_rejected(signed, changes):
    public, binding, doc, sign = signed
    doc.update(changes)
    with pytest.raises(VerdictVerificationError): verify_verdict(sign(doc), public, binding)


def test_verified_fail_remains_fail(signed):
    public, binding, doc, sign = signed
    doc.update(verdict="FAIL", delta=-0.3)
    assert verify_verdict(sign(doc), public, binding)["verdict"] == "FAIL"


@pytest.mark.parametrize("raw", ['{"verdict":"FAIL","verdict":"PASS"}', '{"value":NaN}', '[]', '{"text":"\\ud800"}'])
def test_strict_json_input(raw):
    with pytest.raises(VerdictVerificationError): strict_document(raw)


@pytest.mark.parametrize("verdict,expected_exit", [("PASS", 0), ("FAIL", 2)])
def test_cli_exit_code(signed, tmp_path, verdict, expected_exit):
    public, binding, doc, sign = signed
    doc["verdict"] = verdict
    envelope, trusted_key, expectation = [tmp_path / name for name in ("envelope.json", "public.pem", "expected.json")]
    envelope.write_text(json.dumps(sign(doc)))
    trusted_key.write_bytes(public)
    expectation.write_text(json.dumps(binding))
    script = Path(__file__).resolve().parents[2] / "scripts/verify_ci_verdict.py"
    result = subprocess.run([sys.executable, str(script), "--envelope", str(envelope), "--public-key", str(trusted_key), "--expected-binding", str(expectation)], capture_output=True, text=True)
    assert result.returncode == expected_exit, result.stderr
    assert json.loads(result.stdout) == {"verified": True, "verdict": verdict}


def test_noncanonical_base64_signature_spelling_is_rejected(signed):
    public, binding, doc, sign = signed
    envelope = sign(doc)
    original = envelope["signature"]
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    # A 64-byte Ed25519 signature ends in two '=' padding symbols. The
    # unused low 4 bits of the final encoded data symbol must be zero.
    index = alphabet.index(original[-3])
    changed = alphabet[(index & 0x30) | 1]
    envelope["signature"] = original[:-3] + changed + original[-2:]
    assert envelope["signature"] != original
    assert base64.urlsafe_b64decode(envelope["signature"]) == base64.urlsafe_b64decode(original)
    with pytest.raises(VerdictVerificationError, match="VERDICT_SIGNATURE_NONCANONICAL"):
        verify_verdict(envelope, public, binding)



@pytest.mark.parametrize("regression_count", [None, -1, 1, True, 1.0])
def test_strict_signed_verdict_cannot_claim_pass_with_unproven_or_regressed_cases(signed, regression_count):
    public, binding, doc, sign = signed
    binding["policy_version"] = "strict-exact-no-regression-v1"
    doc["binding"] = deepcopy(binding)
    if regression_count is not None:
        doc["regressed_case_count"] = regression_count
    with pytest.raises(VerdictVerificationError, match="VERDICT_POLICY_INCONSISTENT"):
        verify_verdict(sign(doc), public, binding)


def test_strict_signed_fail_with_one_regression_remains_verifiable(signed):
    public, binding, doc, sign = signed
    binding["policy_version"] = "strict-exact-no-regression-v1"
    doc["binding"] = deepcopy(binding)
    doc["regressed_case_count"] = 1
    doc["verdict"] = "FAIL"
    assert verify_verdict(sign(doc), public, binding)["regressed_case_count"] == 1


def test_strict_signed_pass_requires_zero_regressions(signed):
    public, binding, doc, sign = signed
    binding["policy_version"] = "strict-exact-no-regression-v1"
    doc["binding"] = deepcopy(binding)
    doc["regressed_case_count"] = 0
    assert verify_verdict(sign(doc), public, binding)["verdict"] == "PASS"
