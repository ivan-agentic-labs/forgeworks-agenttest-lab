from __future__ import annotations

import hashlib
import json

from agenttest_lab.domain.exact_grader import GRADER_SHA256, MODE
from agenttest_lab.infrastructure.store import Store, TENANT, USER


def test_missing_baseline_pair_is_coverage_gap_and_fails_comparison(tmp_path):
    """A candidate omitting one dataset case must not receive a pass verdict."""
    store = Store(str(tmp_path / "ev-t02.sqlite"))
    store.seed()
    source = "\n".join(
        json.dumps(
            {"case_key": key, "input": {"fixture": key}, "expected": key.upper()},
            separators=(",", ":"),
        )
        for key in ("case-1", "case-2")
    ) + "\n"
    dataset = store.dataset(TENANT, "EV-T02 synthetic paired corpus", USER)
    version = store.version(
        TENANT,
        dataset,
        hashlib.sha256(source.encode("utf-8")).hexdigest(),
        2,
        source_jsonl=source,
    )
    build = store.build(TENANT, "EV-T02 synthetic build", "b" * 64, "c" * 64, "ev-t02")

    baseline = store.run(
        TENANT,
        version,
        build,
        GRADER_SHA256,
        {"mode": MODE},
        [
            {"case_key": "case-1", "observed_output": "CASE-1"},
            {"case_key": "case-2", "observed_output": "CASE-2"},
        ],
    )
    candidate = store.run(
        TENANT,
        version,
        build,
        GRADER_SHA256,
        {"mode": MODE},
        [{"case_key": "case-1", "observed_output": "CASE-1"}],
    )

    candidate_cases = {row["case_key"]: row for row in store.cases(TENANT, candidate["id"])}
    assert candidate_cases["case-2"]["grade_status"] == "MISSING"
    comparison = store.compare(
        TENANT,
        candidate["id"],
        baseline["id"],
        "strict-exact-no-regression-v1",
    )
    assert comparison["paired"] == 2
    assert comparison["missing"] == 1
    assert comparison["verdict"] == "FAIL"

    export = store.export(TENANT, comparison["artifact_id"])
    assert export is not None
    assert json.loads(export["binding_json"])["verdict"] == "FAIL"
