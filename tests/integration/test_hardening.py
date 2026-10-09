from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from agenttest_lab.domain.trace import TraceValidationError, validate_and_redact_jsonl
from agenttest_lab.infrastructure.store import TENANT, USER
from agenttest_lab.main import create_app

SECRET = "forgeworks-development-secret-32-plus"
ISSUER = "https://issuer.synthetic.invalid"
AUDIENCE = "forgeworks-api"


def headers(scope: str, tenant: str = TENANT):
    token = jwt.encode(
        {
            "sub": USER,
            "tenant_id": tenant,
            "scope": scope,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_trace_jsonl_rejects_malformed_and_redacts_secrets():
    result = validate_and_redact_jsonl(
        '{"case_key":"case-1","input":"contact alice@example.com","headers":{"Authorization":"Bearer top-secret"}}\n'
    )
    assert result.redaction_count == 2
    assert "alice@example.com" not in result.redacted_jsonl
    assert "top-secret" not in result.redacted_jsonl
    assert result.sha256 and len(result.sha256) == 64
    try:
        validate_and_redact_jsonl('{"case_key":"case-1"}\nnot-json\n')
    except TraceValidationError as error:
        assert error.code == "INVALID_JSON"
        assert error.line_number == 2
    else:
        raise AssertionError("malformed JSONL must be rejected")


def _resources(client):
    dataset = client.post("/v1/datasets", headers=headers("dataset:create"), json={"name": "golden"}).json()
    version = client.post(
        f"/v1/datasets/{dataset['id']}/versions",
        headers=headers("dataset:write"),
        json={"artifact_id": "33333333-3333-3333-3333-333333333333", "sha256": "a" * 64, "case_count": 2},
    ).json()
    build = client.post(
        "/v1/agent-builds",
        headers=headers("build:write"),
        json={"name": "candidate", "build_sha256": "b" * 64, "tool_manifest_sha256": "c" * 64, "prompt_version": "p1"},
    ).json()
    return version["id"], build["id"]


def test_grader_provenance_and_non_pass_terminal_results(tmp_path):
    app = create_app(str(tmp_path / "db.sqlite"), seed=True)
    with TestClient(app) as client:
        version_id, build_id = _resources(client)
        run = client.post(
            "/v1/evaluation-runs",
            headers=headers("evaluation:run"),
            json={
                "dataset_version_id": version_id,
                "agent_build_id": build_id,
                "grader_sha256": "d" * 64,
                "grader_config": {"threshold": 0.2, "seed": 42, "seed_source": "fixture"},
                "case_results": [
                    {"case_key": "case-1", "status": "PASS", "score": 1.0, "trace_jsonl": '{"case_key":"case-1","token":"do-not-store"}'},
                    {"case_key": "case-2", "status": "TIMEOUT"},
                ],
            },
        )
        assert run.status_code == 202
        payload = run.json()
        assert payload["status"] == "PARTIAL"
        assert payload["seed"] == 42
        assert payload["seed_source"] == "fixture"
        assert len(payload["grader_config_sha256"]) == 64
        cases = client.get(f"/v1/evaluation-runs/{payload['id']}/cases", headers=headers("evaluation:read")).json()["items"]
        assert [item["grade_status"] for item in cases] == ["PASS", "TIMEOUT"]
        assert cases[1]["score"] is None


def test_comparison_binds_versions_and_creates_export_artifact(tmp_path):
    app = create_app(str(tmp_path / "db.sqlite"), seed=True)
    with TestClient(app) as client:
        version_id, build_id = _resources(client)
        body = {"dataset_version_id": version_id, "agent_build_id": build_id, "grader_sha256": "d" * 64}
        baseline = client.post("/v1/evaluation-runs", headers=headers("evaluation:run"), json=body).json()
        candidate = client.post("/v1/evaluation-runs", headers=headers("evaluation:run"), json=body).json()
        comparison = client.post(
            f"/v1/evaluation-runs/{candidate['id']}/comparisons",
            headers=headers("evaluation:compare"),
            json={"baseline_run_id": baseline["id"], "policy_version": "deterministic-v2"},
        )
        assert comparison.status_code == 201
        replay = client.post(
            f"/v1/evaluation-runs/{candidate['id']}/comparisons",
            headers={**headers("evaluation:compare"), "Idempotency-Key": "comparison-replay-001"},
            json={"baseline_run_id": baseline["id"], "policy_version": "deterministic-v2"},
        )
        replay_again = client.post(
            f"/v1/evaluation-runs/{candidate['id']}/comparisons",
            headers={**headers("evaluation:compare"), "Idempotency-Key": "comparison-replay-001"},
            json={"baseline_run_id": baseline["id"], "policy_version": "deterministic-v2"},
        )
        assert replay.status_code == replay_again.status_code == 201
        assert replay.json() == replay_again.json()
        conflict = client.post(
            f"/v1/evaluation-runs/{candidate['id']}/comparisons",
            headers={**headers("evaluation:compare"), "Idempotency-Key": "comparison-replay-001"},
            json={"baseline_run_id": baseline["id"], "policy_version": "different-policy"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
        result = comparison.json()
        assert result["artifact_id"]
        assert result["binding"]["dataset_version_id"] == version_id
        artifact = client.get(f"/v1/artifacts/{result['artifact_id']}", headers=headers("artifact:read"))
        assert artifact.status_code == 200
        assert artifact.json()["status"] == "AVAILABLE"
        download = client.post(f"/v1/artifacts/{result['artifact_id']}/download-intents", headers=headers("artifact:download"))
        assert download.status_code == 201
        assert download.json()["object_generation"] == "synthetic-local"
        import hashlib
        transferred = client.get(download.json()['download_url'])
        assert transferred.status_code == 200
        assert hashlib.sha256(transferred.content).hexdigest() == artifact.json()['sha256']
        assert transferred.headers['cache-control'] == 'no-store'
        # A previously issued capability must not survive membership revocation.
        with app.state.store.conn() as db:
            db.execute("UPDATE memberships SET status='REVOKED' WHERE tenant_id=? AND user_id=?", (TENANT, USER))
        assert client.get(download.json()['download_url']).status_code == 403
        with app.state.store.conn() as db:
            db.execute("UPDATE memberships SET status='ACTIVE' WHERE tenant_id=? AND user_id=?", (TENANT, USER))
        from uuid import uuid4
        assert client.get(download.json()['download_url'].replace(result['artifact_id'],str(uuid4()))).status_code == 403
        with app.state.store.conn() as db:
            db.execute('UPDATE artifact_exports SET binding_json=? WHERE artifact_id=?',('{}',result['artifact_id']))
        assert client.get(download.json()['download_url']).status_code == 409

        self_compare = client.post(
            f"/v1/evaluation-runs/{candidate['id']}/comparisons",
            headers=headers("evaluation:compare"),
            json={"baseline_run_id": candidate["id"], "policy_version": "deterministic-v2"},
        )
        assert self_compare.status_code == 409
        assert self_compare.json()["code"] == "INVALID_COMPARISON_BINDING"



def test_unverified_external_artifacts_remain_quarantined(tmp_path):
    with TestClient(create_app(str(tmp_path/'db.sqlite'),seed=True)) as client:
        created=client.post('/v1/artifacts/upload-intents',headers=headers('artifact:create'),json={'kind':'dataset','filename':'synthetic.json','size_bytes':2,'sha256':'a'*64})
        assert created.status_code==201
        aid=created.json()['artifact_id']
        committed=client.post(f'/v1/artifacts/{aid}/commit',headers=headers('artifact:commit'),json={'size_bytes':2,'sha256':'a'*64,'object_generation':'declared-not-verified'})
        assert committed.status_code==200 and committed.json()['status']=='QUARANTINED'
        assert client.post(f'/v1/artifacts/{aid}/download-intents',headers=headers('artifact:download')).status_code==409
