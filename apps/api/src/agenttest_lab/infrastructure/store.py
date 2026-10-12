from __future__ import annotations

import hashlib
import os
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agenttest_lab.domain.trace import validate_and_redact_jsonl
from agenttest_lab.domain.dataset import parse_dataset
from agenttest_lab.domain.exact_grader import MODE, GRADER_SHA256, validate_output, grade

TENANT = "00000000-0000-0000-0000-000000000001"
USER = "00000000-0000-0000-0000-000000000010"
SHA256 = r"^[0-9a-f]{64}$"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class StoreError(ValueError):
    def __init__(self, code: str, detail: str, status: int = 422):
        self.code, self.detail, self.status = code, detail, status
        super().__init__(detail)


class Store:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def conn(self, tenant=None) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def init(self) -> None:
        with self.conn() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY, slug TEXT, status TEXT);
                CREATE TABLE IF NOT EXISTS memberships(tenant_id TEXT, user_id TEXT, role TEXT, status TEXT,
                    PRIMARY KEY(tenant_id,user_id));
                CREATE TABLE IF NOT EXISTS datasets(tenant_id TEXT, id TEXT, name TEXT, owner_id TEXT,
                    latest_version INTEGER, PRIMARY KEY(tenant_id,id));
                CREATE TABLE IF NOT EXISTS versions(tenant_id TEXT, id TEXT, dataset_id TEXT, version_number INTEGER,
                    sha256 TEXT, case_count INTEGER, artifact_id TEXT, created_at TEXT, PRIMARY KEY(tenant_id,id));
                CREATE TABLE IF NOT EXISTS dataset_sources(tenant_id TEXT,version_id TEXT,source_jsonl TEXT,PRIMARY KEY(tenant_id,version_id));
                CREATE TABLE IF NOT EXISTS builds(tenant_id TEXT, id TEXT, name TEXT, build_sha TEXT, tool_sha TEXT,
                    prompt_version TEXT, created_at TEXT, PRIMARY KEY(tenant_id,id));
                CREATE TABLE IF NOT EXISTS runs(tenant_id TEXT, id TEXT, version_id TEXT, build_id TEXT, grader_sha TEXT,
                    grader_config_json TEXT, grader_config_sha TEXT, threshold REAL, seed INTEGER, seed_source TEXT,
                    status TEXT, expected_case_count INTEGER, job_id TEXT, created_at TEXT, PRIMARY KEY(tenant_id,id));
                CREATE TABLE IF NOT EXISTS cases(tenant_id TEXT, id TEXT, run_id TEXT, case_key TEXT, grade_status TEXT,
                    score REAL, grader_sha TEXT, trace_digest TEXT, error_code TEXT, created_at TEXT,
                    PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,run_id,case_key));
                CREATE TABLE IF NOT EXISTS comparisons(tenant_id TEXT, id TEXT, baseline_id TEXT, candidate_id TEXT,
                    baseline_version_id TEXT, candidate_version_id TEXT, baseline_build_id TEXT, candidate_build_id TEXT,
                    baseline_grader_sha TEXT, candidate_grader_sha TEXT, baseline_config_sha TEXT, candidate_config_sha TEXT,
                    paired INTEGER, missing INTEGER, delta REAL, threshold REAL, policy TEXT, verdict TEXT,
                    artifact_sha TEXT, artifact_id TEXT, created_at TEXT, PRIMARY KEY(tenant_id,id),
                    UNIQUE(tenant_id,baseline_id,candidate_id,policy));
                CREATE TABLE IF NOT EXISTS artifacts(tenant_id TEXT, id TEXT, kind TEXT, filename TEXT, size_bytes INTEGER,
                    sha256 TEXT, declared_media_type TEXT, status TEXT, object_generation TEXT, rejected_reason TEXT,
                    created_at TEXT, PRIMARY KEY(tenant_id,id));
                CREATE TABLE IF NOT EXISTS artifact_exports(tenant_id TEXT, id TEXT, artifact_id TEXT, comparison_id TEXT,
                    kind TEXT, sha256 TEXT, binding_json TEXT, created_at TEXT, PRIMARY KEY(tenant_id,id),
                    UNIQUE(tenant_id,comparison_id,kind));
                CREATE TABLE IF NOT EXISTS idempotency_keys(tenant_id TEXT, operation TEXT, key TEXT,
                    fingerprint TEXT, resource_id TEXT, created_at TEXT,
                    PRIMARY KEY(tenant_id,operation,key));
                """
            )
            # Keep local developer databases created by the MVP readable while adding the
            # hardening columns. SQLite cannot add a NOT NULL column without a default.
            for table, name, definition in (
                ("versions", "artifact_id", "TEXT"), ("versions", "created_at", "TEXT"),
                ("builds", "created_at", "TEXT"), ("runs", "grader_config_json", "TEXT"),
                ("runs", "grader_config_sha", "TEXT"), ("runs", "threshold", "REAL"),
                ("runs", "seed", "INTEGER"), ("runs", "seed_source", "TEXT"),
                ("runs", "expected_case_count", "INTEGER"), ("cases", "error_code", "TEXT"),
                ("cases", "created_at", "TEXT"), ("comparisons", "baseline_version_id", "TEXT"),
                ("comparisons", "candidate_version_id", "TEXT"), ("comparisons", "baseline_build_id", "TEXT"),
                ("comparisons", "candidate_build_id", "TEXT"), ("comparisons", "baseline_grader_sha", "TEXT"),
                ("comparisons", "candidate_grader_sha", "TEXT"), ("comparisons", "baseline_config_sha", "TEXT"),
                ("comparisons", "candidate_config_sha", "TEXT"), ("comparisons", "threshold", "REAL"),
                ("comparisons", "artifact_id", "TEXT"), ("comparisons", "created_at", "TEXT"),
            ):
                columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                if name not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def seed(self) -> None:
        if os.getenv("APP_ENV", "development") not in {"development", "test"}:
            raise ValueError("Fixture seeding is restricted to development/test")
        self.allow_fixture_versions = True
        with self.conn() as db:
            db.execute("INSERT OR IGNORE INTO tenants VALUES(?,?,?)", (TENANT, "synthetic-demo", "ACTIVE"))
            db.execute("INSERT OR IGNORE INTO memberships VALUES(?,?,?,?)", (TENANT, USER, "editor", "ACTIVE"))

    def member_role(self, tenant: str, user: str) -> str | None:
        """Fetch role of an ACTIVE member of this exact tenant."""
        with self.conn() as db:
            row = db.execute(
                "SELECT role FROM memberships WHERE tenant_id=? AND user_id=? AND status='ACTIVE'",
                (tenant, user),
            ).fetchone()
            return str(row["role"]) if row else None

    def member(self, tenant_id: str, user_id: str) -> bool:
        with self.conn() as db:
            return db.execute(
                "SELECT 1 FROM memberships WHERE tenant_id=? AND user_id=? AND status='ACTIVE'",
                (tenant_id, user_id),
            ).fetchone() is not None

    def dataset(self, tenant_id: str, name: str, owner: str) -> str:
        dataset_id = str(uuid.uuid4())
        with self.conn() as db:
            db.execute("INSERT INTO datasets VALUES(?,?,?,?,?)", (tenant_id, dataset_id, name, owner, 0))
        return dataset_id

    def version(self, tenant_id: str, dataset_id: str, sha256: str, case_count: int, artifact_id: str | None = None, source_jsonl: str | None = None) -> str:
        if isinstance(case_count, bool) or not isinstance(case_count, int) or not 1 <= case_count <= 1000:
            raise StoreError("DATASET_BUDGET_EXCEEDED", "Dataset versions require 1 to 1000 cases")
        if source_jsonl is not None:
            try:
                parse_dataset(source_jsonl, sha256, case_count)
            except (ValueError, UnicodeError) as error:
                raise StoreError("DATASET_SOURCE_INVALID", str(error)) from error
        elif not (getattr(self, "allow_fixture_versions", False) and os.getenv("APP_ENV", "development") in {"development", "test"}):
            raise StoreError("DATASET_SOURCE_REQUIRED", "Dataset source JSONL bytes are required; metadata alone is not ingestion", 409)
        version_id = str(uuid.uuid4())
        with self.conn() as db:
            db.execute("BEGIN IMMEDIATE")
            dataset = db.execute("SELECT latest_version FROM datasets WHERE tenant_id=? AND id=?", (tenant_id, dataset_id)).fetchone()
            if not dataset:
                raise StoreError("RESOURCE_NOT_FOUND", "Dataset is not visible", 404)
            version_number = int(dataset["latest_version"]) + 1
            created = now()
            db.execute(
                "INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)",
                (tenant_id, version_id, dataset_id, version_number, sha256, case_count, artifact_id, created),
            )
            db.execute("UPDATE datasets SET latest_version=? WHERE tenant_id=? AND id=?", (version_number, tenant_id, dataset_id))
            if source_jsonl is not None:
                db.execute("INSERT INTO dataset_sources(tenant_id,version_id,source_jsonl) VALUES(?,?,?)", (tenant_id, version_id, source_jsonl))
        return version_id

    def build(self, tenant_id: str, name: str, build_sha: str, tool_sha: str, prompt_version: str) -> str:
        build_id = str(uuid.uuid4())
        with self.conn() as db:
            db.execute("INSERT INTO builds VALUES(?,?,?,?,?,?,?)", (tenant_id, build_id, name, build_sha, tool_sha, prompt_version, now()))
        return build_id

    def _run_row(self, tenant_id: str, run_id: str) -> sqlite3.Row | None:
        with self.conn() as db:
            return db.execute("SELECT * FROM runs WHERE tenant_id=? AND id=?", (tenant_id, run_id)).fetchone()

    def run(
        self,
        tenant_id: str,
        version_id: str,
        build_id: str,
        grader_sha: str,
        grader_config: dict[str, Any] | None = None,
        results: Iterable[dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
    ) -> sqlite3.Row:
        supplied = list(results) if results is not None else []
        if len(supplied) > 1000:
            raise StoreError("EVALUATION_BUDGET_EXCEEDED", "At most 1000 case results are accepted")
        keys = [item.get("case_key") if isinstance(item, dict) else None for item in supplied]
        if any(not isinstance(key, str) or not key or len(key) > 128 for key in keys):
            raise StoreError("INVALID_CASE_BINDING", "Each result requires a bounded string case key")
        if len(set(keys)) != len(keys):
            raise StoreError("DUPLICATE_CASE_RESULT", "Duplicate case results cannot overwrite evaluation evidence")
        trace_bytes = sum(len(item["trace_jsonl"].encode("utf-8", errors="surrogatepass")) for item in supplied if isinstance(item, dict) and isinstance(item.get("trace_jsonl"), str))
        if trace_bytes > 4 * 1024 * 1024:
            raise StoreError("EVALUATION_TRACE_BUDGET_EXCEEDED", "Combined traces exceed the 4 MiB evaluation budget")
        mode = (grader_config or {}).get("mode", "external-scores")
        if mode not in {"external-scores", MODE}:
            raise StoreError("INVALID_GRADER_CONFIGURATION", "Unsupported grading mode")
        if mode == MODE and grader_sha != GRADER_SHA256:
            raise StoreError("GRADER_IMPLEMENTATION_MISMATCH", "grader_sha256 must identify the installed exact JSON implementation")
        output_bytes = 0
        for item in supplied:
            if "observed_output" in item:
                try:
                    output_bytes += len(validate_output(item["observed_output"]))
                except (ValueError, UnicodeError, RecursionError) as error:
                    raise StoreError("INVALID_OBSERVED_OUTPUT", str(error)) from error
        if output_bytes > 4 * 1024 * 1024:
            raise StoreError("EVALUATION_OUTPUT_BUDGET_EXCEEDED", "Combined outputs exceed 4 MiB")
        fingerprint = digest({
            "version_id": version_id,
            "build_id": build_id,
            "grader_sha": grader_sha,
            "grader_config": grader_config or {},
            "results": supplied,
        })
        with self.conn() as db:
            if idempotency_key:
                prior = db.execute(
                    "SELECT * FROM idempotency_keys WHERE tenant_id=? AND operation='evaluation-run' AND key=?",
                    (tenant_id, idempotency_key),
                ).fetchone()
                if prior:
                    if prior["fingerprint"] != fingerprint:
                        raise StoreError("IDEMPOTENCY_KEY_REUSED", "Idempotency key was already used with a different request", 409)
                    replay = db.execute("SELECT * FROM runs WHERE tenant_id=? AND id=?", (tenant_id, prior["resource_id"])).fetchone()
                    if replay:
                        return replay
                    raise StoreError("IDEMPOTENCY_RECONCILIATION_REQUIRED", "The idempotent evaluation result is unavailable", 503)
            version = db.execute("SELECT * FROM versions WHERE tenant_id=? AND id=?", (tenant_id, version_id)).fetchone()
            build = db.execute("SELECT * FROM builds WHERE tenant_id=? AND id=?", (tenant_id, build_id)).fetchone()
            if not version or not build:
                raise StoreError("RESOURCE_NOT_FOUND", "Dataset version or agent build is not visible", 404)
            config = dict(grader_config or {})
            threshold = float(config.get("threshold", 0.0))
            if not 0.0 <= threshold <= 1.0:
                raise StoreError("INVALID_GRADER_CONFIGURATION", "threshold must be between 0 and 1")
            seed = config.get("seed")
            if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
                raise StoreError("INVALID_GRADER_CONFIGURATION", "seed must be an integer")
            if seed is not None and not -(2**63) <= seed <= 2**63-1:
                raise StoreError("INVALID_GRADER_CONFIGURATION", "seed must fit a signed 64-bit integer")
            seed_source = str(config.get("seed_source", "request" if seed is not None else "deterministic-default"))
            config["threshold"] = threshold
            config["seed"] = seed
            config["seed_source"] = seed_source
            config_sha = digest(config)
            if idempotency_key:
                # Stable IDs make a retry safe even if the caller is restarted between
                # the request and response. The request fingerprint above prevents key reuse.
                run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"agenttest:{tenant_id}:evaluation-run:{idempotency_key}"))
                job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"agenttest:{tenant_id}:evaluation-job:{idempotency_key}"))
            else:
                run_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
            created = now()
            expected = int(version["case_count"])
            if not 1 <= expected <= 1000:
                raise StoreError("EVALUATION_BUDGET_EXCEEDED", "Stored dataset exceeds the evaluation case budget")
            source = db.execute("SELECT * FROM dataset_sources WHERE tenant_id=? AND version_id=?", (tenant_id, version_id)).fetchone()
            if source:
                try:
                    dataset_cases = parse_dataset(source["source_jsonl"], version["sha256"], expected)
                    ordered_keys = [case["case_key"] for case in dataset_cases]
                    expected_outputs = {case["case_key"]: case["expected"] for case in dataset_cases}
                except (ValueError, UnicodeError) as error:
                    raise StoreError("DATASET_SOURCE_INTEGRITY_FAILED", str(error), 409) from error
            elif mode != MODE and getattr(self, "allow_fixture_versions", False) and os.getenv("APP_ENV", "development") in {"development", "test"}:
                ordered_keys = [f"case-{i}" for i in range(1, expected + 1)]
            else:
                raise StoreError("DATASET_SOURCE_REQUIRED", "This version has no verified source snapshot", 409)
            expected_keys = set(ordered_keys)
            if any(key not in expected_keys for key in keys):
                raise StoreError("UNKNOWN_CASE_RESULT", "Result key is not part of this dataset version's case set")
            if not supplied and mode != MODE:
                if os.getenv("AGENTTEST_SYNTHETIC_MODE") != "1" or os.getenv("APP_ENV") not in {"development", "test"}:
                    raise StoreError("AGENT_EXECUTION_DISABLED", "Supply actual case results; synthetic evaluation requires explicit development/test opt-in", 503)
                supplied = [
                    {"case_key": key, "status": "PASS", "score": 1.0, "trace_digest": digest({"case_key": key, "synthetic": True})}
                    for key in ordered_keys
                ]
                if grader_sha.endswith("f") and expected >= 2:
                    supplied[1] = {**supplied[1], "status": "FAIL", "score": 0.8}
            by_key = {str(item.get("case_key", "")): item for item in supplied if isinstance(item, dict)}
            complete = True
            db.execute(
                "INSERT INTO runs(tenant_id,id,version_id,build_id,grader_sha,grader_config_json,grader_config_sha,threshold,seed,seed_source,status,expected_case_count,job_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tenant_id, run_id, version_id, build_id, grader_sha, canonical_json(config), config_sha, threshold, seed, seed_source, "PENDING", expected, job_id, created),
            )
            if idempotency_key:
                db.execute(
                    "INSERT INTO idempotency_keys(tenant_id,operation,key,fingerprint,resource_id,created_at) VALUES(?,?,?,?,?,?)",
                    (tenant_id, "evaluation-run", idempotency_key, fingerprint, run_id, created),
                )
            for key in ordered_keys:
                item = by_key.get(key)
                if item is None:
                    status, score, error_code, trace_digest = "MISSING", None, "MISSING_RESULT", digest({"case_key": key, "missing": True})
                    complete = False
                else:
                    status = str(item.get("status", item.get("grade_status", "INVALID_RESULT"))).upper()
                    raw_score = item.get("score")
                    valid_score = isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool) and 0 <= float(raw_score) <= 1
                    if mode == MODE:
                        score, error_code = None, None
                    elif status in {"MISSING", "TIMEOUT"}:
                        score, error_code, complete = None, status, False
                    elif status not in {"PASS", "FAIL"} or not valid_score:
                        status, score, error_code, complete = "INVALID_RESULT", None, "INVALID_RESULT", False
                    else:
                        score, error_code = float(raw_score), None
                        if status != "PASS": complete = False
                    if mode == MODE:
                        if "observed_output" not in item:
                            status, score, error_code = "MISSING", None, "MISSING_OUTPUT"
                        else:
                            status, score = grade(expected_outputs[key], item["observed_output"])
                            error_code = None
                        # Caller status/score never determines an exact-json grade.
                    if status != "PASS":
                        complete = False
                    trace_digest = str(item.get("trace_digest") or digest({"case_key": key, "status": status, "score": score}))
                    if item.get("trace_jsonl") is not None:
                        try:
                            trace_digest = validate_and_redact_jsonl(item["trace_jsonl"], expected_case_key=key).sha256
                            if item.get("trace_digest") is not None and item["trace_digest"] != trace_digest:
                                raise ValueError("TRACE_DIGEST_MISMATCH")
                        except Exception:
                            status, score, error_code, complete = "INVALID_RESULT", None, "INVALID_TRACE", False
                    if mode == MODE:
                        # Bind persisted evidence to the dataset and actual output, even
                        # when a caller also supplies an independently validated trace.
                        trace_digest = digest({"mode": MODE, "dataset_sha256": version["sha256"], "case_key": key,
                            "output_present": "observed_output" in item,
                            "output_sha256": hashlib.sha256(validate_output(item["observed_output"])).hexdigest() if "observed_output" in item else None,
                            "trace_digest": trace_digest if item.get("trace_jsonl") is not None else None,
                            "status": status, "score": score})
                db.execute(
                    "INSERT INTO cases VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (tenant_id, str(uuid.uuid4()), run_id, key, status, score, grader_sha, trace_digest, error_code, created),
                )
            status = "SUCCEEDED" if complete else "PARTIAL"
            db.execute("UPDATE runs SET status=? WHERE tenant_id=? AND id=?", (status, tenant_id, run_id))
        row = self._run_row(tenant_id, run_id)
        assert row is not None
        return row

    def cases(self, tenant_id: str, run_id: str) -> list[sqlite3.Row]:
        with self.conn() as db:
            return db.execute("SELECT * FROM cases WHERE tenant_id=? AND run_id=? ORDER BY case_key", (tenant_id, run_id)).fetchall()

    def compare(self, tenant_id: str, candidate_id: str, baseline_id: str, policy: str, threshold: float | None = None, idempotency_key: str | None = None) -> sqlite3.Row:
        if candidate_id == baseline_id:
            raise StoreError("INVALID_COMPARISON_BINDING", "A run cannot be compared with itself", 409)
        baseline = self._run_row(tenant_id, baseline_id)
        candidate = self._run_row(tenant_id, candidate_id)
        if not baseline or not candidate:
            raise StoreError("RESOURCE_NOT_FOUND", "Baseline or candidate run is not visible", 404)
        if baseline["version_id"] != candidate["version_id"]:
            raise StoreError("DATASET_VERSION_MISMATCH", "Baseline and candidate must use the same immutable dataset version", 409)
        base_mode = json.loads(baseline["grader_config_json"]).get("mode", "external-scores")
        candidate_mode = json.loads(candidate["grader_config_json"]).get("mode", "external-scores")
        if base_mode != candidate_mode:
            raise StoreError("GRADING_MODE_MISMATCH", "Computed grades cannot be compared with caller-supplied scores", 409)
        strict_policy = policy == "strict-exact-no-regression-v1"
        if strict_policy and base_mode != MODE:
            raise StoreError("STRICT_POLICY_REQUIRES_EXACT_GRADER", "Strict per-case regression proof requires verified exact-json grading", 409)
        if base_mode == MODE and baseline["grader_sha"] != candidate["grader_sha"]:
            raise StoreError("GRADER_IMPLEMENTATION_MISMATCH", "Exact JSON comparisons require the same grader implementation", 409)
        effective_threshold = float(threshold if threshold is not None else max(float(baseline["threshold"] or 0), float(candidate["threshold"] or 0)))
        fingerprint = digest({"candidate_id": candidate_id, "baseline_id": baseline_id, "policy": policy, "threshold": effective_threshold})
        with self.conn() as db:
            if idempotency_key:
                prior = db.execute("SELECT * FROM idempotency_keys WHERE tenant_id=? AND operation='comparison' AND key=?", (tenant_id, idempotency_key)).fetchone()
                if prior:
                    if prior["fingerprint"] != fingerprint:
                        raise StoreError("IDEMPOTENCY_KEY_REUSED", "Idempotency key was already used with a different comparison request", 409)
                    replay = db.execute("SELECT * FROM comparisons WHERE tenant_id=? AND id=?", (tenant_id, prior["resource_id"])).fetchone()
                    if replay:
                        return replay
                    raise StoreError("IDEMPOTENCY_RECONCILIATION_REQUIRED", "The idempotent comparison result is unavailable", 503)
            existing = db.execute(
                "SELECT * FROM comparisons WHERE tenant_id=? AND baseline_id=? AND candidate_id=? AND policy=?",
                (tenant_id, baseline_id, candidate_id, policy),
            ).fetchone()
            if existing:
                if float(existing["threshold"]) != effective_threshold:
                    raise StoreError("COMPARISON_POLICY_CONFLICT", "The immutable comparison already uses a different threshold", 409)
                if idempotency_key:
                    db.execute(
                        "INSERT OR IGNORE INTO idempotency_keys(tenant_id,operation,key,fingerprint,resource_id,created_at) VALUES(?,?,?,?,?,?)",
                        (tenant_id, "comparison", idempotency_key, fingerprint, existing["id"], now()),
                    )
                return existing
        base_cases = self.cases(tenant_id, baseline_id)
        candidate_cases = self.cases(tenant_id, candidate_id)
        base_map, candidate_map = {row["case_key"]: row for row in base_cases}, {row["case_key"]: row for row in candidate_cases}
        paired_keys = sorted(set(base_map) & set(candidate_map))
        terminal_statuses = {"MISSING", "TIMEOUT", "INVALID_RESULT"}
        missing = len(set(base_map) ^ set(candidate_map)) + sum(1 for key in paired_keys if base_map[key]["grade_status"] in terminal_statuses or candidate_map[key]["grade_status"] in terminal_statuses)
        base_scores = [float(base_map[key]["score"]) for key in paired_keys if base_map[key]["score"] is not None]
        candidate_scores = [float(candidate_map[key]["score"]) for key in paired_keys if candidate_map[key]["score"] is not None]
        delta = (sum(candidate_scores) / len(candidate_scores) - sum(base_scores) / len(base_scores)) if base_scores and candidate_scores else -1.0
        bad_status = any(row["grade_status"] in terminal_statuses for row in (*base_cases, *candidate_cases))
        # Mean scores can hide an individual regression (1,0 -> 0,1).
        # This opt-in policy checks each *verified exact-json* case independently
        # without changing the existing aggregate comparison contract.
        regressed = 0
        if strict_policy:
            for key in paired_keys:
                baseline_case = base_map[key]
                candidate_case = candidate_map[key]
                base_score = baseline_case["score"]
                candidate_score = candidate_case["score"]
                if (base_score is not None and candidate_score is not None and candidate_score < base_score):
                    regressed += 1
                elif baseline_case["grade_status"] == "PASS" and candidate_case["grade_status"] != "PASS":
                    regressed += 1
        verdict = "PASS" if missing == 0 and not bad_status and delta >= -effective_threshold and (not strict_policy or regressed == 0) else "FAIL"
        binding = {
            "baseline_run_id": baseline_id, "candidate_run_id": candidate_id,
            "dataset_version_id": baseline["version_id"], "baseline_build_id": baseline["build_id"],
            "candidate_build_id": candidate["build_id"], "baseline_grader_sha256": baseline["grader_sha"],
            "candidate_grader_sha256": candidate["grader_sha"], "baseline_grader_config_sha256": baseline["grader_config_sha"],
            "candidate_grader_config_sha256": candidate["grader_config_sha"], "policy_version": policy,
            "threshold": effective_threshold, "seed_provenance": {
                "baseline_seed": baseline["seed"], "candidate_seed": candidate["seed"],
                "baseline_source": baseline["seed_source"], "candidate_source": candidate["seed_source"],
            },
        }
        export = {"binding": binding, "paired": len(paired_keys), "missing": missing, "delta": delta, "verdict": verdict}
        if strict_policy:
            export["regressed_case_count"] = regressed
        export_json = canonical_json(export)
        artifact_sha = hashlib.sha256(export_json.encode("utf-8")).hexdigest()
        comparison_id, artifact_id, created = str(uuid.uuid4()), str(uuid.uuid4()), now()
        with self.conn() as db:
            db.execute(
                "INSERT INTO comparisons(tenant_id,id,baseline_id,candidate_id,baseline_version_id,candidate_version_id,baseline_build_id,candidate_build_id,baseline_grader_sha,candidate_grader_sha,baseline_config_sha,candidate_config_sha,paired,missing,delta,threshold,policy,verdict,artifact_sha,artifact_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tenant_id, comparison_id, baseline_id, candidate_id, baseline["version_id"], candidate["version_id"], baseline["build_id"], candidate["build_id"], baseline["grader_sha"], candidate["grader_sha"], baseline["grader_config_sha"], candidate["grader_config_sha"], len(paired_keys), missing, delta, effective_threshold, policy, verdict, artifact_sha, artifact_id, created),
            )
            db.execute(
                "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (tenant_id, artifact_id, "ci-verdict-export", f"comparison-{comparison_id}.json", len(export_json.encode("utf-8")), artifact_sha, "application/json", "AVAILABLE", "synthetic-local", None, created),
            )
            db.execute(
                "INSERT INTO artifact_exports VALUES(?,?,?,?,?,?,?,?)",
                (tenant_id, str(uuid.uuid4()), artifact_id, comparison_id, "ci-verdict", artifact_sha, export_json, created),
            )
            if idempotency_key:
                db.execute(
                    "INSERT INTO idempotency_keys(tenant_id,operation,key,fingerprint,resource_id,created_at) VALUES(?,?,?,?,?,?)",
                    (tenant_id, "comparison", idempotency_key, fingerprint, comparison_id, created),
                )
        row = self.comparison(tenant_id, comparison_id)
        assert row is not None
        return row

    def comparison(self, tenant_id: str, comparison_id: str) -> sqlite3.Row | None:
        with self.conn() as db:
            return db.execute("SELECT * FROM comparisons WHERE tenant_id=? AND id=?", (tenant_id, comparison_id)).fetchone()

    def artifact_intent(self, tenant_id: str, kind: str, filename: str, size_bytes: int, sha256: str, media_type: str | None) -> sqlite3.Row:
        artifact_id, created = str(uuid.uuid4()), now()
        with self.conn() as db:
            db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)", (tenant_id, artifact_id, kind, filename, size_bytes, sha256, media_type, "INTENT_ISSUED", None, None, created))
        row = self.artifact(tenant_id, artifact_id)
        assert row is not None
        return row

    def artifact_commit(self, tenant_id: str, artifact_id: str, sha256: str, size_bytes: int, generation: str) -> sqlite3.Row:
        with self.conn() as db:
            row = db.execute("SELECT * FROM artifacts WHERE tenant_id=? AND id=?", (tenant_id, artifact_id)).fetchone()
            if not row:
                raise StoreError("RESOURCE_NOT_FOUND", "Artifact is not visible", 404)
            if row["status"] != "INTENT_ISSUED":
                raise StoreError("ARTIFACT_NOT_PENDING", "Artifact is immutable and cannot be committed again", 409)
            if row["sha256"] != sha256 or int(row["size_bytes"]) != size_bytes:
                db.execute("UPDATE artifacts SET status='REJECTED', rejected_reason='CHECKSUM_OR_SIZE_MISMATCH' WHERE tenant_id=? AND id=?", (tenant_id, artifact_id))
                raise StoreError("ARTIFACT_INTEGRITY_MISMATCH", "Committed artifact does not match its upload intent", 409)
            db.execute("UPDATE artifacts SET status='QUARANTINED', object_generation=? WHERE tenant_id=? AND id=?", (generation, tenant_id, artifact_id))
        result = self.artifact(tenant_id, artifact_id)
        assert result is not None
        return result

    def artifact(self, tenant_id: str, artifact_id: str) -> sqlite3.Row | None:
        with self.conn() as db:
            return db.execute("SELECT * FROM artifacts WHERE tenant_id=? AND id=?", (tenant_id, artifact_id)).fetchone()

    def download_intent(self, tenant_id: str, artifact_id: str) -> sqlite3.Row:
        row = self.artifact(tenant_id, artifact_id)
        if not row:
            raise StoreError("RESOURCE_NOT_FOUND", "Artifact is not visible", 404)
        if row["status"] != "AVAILABLE":
            raise StoreError("ARTIFACT_NOT_AVAILABLE", "Artifact is not available for download", 409)
        return row


    def export(self, tenant_id: str, artifact_id: str):
        with self.conn() as db:
            return db.execute("SELECT binding_json,sha256 FROM artifact_exports WHERE tenant_id=? AND artifact_id=?", (tenant_id, artifact_id)).fetchone()
