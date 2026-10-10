#!/usr/bin/env python3
"""Read-only offline CI gate. 0=verified PASS; 2=verified FAIL; 1=invalid."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api/src"))
from agenttest_lab.domain.verdict_verification import MAX_BYTES, VerdictVerificationError, strict_document, verify_verdict


def bounded_file(path, limit):
    with Path(path).open("rb") as source:
        content = source.read(limit + 1)
    if len(content) > limit: raise VerdictVerificationError("INPUT_BUDGET_EXCEEDED")
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--public-key", required=True, help="Trusted PEM key from CI configuration")
    parser.add_argument("--expected-binding", required=True, help="Independently pinned binding JSON from CI configuration")
    args = parser.parse_args()
    try:
        result = verify_verdict(strict_document(bounded_file(args.envelope, MAX_BYTES * 2)), bounded_file(args.public_key, 4096), strict_document(bounded_file(args.expected_binding, MAX_BYTES)))
    except (OSError, VerdictVerificationError) as error:
        print(json.dumps({"verified": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps({"verified": True, "verdict": result["verdict"]}))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__": raise SystemExit(main())
