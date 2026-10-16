from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from agenttest_lab.infrastructure.store import TENANT, USER
from agenttest_lab.main import create_app

SECRET = "forgeworks-development-secret-32-plus"
ISSUER = "https://issuer.synthetic.invalid"
AUDIENCE = "forgeworks-api"
ROOT = Path(__file__).resolve().parents[2]


def headers(scope: str = "dataset:create dataset:write build:write evaluation:run evaluation:read evaluation:compare artifact:read artifact:download"):
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


def create_resources(client: TestClient, case_count: int = 2):
    dataset = client.post("/v1/datasets", headers=headers(), json={"name": "e2e-golden"})
    assert dataset.status_code == 201, dataset.text
    version = client.post(
        f"/v1/datasets/{dataset.json()['id']}/versions",
        headers=headers(),
        json={"artifact_id": "33333333-3333-3333-3333-333333333333", "sha256": "a" * 64, "case_count": case_count},
    )
    assert version.status_code == 201, version.text
    build = client.post(
        "/v1/agent-builds",
        headers=headers(),
        json={"name": "e2e-build", "build_sha256": "b" * 64, "tool_manifest_sha256": "c" * 64, "prompt_version": "e2e-v1"},
    )
    assert build.status_code == 201, build.text
    return version.json()["id"], build.json()["id"]


def run(client: TestClient, version_id: str, build_id: str, grader: str = "d", results=None, key: str | None = None):
    request_headers = headers()
    if key:
        request_headers["Idempotency-Key"] = key
    response = client.post(
        "/v1/evaluation-runs",
        headers=request_headers,
        json={
            "dataset_version_id": version_id,
            "agent_build_id": build_id,
            "grader_sha256": grader * 64,
            "grader_config": {"threshold": 0.2, "seed": 42, "seed_source": "e2e-fixture"},
            **({"case_results": results} if results is not None else {}),
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_full_fastapi_static_console_flow_reaches_signed_ci_verdict(tmp_path):
    app = create_app(str(tmp_path / "e2e.sqlite"), seed=True)
    with TestClient(app) as client:
        ui = client.get("/ui/")
        assert ui.status_code == 200
        assert "Run evaluation flow" in ui.text
        assert "Fail-closed policy" in ui.text
        assert "dataset_version_id" in (ROOT / "apps/web/app.js").read_text(encoding="utf-8")

        version_id, build_id = create_resources(client)
        baseline = run(client, version_id, build_id, grader="d")
        candidate = run(client, version_id, build_id, grader="e")

        baseline_cases = client.get(f"/v1/evaluation-runs/{baseline['id']}/cases", headers=headers())
        candidate_cases = client.get(f"/v1/evaluation-runs/{candidate['id']}/cases", headers=headers())
        assert baseline_cases.status_code == candidate_cases.status_code == 200
        assert [case["grade_status"] for case in baseline_cases.json()["items"]] == ["PASS", "PASS"]
        assert [case["grade_status"] for case in candidate_cases.json()["items"]] == ["PASS", "PASS"]

        comparison = client.post(
            f"/v1/evaluation-runs/{candidate['id']}/comparisons",
            headers=headers(),
            json={"baseline_run_id": baseline["id"], "policy_version": "e2e-v1", "threshold": 0.2},
        )
        assert comparison.status_code == 201, comparison.text
        comparison_body = comparison.json()
        assert comparison_body["binding"]["dataset_version_id"] == version_id

        verdict = client.get(f"/v1/comparisons/{comparison_body['id']}/ci-verdict", headers=headers())
        assert verdict.status_code == 200
        verdict_body = verdict.json()
        assert verdict_body["verdict"] == "PASS"
        assert len(verdict_body["signed_artifact_sha256"]) == 64
        assert verdict_body["artifact_id"] == comparison_body["artifact_id"]


@pytest.mark.parametrize("terminal", ["MISSING", "TIMEOUT", "INVALID_RESULT"])
def test_static_console_flow_is_fail_closed_for_terminal_case_results(tmp_path, terminal):
    app = create_app(str(tmp_path / f"{terminal}.sqlite"), seed=True)
    with TestClient(app) as client:
        version_id, build_id = create_resources(client, case_count=1)
        baseline = run(client, version_id, build_id, grader="d")
        candidate = run(
            client,
            version_id,
            build_id,
            grader="e",
            results=[{"case_key": "case-1", "status": terminal}],
        )
        candidate_cases = client.get(f"/v1/evaluation-runs/{candidate['id']}/cases", headers=headers()).json()["items"]
        assert candidate_cases[0]["grade_status"] == terminal
        comparison = client.post(
            f"/v1/evaluation-runs/{candidate['id']}/comparisons",
            headers=headers(),
            json={"baseline_run_id": baseline["id"], "policy_version": "e2e-v1"},
        )
        assert comparison.status_code == 201
        body = comparison.json()
        assert body["missing_case_count"] >= 1
        verdict = client.get(f"/v1/comparisons/{body['id']}/ci-verdict", headers=headers()).json()
        assert verdict["verdict"] == "FAIL"
        javascript = (ROOT / "apps/web/app.js").read_text(encoding="utf-8")
        assert f'"{terminal}"' in javascript
        assert "A pass is not possible" in javascript


def test_static_console_flow_blocks_missing_response_fields(tmp_path):
    javascript = (ROOT / "apps/web/app.js").read_text(encoding="utf-8")
    assert "Decision blocked fail-closed" in javascript
    assert "No PASS is emitted when evidence is missing" in javascript
    assert "/v1/evaluation-runs" in javascript
    assert "/cases" in javascript
    assert "/comparisons/" in javascript
    assert "/ci-verdict" in javascript

def test_static_console_labels_fixture_pass_as_unverified():
    # Statuses entered through the console are not observations from a running agent.
    html = (ROOT / "apps/web/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "apps/web/app.js").read_text(encoding="utf-8")
    assert "Fixture-only result source:" in html
    assert "FIXTURE PASS / NOT VERIFIED" in javascript
    assert "does not execute an agent" in javascript
    assert 'state: "pass", label: "PASS"' not in javascript
