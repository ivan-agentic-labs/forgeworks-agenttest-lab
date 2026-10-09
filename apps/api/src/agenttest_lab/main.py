from __future__ import annotations
from agenttest_lab.presentation.authentication import decode_bearer, verify_session

import os
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Query
from fastapi.responses import JSONResponse, Response
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
    case_count: int = Field(ge=1, le=1000, strict=True)
    source_jsonl: str | None = Field(default=None, max_length=1_048_576)


class Build(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    build_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_version: str = Field(min_length=1)


class CaseResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_key: str = Field(min_length=1, max_length=128)
    status: str = "PASS"
    score: float | None = None
    trace_jsonl: str | None = None
    trace_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class GraderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    seed: int | None = Field(default=None, ge=-(2**63), le=2**63-1, strict=True)
    seed_source: str | None = Field(default=None, min_length=1)


class Run(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_version_id: UUID
    agent_build_id: UUID
    grader_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    grader_config: GraderConfig | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    seed: int | None = Field(default=None, ge=-(2**63), le=2**63-1, strict=True)
    case_results: list[CaseResultInput] | None = Field(default=None, max_length=1000)


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


def auth(authorization: Annotated[str | None, Header()] = None):
    return decode_bearer(authorization)


def scope(required: str, store: Store):
    def dependency(c: dict[str, Any] = Depends(auth)) -> dict[str, Any]:
        verify_session(store, c)
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
    if os.getenv("AGENTTEST_DATABASE_URL"):
        from agenttest_lab.infrastructure.postgres_store import PostgresStore
        store = PostgresStore(os.environ["AGENTTEST_DATABASE_URL"])
    else:
        if os.getenv("APP_ENV", "development") not in {"development", "test"}:
            raise ValueError("SQLite is restricted to development/test")
        store = Store(db_path or os.getenv("AGENTTEST_DB_PATH", str(ROOT / ".runtime/agenttest.db")))
    if seed:
        store.seed()
    app = FastAPI(title="AgentTest Lab MVP", version="0.2.0")
    app.state.store = store
    objects = None
    if os.getenv("S3_ENDPOINT"):
        from agenttest_lab.infrastructure.object_storage import ObjectStorage
        objects = ObjectStorage("agenttest-lab")

    @app.exception_handler(HTTPException)
    async def errors(_, error: HTTPException):
        return JSONResponse(status_code=error.status_code, content=error.detail if isinstance(error.detail, dict) else {"type": "about:blank", "title": "Request rejected", "status": error.status_code, "code": "REQUEST_REJECTED", "detail": str(error.detail), "request_id": "runtime"})

    @app.get("/v1/auth/config")
    def auth_config():
        key=os.getenv("SUPABASE_PUBLISHABLE_KEY","")
        return {"enabled":os.getenv("AUTH_MODE")=="supabase" and key.startswith("sb_publishable_"), "supabase_url":os.getenv("SUPABASE_URL",""), "publishable_key":key if key.startswith("sb_publishable_") else "", "product":"agenttest-lab", "environment":os.getenv("APP_ENV","development")}

    @app.get("/readyz")
    def ready():
        from agenttest_lab.presentation.authentication import readiness
        return readiness(store)

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "agenttest-lab"}

    @app.post("/v1/datasets", status_code=201)
    def dataset(body: Dataset, c=Depends(scope("dataset:create", store))):
        did = store.dataset(c["tenant_id"], body.name, c["sub"])
        return {"id": did, "status": "ACTIVE", "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "name": body.name, "owner_id": c["sub"], "latest_version": 0}

    @app.post("/v1/datasets/{did}/versions", status_code=201)
    def version(did: UUID, body: Version, c=Depends(scope("dataset:write", store))):
        source_jsonl = body.source_jsonl
        if source_jsonl is None and objects:
            artifact = store.artifact(c["tenant_id"], str(body.artifact_id))
            if not artifact or artifact["status"] != "AVAILABLE" or artifact["kind"] != "dataset":
                reject(409, "DATASET_SOURCE_REQUIRED", "A committed dataset artifact is required")
            if artifact["sha256"] != body.sha256:
                reject(409, "DATASET_SOURCE_INVALID", "Dataset digest differs from uploaded artifact")
            try:
                source_jsonl = objects.read(c["tenant_id"], str(body.artifact_id), artifact["object_generation"], artifact["sha256"], artifact["size_bytes"]).decode("utf-8")
            except UnicodeDecodeError:
                reject(422, "DATASET_SOURCE_INVALID", "Dataset source must be UTF-8")
        try:
            vid = store.version(c["tenant_id"], str(did), body.sha256, body.case_count, str(body.artifact_id), source_jsonl)
        except StoreError as error:
            handle_store_error(error)
        with store.conn(c["tenant_id"]) as db:
            version = db.execute("SELECT * FROM versions WHERE tenant_id=? AND id=?", (c["tenant_id"], vid)).fetchone()
        return {"id": vid, "status": "IMMUTABLE", "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "dataset_id": str(did), "version_number": version["version_number"], "sha256": body.sha256, "case_count": body.case_count}

    @app.post("/v1/agent-builds", status_code=201)
    def build(body: Build, c=Depends(scope("build:write", store))):
        bid = store.build(c["tenant_id"], body.name, body.build_sha256, body.tool_manifest_sha256, body.prompt_version)
        return {"id": bid, "status": "REGISTERED", "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "name": body.name, "build_sha256": body.build_sha256, "tool_manifest_sha256": body.tool_manifest_sha256, "prompt_version": body.prompt_version}

    @app.post("/v1/evaluation-runs", status_code=202)
    def run(body: Run, c=Depends(scope("evaluation:run", store)), idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None):
        config = body.grader_config.model_dump(exclude_none=True) if body.grader_config else {}
        if body.threshold is not None:
            config["threshold"] = body.threshold
        if body.seed is not None:
            config["seed"] = body.seed
        try:
            row = store.run(c["tenant_id"], str(body.dataset_version_id), str(body.agent_build_id), body.grader_sha256, config, [item.model_dump(exclude_none=True) for item in body.case_results] if body.case_results is not None else None, idempotency_key=idempotency_key)
        except StoreError as error:
            handle_store_error(error)
        return {"id": row["id"], "status": row["status"], "created_at": row["created_at"], "dataset_version_id": row["version_id"], "agent_build_id": row["build_id"], "grader_sha256": row["grader_sha"], "grader_config_sha256": row["grader_config_sha"], "threshold": row["threshold"], "seed": row["seed"], "seed_source": row["seed_source"], "job_id": row["job_id"]}

    @app.get("/v1/evaluation-runs/{rid}/cases")
    def cases(rid: UUID, c=Depends(scope("evaluation:read", store))):
        items = [{"id": x["id"], "run_id": x["run_id"], "case_key": x["case_key"], "grade_status": x["grade_status"], "score": x["score"], "grader_sha256": x["grader_sha"], "trace_digest": x["trace_digest"], "error_code": x["error_code"]} for x in store.cases(c["tenant_id"], str(rid))]
        return {"items": items, "next_cursor": None, "has_more": False}

    @app.post("/v1/evaluation-runs/{rid}/comparisons", status_code=201)
    def compare(rid: UUID, body: Compare, c=Depends(scope("evaluation:compare", store)), idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None):
        try:
            row = store.compare(c["tenant_id"], str(rid), str(body.baseline_run_id), body.policy_version, body.threshold, idempotency_key=idempotency_key)
        except StoreError as error:
            handle_store_error(error)
        return {"id": row["id"], "status": "COMPUTED", "created_at": row["created_at"], "baseline_run_id": row["baseline_id"], "candidate_run_id": row["candidate_id"], "paired_case_count": row["paired"], "missing_case_count": row["missing"], "delta_score": row["delta"], "policy_version": row["policy"], "threshold": row["threshold"], "artifact_id": row["artifact_id"], "binding": {"dataset_version_id": row["baseline_version_id"], "baseline_build_id": row["baseline_build_id"], "candidate_build_id": row["candidate_build_id"], "baseline_grader_sha256": row["baseline_grader_sha"], "candidate_grader_sha256": row["candidate_grader_sha"], "baseline_grader_config_sha256": row["baseline_config_sha"], "candidate_grader_config_sha256": row["candidate_config_sha"]}}

    @app.get("/v1/comparisons/{cid}/ci-verdict")
    def verdict(cid: UUID, c=Depends(scope("evaluation:read", store))):
        row = store.comparison(c["tenant_id"], str(cid))
        if not row:
            reject(404, "RESOURCE_NOT_FOUND", "Comparison is not visible")
        from agenttest_lab.infrastructure.verdict_signing import sign_export
        with store.conn(c["tenant_id"]) as db:
            export = db.execute("SELECT binding_json FROM artifact_exports WHERE tenant_id=? AND comparison_id=? AND kind='ci-verdict'", (c["tenant_id"], row["id"])).fetchone()
        if not export:
            reject(409, "VERDICT_EXPORT_MISSING", "Immutable verdict export is unavailable")
        signature = sign_export(export["binding_json"], row["artifact_sha"])
        return {"id": row["id"], "status": "SIGNED", "created_at": row["created_at"], "comparison_id": row["id"], "verdict": row["verdict"], "policy_version": row["policy"], "signed_artifact_sha256": row["artifact_sha"], "artifact_id": row["artifact_id"], "binding": {"dataset_version_id": row["baseline_version_id"], "baseline_run_id": row["baseline_id"], "candidate_run_id": row["candidate_id"], "threshold": row["threshold"]}, **signature}

    @app.post("/v1/artifacts/upload-intents", status_code=201)
    def upload_intent(body: UploadIntentRequest, c=Depends(scope("artifact:create", store))):
        if objects is None and os.getenv("APP_ENV", "development") not in {"development", "test"}:
            reject(503, "EXTERNAL_STORAGE_REQUIRED", "An external artifact upload backend is required")
        if objects and (body.kind != "dataset" or body.size_bytes > objects.max_bytes):
            reject(422, "ARTIFACT_TYPE_UNSUPPORTED", "Only dataset artifacts up to 1 MiB are supported")
        row = store.artifact_intent(c["tenant_id"], body.kind, body.filename, body.size_bytes, body.sha256, body.declared_media_type)
        if objects:
            from agenttest_lab.infrastructure.artifact_downloads import signing_secret
            expiry = int(datetime.now(timezone.utc).timestamp()) + 300
            claims = {"iss":"agenttest-artifacts", "aud":"artifact-upload", "sub":row["id"], "tenant_id":c["tenant_id"], "actor":c["sub"], "exp":expiry, "sha256":row["sha256"], "session_id":c.get("session_id")}
            token = jwt.encode(claims, signing_secret(), algorithm="HS256")
            return {"artifact_id":row["id"], "status":row["status"], "upload_url":f"/v1/artifact-transfers/{row['id']}?token={token}", "expires_at":datetime.fromtimestamp(expiry,timezone.utc).isoformat(), "required_headers":{"Content-Type":"application/x-ndjson"}}
        return {"artifact_id": row["id"], "status": row["status"], "upload_url": f"https://storage.invalid/upload/{row['id']}", "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"), "required_headers": {"x-artifact-sha256": row["sha256"]}}

    @app.post("/v1/artifacts/{artifact_id}/commit", status_code=200)
    def commit_artifact(artifact_id: UUID, body: CommitUploadRequest, c=Depends(scope("artifact:commit", store))):
        if objects is None and os.getenv("APP_ENV", "development") not in {"development", "test"}:
            reject(503, "EXTERNAL_STORAGE_REQUIRED", "An external artifact upload backend is required")
        if objects:
            intent = store.artifact(c["tenant_id"], str(artifact_id))
            if not intent:
                reject(404, "RESOURCE_NOT_FOUND", "Artifact is not visible")
            if body.sha256 != intent["sha256"] or body.size_bytes != intent["size_bytes"]:
                reject(409, "ARTIFACT_INTEGRITY_MISMATCH", "Committed metadata differs from the upload intent")
            source = objects.read(c["tenant_id"], str(artifact_id), body.object_generation, body.sha256, body.size_bytes)
            from agenttest_lab.domain.dataset import parse_dataset
            try:
                text = source.decode("utf-8")
                count = len([line for line in text.splitlines() if line.strip()])
                parse_dataset(text, body.sha256, count)
            except (ValueError, UnicodeError):
                reject(422, "DATASET_SOURCE_INVALID", "Uploaded dataset failed JSONL validation")
        try:
            row = store.artifact_commit(c["tenant_id"], str(artifact_id), body.sha256, body.size_bytes, body.object_generation)
        except StoreError as error:
            handle_store_error(error)
        if objects:
            with store.conn(c["tenant_id"]) as db:
                db.execute("UPDATE artifacts SET status='AVAILABLE' WHERE tenant_id=? AND id=? AND status='QUARANTINED' AND object_generation=?", (c["tenant_id"], str(artifact_id), body.object_generation))
            row = store.artifact(c["tenant_id"], str(artifact_id))
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
        export = store.export(c["tenant_id"], str(artifact_id))
        if not export:
            if not objects or row["kind"] != "dataset":
                reject(409, "ARTIFACT_BYTES_UNAVAILABLE", "Persisted artifact bytes are unavailable")
            objects.read(c["tenant_id"], str(artifact_id), row["object_generation"], row["sha256"], row["size_bytes"])
        from agenttest_lab.infrastructure.artifact_downloads import issue_download
        token, expiry = issue_download(c["tenant_id"], c["sub"], str(artifact_id), row["sha256"])
        return {"artifact_id": row["id"], "download_url": f"/v1/artifact-transfers/{row['id']}?token={token}", "expires_at": datetime.fromtimestamp(expiry,timezone.utc).isoformat().replace("+00:00", "Z"), "object_generation": row["object_generation"]}

    @app.put("/v1/artifact-transfers/{artifact_id}", status_code=201)
    async def upload_dataset(artifact_id: UUID, request: Request, token: str = Query(max_length=4096)):
        if not objects:
            reject(503, "EXTERNAL_STORAGE_REQUIRED", "Artifact upload backend is unavailable")
        from agenttest_lab.infrastructure.artifact_downloads import signing_secret
        try:
            claims = jwt.decode(token, signing_secret(), algorithms=["HS256"], issuer="agenttest-artifacts", audience="artifact-upload", options={"require":["exp","sub","tenant_id","actor","sha256"]})
            if claims["sub"] != str(artifact_id):
                raise jwt.InvalidTokenError("Wrong artifact")
            UUID(claims["tenant_id"]); UUID(claims["actor"])
        except (jwt.PyJWTError, ValueError):
            reject(403, "INVALID_ARTIFACT_CAPABILITY", "Upload capability is invalid or expired")
        if not store.member(claims["tenant_id"], claims["actor"]):
            reject(403, "MEMBERSHIP_REVOKED", "Upload capability owner is inactive")
        if claims.get("session_id") and not store.session_active(claims["tenant_id"], claims["actor"], claims["session_id"]):
            reject(403, "SESSION_REVOKED", "Upload capability session is inactive")
        row = store.artifact(claims["tenant_id"], str(artifact_id))
        if not row or row["status"] != "INTENT_ISSUED" or row["sha256"] != claims["sha256"]:
            reject(409, "ARTIFACT_NOT_PENDING", "Artifact is not pending upload")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > min(row["size_bytes"],objects.max_bytes):
                reject(413, "ARTIFACT_TOO_LARGE", "Upload exceeds declared size")
        result = objects.put(claims["tenant_id"], str(artifact_id), bytes(body), row["sha256"], row["size_bytes"])
        return {"artifact_id":str(artifact_id),"object_generation":result["generation"],"sha256":result["sha256"],"size_bytes":result["size"]}

    @app.get("/v1/artifact-transfers/{artifact_id}")
    def transfer_artifact(artifact_id: UUID, token: str):
        from agenttest_lab.infrastructure.artifact_downloads import verify_download
        claims = verify_download(token, str(artifact_id))
        if not store.member(claims["tenant_id"], claims["actor"]):
            raise HTTPException(status_code=403, detail={"code":"MEMBERSHIP_REVOKED", "detail":"Artifact capability owner is no longer an active member"})
        export = store.export(claims["tenant_id"], str(artifact_id))
        artifact = store.artifact(claims["tenant_id"], str(artifact_id))
        if not artifact or artifact["status"] != "AVAILABLE":
            reject(409, "ARTIFACT_BYTES_UNAVAILABLE", "Persisted artifact bytes are unavailable")
        if not export:
            if not objects or artifact["kind"] != "dataset" or artifact["sha256"] != claims["sha256"]:
                reject(409, "ARTIFACT_BYTES_UNAVAILABLE", "Persisted artifact bytes are unavailable")
            body = objects.read(claims["tenant_id"], str(artifact_id), artifact["object_generation"], artifact["sha256"], artifact["size_bytes"])
            return Response(body,media_type="application/x-ndjson",headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff","Content-Disposition":"attachment"})
        body = export["binding_json"].encode('utf-8')
        if hashlib.sha256(body).hexdigest() != claims["sha256"] or export["sha256"] != claims["sha256"] or artifact["sha256"] != claims["sha256"]:
            reject(409, "ARTIFACT_INTEGRITY_FAILURE", "Persisted export bytes do not match the signed digest")
        return Response(body,media_type='application/json',headers={'Content-Disposition':'attachment','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'})

    @app.get("/v1/jobs/{jid}")
    def job(jid: UUID, c=Depends(scope("job:read", store))):
        with store.conn(c["tenant_id"]) as db:
            row = db.execute("SELECT * FROM runs WHERE tenant_id=? AND job_id=?", (c["tenant_id"], str(jid))).fetchone()
        if not row:
            reject(404, "RESOURCE_NOT_FOUND", "Job is not visible")
        return {"id": row["job_id"], "kind": "evaluation", "state": "SUCCEEDED" if row["status"] == "SUCCEEDED" else "FAILED_TERMINAL" if row["status"] == "PARTIAL" else row["status"], "created_at": row["created_at"], "state_version": 1, "attempt_count": 1, "last_error_code": None if row["status"] == "SUCCEEDED" else "INCOMPLETE_RESULTS"}

    web_dir = ROOT / "apps" / "web"
    if web_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(web_dir), html=True), name="web-console")

    @app.get("/", include_in_schema=False)
    def home():
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/ui/",status_code=307)

    return app


app = create_app(seed=os.getenv("AGENTTEST_SEED_FIXTURE", "0") == "1")

