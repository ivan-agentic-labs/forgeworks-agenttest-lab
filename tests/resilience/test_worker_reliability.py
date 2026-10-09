from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from agenttest_lab.infrastructure.store import TENANT, USER, canonical_json
from agenttest_lab.main import create_app

SECRET = "forgeworks-development-secret-32-plus"
ISSUER = "https://issuer.synthetic.invalid"
AUDIENCE = "forgeworks-api"


def headers(scope: str = "dataset:create dataset:write build:write evaluation:run evaluation:read evaluation:compare artifact:read artifact:download job:read"):
    token = jwt.encode(
        {
            "sub": USER,
            "tenant_id": TENANT,
            "scope": scope,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def resources(client: TestClient, case_count: int = 2):
    dataset = client.post("/v1/datasets", headers=headers(), json={"name": "reliability"}).json()
    version = client.post(
        f"/v1/datasets/{dataset['id']}/versions",
        headers=headers(),
        json={"artifact_id": "33333333-3333-3333-3333-333333333333", "sha256": "a" * 64, "case_count": case_count},
    ).json()
    build = client.post(
        "/v1/agent-builds",
        headers=headers(),
        json={"name": "reliability-build", "build_sha256": "b" * 64, "tool_manifest_sha256": "c" * 64, "prompt_version": "reliability-v1"},
    ).json()
    return dataset["id"], version["id"], build["id"]


def submit(client: TestClient, version_id: str, build_id: str, *, key=None, results=None, grader="d"):
    request_headers = headers()
    if key:
        request_headers["Idempotency-Key"] = key
    payload = {
        "dataset_version_id": version_id,
        "agent_build_id": build_id,
        "grader_sha256": grader * 64,
        "grader_config": {"threshold": 0.2, "seed": 7, "seed_source": "reliability-fixture"},
    }
    if results is not None:
        payload["case_results"] = results
    response = client.post("/v1/evaluation-runs", headers=request_headers, json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def test_duplicate_evaluation_is_idempotent_across_retry(tmp_path):
    app = create_app(str(tmp_path / "duplicate.sqlite"), seed=True)
    with TestClient(app) as client:
        _, version_id, build_id = resources(client)
        first = submit(client, version_id, build_id, key="retry-evaluation-001")
        second = submit(client, version_id, build_id, key="retry-evaluation-001")
        assert second["id"] == first["id"]
        assert second["job_id"] == first["job_id"]
        cases = client.get(f"/v1/evaluation-runs/{first['id']}/cases", headers=headers()).json()["items"]
        assert len(cases) == 2
        changed = client.post(
            "/v1/evaluation-runs",
            headers={**headers(), "Idempotency-Key": "retry-evaluation-001"},
            json={"dataset_version_id": version_id, "agent_build_id": build_id, "grader_sha256": "e" * 64},
        )
        assert changed.status_code == 409
        assert changed.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_comparison_rejects_mutated_or_different_immutable_dataset_version(tmp_path):
    app = create_app(str(tmp_path / "pinning.sqlite"), seed=True)
    with TestClient(app) as client:
        dataset_id, first_version, build_id = resources(client, case_count=1)
        second_version = client.post(
            f"/v1/datasets/{dataset_id}/versions",
            headers=headers(),
            json={"artifact_id": "44444444-4444-4444-4444-444444444444", "sha256": "e" * 64, "case_count": 1},
        ).json()["id"]
        baseline = submit(client, first_version, build_id, grader="d")
        candidate = submit(client, second_version, build_id, grader="e")
        response = client.post(
            f"/v1/evaluation-runs/{candidate['id']}/comparisons",
            headers=headers(),
            json={"baseline_run_id": baseline["id"], "policy_version": "reliability-v1"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "DATASET_VERSION_MISMATCH"


def test_missing_result_is_partial_and_worker_job_is_terminal_after_restart(tmp_path):
    app = create_app(str(tmp_path / "partial.sqlite"), seed=True)
    with TestClient(app) as client:
        _, version_id, build_id = resources(client, case_count=2)
        run = submit(client, version_id, build_id, results=[{"case_key": "case-1", "status": "PASS", "score": 1.0}])
        assert run["status"] == "PARTIAL"
        cases = client.get(f"/v1/evaluation-runs/{run['id']}/cases", headers=headers()).json()["items"]
        assert [(item["case_key"], item["grade_status"], item["score"]) for item in cases] == [("case-1", "PASS", 1.0), ("case-2", "MISSING", None)]
        job = client.get(f"/v1/jobs/{run['job_id']}", headers=headers()).json()
        assert job["state"] == "FAILED_TERMINAL"
        assert job["last_error_code"] == "INCOMPLETE_RESULTS"
        assert job["attempt_count"] == 1
        # A worker restart/reconciliation read cannot promote incomplete evidence to success.
        restarted = client.get(f"/v1/jobs/{run['job_id']}", headers=headers()).json()
        assert restarted == job


@pytest.mark.parametrize("status", ["TIMEOUT", "INVALID_RESULT"])
def test_timeout_and_invalid_result_remain_fail_closed(tmp_path, status):
    app = create_app(str(tmp_path / f"{status}.sqlite"), seed=True)
    with TestClient(app) as client:
        _, version_id, build_id = resources(client, case_count=1)
        baseline = submit(client, version_id, build_id)
        candidate = submit(client, version_id, build_id, results=[{"case_key": "case-1", "status": status}])
        comparison = client.post(
            f"/v1/evaluation-runs/{candidate['id']}/comparisons",
            headers=headers(),
            json={"baseline_run_id": baseline["id"], "policy_version": "reliability-v1"},
        ).json()
        assert comparison["missing_case_count"] == 1
        verdict = client.get(f"/v1/comparisons/{comparison['id']}/ci-verdict", headers=headers()).json()
        assert verdict["verdict"] == "FAIL"


def test_repeated_run_is_deterministic_for_fixed_inputs(tmp_path):
    app = create_app(str(tmp_path / "deterministic.sqlite"), seed=True)
    with TestClient(app) as client:
        _, version_id, build_id = resources(client)
        first = submit(client, version_id, build_id, grader="d")
        second = submit(client, version_id, build_id, grader="d")
        assert first["grader_config_sha256"] == second["grader_config_sha256"]
        assert first["threshold"] == second["threshold"] == 0.2
        first_cases = client.get(f"/v1/evaluation-runs/{first['id']}/cases", headers=headers()).json()["items"]
        second_cases = client.get(f"/v1/evaluation-runs/{second['id']}/cases", headers=headers()).json()["items"]
        assert [(x["case_key"], x["grade_status"], x["score"], x["trace_digest"]) for x in first_cases] == [(x["case_key"], x["grade_status"], x["score"], x["trace_digest"]) for x in second_cases]


def test_export_artifact_sha_and_size_match_immutable_export_payload(tmp_path):
    app = create_app(str(tmp_path / "export.sqlite"), seed=True)
    with TestClient(app) as client:
        _, version_id, build_id = resources(client, case_count=1)
        baseline = submit(client, version_id, build_id, grader="d")
        candidate = submit(client, version_id, build_id, grader="e")
        comparison = client.post(
            f"/v1/evaluation-runs/{candidate['id']}/comparisons",
            headers=headers(),
            json={"baseline_run_id": baseline["id"], "policy_version": "reliability-v1"},
        ).json()
        artifact = client.get(f"/v1/artifacts/{comparison['artifact_id']}", headers=headers()).json()
        with app.state.store.conn() as db:
            export = db.execute("SELECT * FROM artifact_exports WHERE artifact_id=?", (comparison["artifact_id"],)).fetchone()
        assert export is not None
        payload = export["binding_json"]
        assert json.loads(payload)["binding"]["dataset_version_id"] == version_id
        assert export["sha256"] == hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert artifact["sha256"] == export["sha256"]
        assert artifact["size_bytes"] == len(payload.encode("utf-8"))
        assert client.post(f"/v1/artifacts/{comparison['artifact_id']}/download-intents", headers=headers()).status_code == 201
