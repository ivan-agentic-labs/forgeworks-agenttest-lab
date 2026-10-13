import hashlib
import json

from fastapi.testclient import TestClient
from agenttest_lab.infrastructure.store import Store, TENANT, USER
from agenttest_lab.main import create_app
from test_agenttest_flow import h


def make_store(tmp_path, case_count):
    store = Store(str(tmp_path / "scores.sqlite"))
    store.seed()
    rows = [
        json.dumps({"case_key": f"case-{index}", "input": {}, "expected": "fixture"})
        for index in range(case_count)
    ]
    source = "\n".join(rows) + "\n"
    dataset = store.dataset(TENANT, "Synthetic score precision", USER)
    version = store.version(
        TENANT, dataset, hashlib.sha256(source.encode()).hexdigest(), case_count,
        source_jsonl=source,
    )
    build = store.build(TENANT, "Synthetic build", "b" * 64, "c" * 64, "prompt-v1")
    return store, version, build


def score_run(store, version, build, scores):
    results = [
        {"case_key": f"case-{index}", "status": "PASS", "score": score}
        for index, score in enumerate(scores)
    ]
    return store.run(TENANT, version, build, "d" * 64, results=results)


def test_external_scores_are_rounded_half_even_to_four_decimals(tmp_path):
    store, version, build = make_store(tmp_path, 5)
    run = score_run(store, version, build, [0.123456, 0.123444, 0.12345, 0.12355, -0.0])

    cases = {row["case_key"]: row for row in store.cases(TENANT, run["id"])}
    assert [cases[f"case-{index}"]["score"] for index in range(5)] == [
        0.1235, 0.1234, 0.1234, 0.1236, 0.0,
    ]
    assert run["status"] == "SUCCEEDED"


def test_http_run_exposes_the_normalized_persisted_score(tmp_path):
    source = '{"case_key":"case-0","input":{},"expected":"fixture"}\n'
    with TestClient(create_app(str(tmp_path / "http.sqlite"), seed=True)) as client:
        dataset = client.post("/v1/datasets", headers=h("dataset:create"), json={"name": "HTTP precision"})
        dataset_id = dataset.json()["id"]
        version = client.post(
            f"/v1/datasets/{dataset_id}/versions",
            headers=h("dataset:write"),
            json={
                "artifact_id": "33333333-3333-3333-3333-333333333333",
                "sha256": hashlib.sha256(source.encode()).hexdigest(),
                "case_count": 1,
                "source_jsonl": source,
            },
        )
        build = client.post(
            "/v1/agent-builds",
            headers=h("build:write"),
            json={"name": "HTTP build", "build_sha256": "b" * 64,
                  "tool_manifest_sha256": "c" * 64, "prompt_version": "p1"},
        )
        result = client.post(
            "/v1/evaluation-runs",
            headers=h("evaluation:run"),
            json={
                "dataset_version_id": version.json()["id"],
                "agent_build_id": build.json()["id"],
                "grader_sha256": "d" * 64,
                "case_results": [{"case_key": "case-0", "status": "PASS", "score": 0.314159}],
            },
        )
        assert result.status_code == 202, result.text
        cases = client.get(
            f"/v1/evaluation-runs/{result.json()['id']}/cases",
            headers=h("evaluation:read"),
        )
    assert cases.status_code == 200, cases.text
    assert cases.json()["items"][0]["score"] == 0.3142


def test_comparison_delta_rounding_does_not_weaken_threshold_decision(tmp_path):
    store, version, build = make_store(tmp_path, 2)
    baseline = score_run(store, version, build, [0.5000, 0.5000])
    positive_tie_candidate = score_run(store, version, build, [0.5001, 0.5000])
    negative_tie_candidate = score_run(store, version, build, [0.4999, 0.5000])
    increased_candidate = score_run(store, version, build, [0.5001, 0.5001])

    positive_tie = store.compare(TENANT, positive_tie_candidate["id"], baseline["id"], "precision-positive-tie")
    negative_tie = store.compare(TENANT, negative_tie_candidate["id"], baseline["id"], "precision-negative-tie", threshold=0)
    increase = store.compare(TENANT, increased_candidate["id"], baseline["id"], "precision-increase")
    assert positive_tie["delta"] == 0.0 and positive_tie["verdict"] == "PASS"
    assert negative_tie["delta"] == 0.0 and negative_tie["verdict"] == "FAIL"
    assert increase["delta"] == 0.0001

    with store.conn() as db:
        exported = db.execute(
            "SELECT binding_json FROM artifact_exports WHERE tenant_id=? AND comparison_id=?",
            (TENANT, negative_tie["id"]),
        ).fetchone()
    signed_evidence = json.loads(exported["binding_json"])
    assert signed_evidence["delta"] == 0.0 and signed_evidence["verdict"] == "FAIL"


def test_legacy_scores_are_preserved_but_normalized_for_new_comparisons(tmp_path):
    store, version, build = make_store(tmp_path, 1)
    baseline = score_run(store, version, build, [0.1234])
    candidate = score_run(store, version, build, [0.1234])
    # Simulate immutable rows written before the four-decimal rule was introduced.
    with store.conn() as db:
        db.execute("UPDATE cases SET score=? WHERE tenant_id=? AND run_id=?", (0.123449, TENANT, baseline["id"]))
        db.execute("UPDATE cases SET score=? WHERE tenant_id=? AND run_id=?", (0.123451, TENANT, candidate["id"]))

    comparison = store.compare(TENANT, candidate["id"], baseline["id"], "legacy-score-normalization")
    assert comparison["delta"] == 0.0001
    assert store.cases(TENANT, baseline["id"])[0]["score"] == 0.123449
    assert store.cases(TENANT, candidate["id"])[0]["score"] == 0.123451


def test_comparison_delta_excludes_unpaired_cases(tmp_path):
    store, version, build = make_store(tmp_path, 2)
    baseline = score_run(store, version, build, [0.5, 0.0])
    candidate = score_run(store, version, build, [0.5])
    # Older runs can lack a case row entirely; current runs store an explicit MISSING row.
    with store.conn() as db:
        db.execute(
            "DELETE FROM cases WHERE tenant_id=? AND run_id=? AND case_key=?",
            (TENANT, candidate["id"], "case-1"),
        )

    comparison = store.compare(TENANT, candidate["id"], baseline["id"], "paired-only-precision", threshold=0)
    assert comparison["missing"] == 1
    assert comparison["delta"] == 0.0
    assert comparison["verdict"] == "FAIL"
