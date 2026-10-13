"""Fail closed when migration drift removes tenant-table RLS protections."""

REQUIRED_TENANT_TABLES = ('datasets', 'dataset_versions', 'agent_builds', 'evaluation_runs', 'case_results', 'memberships', 'artifacts', 'comparisons', 'artifact_exports', 'idempotency_keys', 'dataset_sources')


def verify_tenant_catalog(db):
    # Scope catalog reads to the runtime schema, never another product's schema.
    rows = db.execute(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=current_schema() AND c.relkind IN ('r','p') "
        "AND c.relname=ANY(%s)",
        (list(REQUIRED_TENANT_TABLES),),
    ).fetchall()
    observed = {row["relname"]: row for row in rows}
    if set(observed) != set(REQUIRED_TENANT_TABLES):
        raise ValueError("RUNTIME_TENANT_TABLES_REQUIRED")
    if any(row["relrowsecurity"] is not True or row["relforcerowsecurity"] is not True
           for row in observed.values()):
        raise ValueError("RUNTIME_TENANT_RLS_REQUIRED")
