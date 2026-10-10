"""Offline verification against a trusted key and independently pinned CI binding."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_BYTES = 65_536
REQUIRED_BINDINGS = {"dataset_version_id", "baseline_run_id", "candidate_run_id", "baseline_build_id", "candidate_build_id", "policy_version", "baseline_grader_sha256", "candidate_grader_sha256", "baseline_grader_config_sha256", "candidate_grader_config_sha256", "threshold"}


class VerdictVerificationError(ValueError):
    pass


def strict_document(raw: str | bytes) -> dict:
    try:
        if len(raw) > MAX_BYTES:
            raise VerdictVerificationError("VERDICT_BUDGET_EXCEEDED")
        if isinstance(raw, bytes): raw = raw.decode("utf-8")
        if len(raw.encode("utf-8")) > MAX_BYTES:
            raise VerdictVerificationError("VERDICT_BUDGET_EXCEEDED")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise VerdictVerificationError("DUPLICATE_JSON_KEY")
                result[key] = value
            return result
        def constant(_): raise VerdictVerificationError("NONFINITE_NUMBER")
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
        if not isinstance(value, dict): raise VerdictVerificationError("VERDICT_SCHEMA_INVALID")
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 16: raise VerdictVerificationError("VERDICT_STRUCTURE_LIMIT")
            if isinstance(item, dict):
                pending.extend((key, depth + 1) for key in item)
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list): pending.extend((child, depth + 1) for child in item)
            elif isinstance(item, float) and not math.isfinite(item): raise VerdictVerificationError("NONFINITE_NUMBER")
            elif isinstance(item, str): item.encode("utf-8")
        return value
    except VerdictVerificationError:
        raise
    except (ValueError, UnicodeError, RecursionError, TypeError, AttributeError) as error:
        raise VerdictVerificationError("VERDICT_JSON_INVALID") from error


def verify_verdict(envelope: dict, public_key_pem: bytes, expected_binding: dict) -> dict:
    """Verify exact signed bytes; never trust a key supplied by the envelope."""
    try:
        if not isinstance(envelope, dict) or envelope.get("signature_algorithm") != "Ed25519":
            raise VerdictVerificationError("VERDICT_ALGORITHM_INVALID")
        if not isinstance(expected_binding, dict) or not REQUIRED_BINDINGS <= expected_binding.keys():
            raise VerdictVerificationError("EXPECTED_BINDING_INCOMPLETE")
        for key in REQUIRED_BINDINGS - {"threshold"}:
            if not isinstance(expected_binding[key], str) or not expected_binding[key]:
                raise VerdictVerificationError("EXPECTED_BINDING_INVALID")
        if type(expected_binding["threshold"]) not in (int, float) or not math.isfinite(expected_binding["threshold"]) or not 0 <= expected_binding["threshold"] <= 1:
            raise VerdictVerificationError("EXPECTED_BINDING_INVALID")
        if not isinstance(public_key_pem, bytes) or len(public_key_pem) > 4096:
            raise VerdictVerificationError("TRUSTED_KEY_INVALID")
        public = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(public, Ed25519PublicKey): raise VerdictVerificationError("TRUSTED_KEY_INVALID")
        raw_key = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        if hashlib.sha256(raw_key).hexdigest() != envelope.get("signing_key_id"):
            raise VerdictVerificationError("VERDICT_KEY_ID_MISMATCH")
        raw = envelope["signed_payload"]
        if not isinstance(raw, str) or len(raw) > MAX_BYTES: raise VerdictVerificationError("VERDICT_BUDGET_EXCEEDED")
        payload = raw.encode("utf-8")
        if len(payload) > MAX_BYTES: raise VerdictVerificationError("VERDICT_BUDGET_EXCEEDED")
        if hashlib.sha256(payload).hexdigest() != envelope.get("signed_artifact_sha256"):
            raise VerdictVerificationError("VERDICT_DIGEST_MISMATCH")
        signature_text = envelope["signature"]
        if not isinstance(signature_text, str) or len(signature_text) != 88:
            raise VerdictVerificationError("VERDICT_SIGNATURE_INVALID")
        signature = base64.b64decode(signature_text, altchars=b"-_", validate=True)
        if len(signature) != 64: raise VerdictVerificationError("VERDICT_SIGNATURE_INVALID")
        public.verify(signature, payload)
        document = strict_document(raw)
        binding = document.get("binding")
        if not isinstance(binding, dict) or any(binding.get(key) != value or type(binding.get(key)) is bool for key, value in expected_binding.items()):
            raise VerdictVerificationError("VERDICT_BINDING_MISMATCH")
        if document.get("verdict") not in {"PASS", "FAIL"} or document["verdict"] != envelope.get("verdict"):
            raise VerdictVerificationError("VERDICT_STATUS_MISMATCH")
        if type(document.get("paired")) is not int or not 0 < document["paired"] <= 1000 or type(document.get("missing")) is not int or not 0 <= document["missing"] <= 1000:
            raise VerdictVerificationError("VERDICT_SCHEMA_INVALID")
        delta = document.get("delta")
        if type(delta) not in (int, float) or not math.isfinite(delta) or not -1 <= delta <= 1:
            raise VerdictVerificationError("VERDICT_SCHEMA_INVALID")
        if document["verdict"] == "PASS" and (document["missing"] != 0 or delta < -expected_binding["threshold"]):
            raise VerdictVerificationError("VERDICT_POLICY_INCONSISTENT")
        return document
    except VerdictVerificationError:
        raise
    except InvalidSignature as error:
        raise VerdictVerificationError("VERDICT_SIGNATURE_INVALID") from error
    except (ValueError, TypeError, KeyError, UnicodeError, UnsupportedAlgorithm, OverflowError) as error:
        raise VerdictVerificationError("VERDICT_INVALID") from error
