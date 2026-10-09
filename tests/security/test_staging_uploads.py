"""Staging cannot advertise placeholder storage or commit unchecked metadata."""
from fastapi.testclient import TestClient
from agenttest_lab.main import create_app, auth
from agenttest_lab.infrastructure.store import TENANT, USER


def test_staging_upload_and_commit_require_real_backend(tmp_path, monkeypatch):
    app = create_app(str(tmp_path / "uploads.db"), seed=True)
    app.dependency_overrides[auth] = lambda: {"tenant_id": TENANT, "sub": USER, "scope": "artifact:create artifact:commit"}
    monkeypatch.setenv("APP_ENV", "staging")
    with TestClient(app) as client:
        intent = client.post("/v1/artifacts/upload-intents", json={"kind": "dataset", "filename": "synthetic.jsonl", "size_bytes": 1, "sha256": "a" * 64})
        assert intent.status_code == 503
        assert intent.json()["code"] == "EXTERNAL_STORAGE_REQUIRED"
        assert "upload_url" not in intent.json()
        commit = client.post("/v1/artifacts/33333333-3333-3333-3333-333333333333/commit", json={"sha256": "a" * 64, "size_bytes": 1, "object_generation": "unverified"})
        assert commit.status_code == 503
        assert commit.json()["code"] == "EXTERNAL_STORAGE_REQUIRED"
