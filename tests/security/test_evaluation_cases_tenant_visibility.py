"""Tenant-safe visibility of evaluation-run case listings in real SQLite store.

The PostgreSQL adapter inherits the same Store.cases logic with RLS-scoped
connections, and disposable runtime CI exercises its implementation.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest

from agenttest_lab.infrastructure.store import Store, StoreError


def test_existing_zero_case_run_is_success_but_other_tenant_is_not_found():
    tenant_a, tenant_b, run_id = (str(uuid4()) for _ in range(3))
    with TemporaryDirectory() as root:
        store = Store(str(Path(root) / "tenant-visibility.db"))
        with store.conn() as db:
            db.execute(
                "INSERT INTO runs(tenant_id,id) VALUES (?,?)",
                (tenant_a, run_id),
            )
        assert store.cases(tenant_a, run_id) == []
        for requested_tenant, requested_run in (
            (tenant_b, run_id),
            (tenant_a, str(uuid4())),
        ):
            with pytest.raises(StoreError) as failure:
                store.cases(requested_tenant, requested_run)
            assert failure.value.code == "RESOURCE_NOT_FOUND"
            assert failure.value.status == 404
            assert failure.value.detail == "Evaluation run is not visible"


def test_tenant_visibility_check_never_returns_foreign_cases():
    tenant_a, tenant_b, run_id, case_id = (str(uuid4()) for _ in range(4))
    with TemporaryDirectory() as root:
        store = Store(str(Path(root) / "tenant-cases.db"))
        with store.conn() as db:
            db.execute("INSERT INTO runs(tenant_id,id) VALUES (?,?)",
                       (tenant_a, run_id))
            db.execute(
                "INSERT INTO cases(tenant_id,id,run_id,case_key) VALUES (?,?,?,?)",
                (tenant_a, case_id, run_id, "synthetic-case"),
            )
        items = store.cases(tenant_a, run_id)
        assert len(items) == 1
        assert items[0]["id"] == case_id
        with pytest.raises(StoreError) as failure:
            store.cases(tenant_b, run_id)
        assert failure.value.status == 404
