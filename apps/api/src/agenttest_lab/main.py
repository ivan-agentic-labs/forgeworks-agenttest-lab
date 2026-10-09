from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from agenttest_lab.infrastructure.store import Store, StoreError

ROOT = Path(__file__).resolve().parents[4]


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)


class Version(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: int = Field(ge=1)


class Build(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    build_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_version: str = Field(min_length=1)


class CaseResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_key: str = Field(min_length=1)
    status: str = "PASS"
    score: float | None = None
    trace_jsonl: str | None = None
    trace_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class GraderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    seed: int | None = None
    seed_source: str | None = Field(default=None, min_length=1)


class Run(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_version_id: UUID
    agent_build_id: UUID
    grader_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    grader_config: GraderConfig | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    seed: int | None = None
    case_results: list[CaseResultInput] | None = None


class Compare(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_run_id: UUID
    policy_version: str = Field(min_length=1)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class UploadIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    declared_media_type: str | None = None


class CommitUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)
    object_generation: str = Field(min_length=1)


def reject(status: int, code: str, detail: str) -> None:
    raise HTTPException(status_code=status, detail={"type": "about:blank", "title": "Request rejected", "status": status, "code": code, "detail": detail, "request_id": "runtime"})


def auth(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        reject(401, "UNAUTHENTICATED", "Bearer token is required")
    try:
        return jwt.decode(
            authorization[7:],
            os.getenv("DEV_AUTH_SECRET", "forgeworks-development-secret-32-plus"),
            algorithms=["HS256"],
            issuer=os.getenv("AUTH_ISSUER", "https://issuer.synthetic.invalid"),
            audience=os.getenv("AUTH_AUDIENCE", "forgeworks-api"),
        )
    except jwt.PyJWTError:
        reject(401, "INVALID_TOKEN", "Token signature, issuer, audience, or expiry is invalid")


def scope(required: str, store: Store):
    def dependency(c: dict[str, Any] = Depends(auth)) -> dict[str, Any]:
        if not c.get("tenant_id") or not c.get("sub") or not store.member(str(c["tenant_id"]), str(c["sub"])):
            reject(403, "TENANT_CONTEXT_INVALID", "Verified membership is required")
        if required not in set(str(c.get("scope", "")).split()):
            reject(403, "INSUFFICIENT_SCOPE", f"Scope {required} is required")
        return c

    return dependency


def handle_store_error(error: StoreError) -> None:
    reject(error.status, error.code, error.detail)


def iso_created(row: Any) -> str:
    return row["created_at"] or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_app(db_path: str | None = None, seed: bool = False) -> FastAPI:
    store = Store(db_path or os.getenv("AGENTTEST_DB_PATH", str(ROOT / ".runtime/agenttest.db")))
    if seed:
        store.seed()
    app = FastAPI(title="AgentTest Lab MVP", version="0.2.0")
    app.state.store = store

    @app.exception_handler(HTTPException)
    async def errors(_, error: HTTPException):
        return JSONResponse(status_code=error.status_code, content=error.detail if isinstance(error.detail, dict) else {"type": "about:blank", "title": "Request rejected", "status": error.status_code, "code": "REQUEST_REJECTED", "detail": str(error.detail), "request_id": "runtime"})

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "agenttest-lab"}

    @app.post("/v1/datasets", status_code=201)
    def dataset(body: Dataset, c=Depends(scope("dataset:create", store))):
        did = store.dataset(c["tenant_id"], body.name, c["sub"])
        return {"id": did, "status": "ACTIVE", "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "name": body.name, "owner_id": c["sub"], "latest_version": 0}

    @app.post("/v1/datasets/{did}/versions", status_code=201)
    def version(did: UUID, body: Version, c=Depends(scope("dataset:write", store))):
        try:
            vid = store.version(c["tenant_id"], str(did), body.sha256, body.case_count, str(body.artifact_id))
        except StoreError as error:
            handle_store_error(error)
        return {"id": vid, "status": "IMMUTABLE", "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "dataset_id": str(did), "version_number": 1, "sha256": body.sha256, "case_count": body.case_count}

    @app.post("/v1/agent-builds", status_code=201)
    def build(body: Build, c=Depends(scope("build:write", store))):
        bid = store.build(c["tenant_id"], body.name, body.build_sha256, body.tool_manifest_sha256, body.prompt_version)
        return {"id": bid, "status": "REGISTERED", "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "name": body.name, "build_sha256": body.build_sha256, "tool_manifest_sha256": body.tool_manifest_sha256, "prompt_version": body.prompt_version}

    @app.post("/v1/evaluation-runs", status_code=202)
    def run(body: Run, c=Depends(scope("evaluation:run", store))):
        config = body.grader_config.model_dump(exclude_none=True) if body.grader_config else {}
        if body.threshold is not None:
            config["threshold"] = body.threshold
        if body.seed is not None:
            config["seed"] = body.seed
        try:
            row = store.run(c["tenant_id"], str(body.dataset_version_id), str(body.agent_build_id), body.grader_sha256, config, [item.model_dump(exclude_none=True) for item in body.case_results] if body.case_results is not None else None)
        except StoreError as error:
            handle_store_error(error)
        return {"id": row["id"], "status": row["status"], "created_at": row["created_at"], "dataset_version_id": row["version_id"], "agent_build_id": row["build_id"], "grader_sha256": row["grader_sha"], "grader_config_sha256": row["grader_config_sha"], "threshold": row["threshold"], "seed": row["seed"], "seed_source": row["seed_source"], "job_id": row["job_id"]}

    @app.get("/v1/evaluation-runs/{rid}/cases")
    def cases(rid: UUID, c=Depends(scope("evaluation:read", store))):
        items = [{"id": x["id"], "run_id": x["run_id"], "case_key": x["case_key"], "grade_status": x["grade_status"], "score": x["score"], "grader_sha256": x["grader_sha"], "trace_digest": x["trace_digest"], "error_code": x["error_code"]} for x in store.cases(c["tenant_id"], str(rid))]
        return {"items": items, "next_cursor": None, "has_more": False}

    @app.post("/v1/evaluation-runs/{rid}/comparisons", status_code=201)
    def compare(rid: UUID, body: Compare, c=Depends(scope("evaluation:compare", store))):
        try:
            row = store.compare(c["tenant_id"], str(rid), str(body.baseline_run_id), body.policy_version, body.threshold)
        except StoreError as error:
            handle_store_error(error)
        return {"id": row["id"], "status": "COMPUTED", "created_at": row["created_at"], "baseline_run_id": row["baseline_id"], "candidate_run_id": row["candidate_id"], "paired_case_count": row["paired"], "missing_case_count": row["missing"], "delta_score": row["delta"], "policy_version": row["policy"], "threshold": row["threshold"], "artifact_id": row["artifact_id"], "binding": {"dataset_version_id": row["baseline_version_id"], "baseline_build_id": row["baseline_build_id"], "candidate_build_id": row["candidate_build_id"], "baseline_grader_sha256": row["baseline_grader_sha"], "candidate_grader_sha256": row["candidate_grader_sha"], "baseline_grader_config_sha256": row["baseline_config_sha"], "candidate_grader_config_sha256": row["candidate_config_sha"]}}

    @app.get("/v1/comparisons/{cid}/ci-verdict")
    def verdict(cid: UUID, c=Depends(scope("evaluation:read", store))):
        row = store.comparison(c["tenant_id"], str(cid))
        if not row:
            reject(404, "RESOURCE_NOT_FOUND", "Comparison is not visible")
        return {"id": row["id"], "status": "SIGNED", "created_at": row["created_at"], "comparison_id": row["id"], "verdict": row["verdict"], "policy_version": row["policy"], "signed_artifact_sha256": row["artifact_sha"], "artifact_id": row["artifact_id"], "binding": {"dataset_version_id": row["baseline_version_id"], "baseline_run_id": row["baseline_id"], "candidate_run_id": row["candidate_id"], "threshold": row["threshold"]}}

    @app.post("/v1/artifacts/upload-intents", status_code=201)
    def upload_intent(body: UploadIntentRequest, c=Depends(scope("artifact:create", store))):
        row = store.artifact_intent(c["tenant_id"], body.kind, body.filename, body.size_bytes, body.sha256, body.declared_media_type)
        return {"artifact_id": row["id"], "status": row["status"], "upload_url": f"https://storage.invalid/upload/{row['id']}", "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"), "required_headers": {"x-artifact-sha256": row["sha256"]}}

    @app.post("/v1/artifacts/{artifact_id}/commit", status_code=200)
    def commit_artifact(artifact_id: UUID, body: CommitUploadRequest, c=Depends(scope("artifact:commit", store))):
        try:
            row = store.artifact_commit(c["tenant_id"], str(artifact_id), body.sha256, body.size_bytes, body.object_generation)
        except StoreError as error:
            handle_store_error(error)
        return {"id": row["id"], "status": row["status"], "kind": row["kind"], "sha256": row["sha256"], "size_bytes": row["size_bytes"], "created_at": row["created_at"], "rejected_reason": row["rejected_reason"]}

    @app.get("/v1/artifacts/{artifact_id}")
    def get_artifact(artifact_id: UUID, c=Depends(scope("artifact:read", store))):
        row = store.artifact(c["tenant_id"], str(artifact_id))
        if not row:
            reject(404, "RESOURCE_NOT_FOUND", "Artifact is not visible")
        return {"id": row["id"], "status": row["status"], "kind": row["kind"], "sha256": row["sha256"], "size_bytes": row["size_bytes"], "created_at": row["created_at"], "rejected_reason": row["rejected_reason"]}

    @app.post("/v1/artifacts/{artifact_id}/download-intents", status_code=201)
    def download_intent(artifact_id: UUID, c=Depends(scope("artifact:download", store))):
        try:
            row = store.download_intent(c["tenant_id"], str(artifact_id))
        except StoreError as error:
            handle_store_error(error)
        return {"artifact_id": row["id"], "download_url": f"https://storage.invalid/download/{row['id']}", "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"), "object_generation": row["object_generation"]}

    @app.get("/v1/jobs/{jid}")
    def job(jid: UUID, c=Depends(scope("job:read", store))):
        with store.conn() as db:
            row = db.execute("SELECT * FROM runs WHERE tenant_id=? AND job_id=?", (c["tenant_id"], str(jid))).fetchone()
        if not row:
            reject(404, "RESOURCE_NOT_FOUND", "Job is not visible")
        return {"id": row["job_id"], "kind": "evaluation", "state": "SUCCEEDED" if row["status"] == "SUCCEEDED" else "FAILED_TERMINAL" if row["status"] == "PARTIAL" else row["status"], "created_at": row["created_at"], "state_version": 1, "attempt_count": 1, "last_error_code": None if row["status"] == "SUCCEEDED" else "INCOMPLETE_RESULTS"}

    web_dir = ROOT / "apps" / "web"
    if web_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(web_dir), html=True), name="web-console")

    return app


app = create_app(seed=os.getenv("AGENTTEST_SEED_FIXTURE", "0") == "1")
