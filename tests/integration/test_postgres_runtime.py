"""Actual disposable PostgreSQL evaluation/export/signature/concurrency and RLS proof."""
import base64,hashlib,json,os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from agenttest_lab.infrastructure.store import TENANT,USER,StoreError
from agenttest_lab.infrastructure.security_catalog import REQUIRED_TENANT_TABLES
from agenttest_lab.infrastructure.postgres_store import PostgresStore, ROLE


def test_postgres_versions_evaluation_comparison_signature_and_tenant_isolation(monkeypatch):
    owner=os.getenv('AGENTTEST_DISPOSABLE_OWNER_DSN')
    if not owner:pytest.skip('Disposable PostgreSQL unavailable; NOT a runtime pass')
    info=conninfo_to_dict(owner)
    if os.getenv('G1_DISPOSABLE_DB')!='yes' or info.get('host') not in {'localhost','127.0.0.1'} or info.get('dbname')!='forgeworks_runtime':pytest.fail('Refusing non-disposable database')
    root=Path(__file__).resolve().parents[2];other=str(uuid4())
    with psycopg.connect(owner) as db:
        if db.execute("SELECT to_regclass('datasets')").fetchone()[0]:pytest.fail('Proof requires a fresh empty database')
        for name in ['001_agenttest_mvp.sql','002_agenttest_runtime.sql','003_agenttest_dataset_sources.sql']:db.execute((root/'migrations/versions'/name).read_text())
        db.execute((root/'infra/environments/staging/003_fk_lookup_index.sql').read_text())
        definition = db.execute("SELECT pg_get_indexdef('idx_evaluation_runs_tenant_dataset_version'::regclass)").fetchone()[0]
        assert 'evaluation_runs USING btree (tenant_id, dataset_version_id)' in definition
        db.execute((root/'infra/environments/staging/004_tenant_rls_initplan.sql').read_text())
        db.execute((root/'infra/environments/staging/005_remaining_tenant_rls_initplans.sql').read_text())
        for table, policy_name in [['agent_builds','tenant_boundary'],['artifact_exports','tenant_boundary'],['artifacts','tenant_boundary'],['case_results','case_results_tenant'],['comparisons','tenant_boundary'],['dataset_sources','tenant_boundary'],['dataset_versions','tenant_boundary'],['evaluation_runs','evaluation_runs_tenant'],['idempotency_keys','tenant_boundary'],['memberships','tenant_boundary']]:
            row = db.execute("SELECT qual, with_check, cmd, roles FROM pg_policies WHERE schemaname=current_schema() AND tablename=%s AND policyname=%s", (table, policy_name)).fetchone()
            assert row and row[2] == 'ALL' and row[3] == ['public']
            assert all('SELECT current_setting' in clause for clause in row[:2])

        policy = db.execute("SELECT qual, with_check FROM pg_policies WHERE schemaname=current_schema() AND tablename='datasets' AND policyname='datasets_tenant'").fetchone()
        assert policy and all('SELECT current_setting' in expression for expression in policy)
        # Run twice to prove replay safety, then inspect actual catalog definitions.
        for _ in range(2):
            db.execute((root/'infra/environments/staging/007_remaining_fk_indexes.sql').read_text())
        definition = db.execute("SELECT pg_get_indexdef('idx_artifact_exports_tenant_artifact'::regclass)").fetchone()[0]
        assert 'artifact_exports USING btree (tenant_id, artifact_id)' in definition
        definition = db.execute("SELECT pg_get_indexdef('idx_comparisons_tenant_artifact'::regclass)").fetchone()[0]
        assert 'comparisons USING btree (tenant_id, artifact_id)' in definition
        definition = db.execute("SELECT pg_get_indexdef('idx_comparisons_tenant_candidate'::regclass)").fetchone()[0]
        assert 'comparisons USING btree (tenant_id, candidate_id)' in definition
        definition = db.execute("SELECT pg_get_indexdef('idx_evaluation_runs_tenant_agent_build'::regclass)").fetchone()[0]
        assert 'evaluation_runs USING btree (tenant_id, agent_build_id)' in definition
        db.execute("CREATE ROLE fw_runtime_test LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'synthetic-local-runtime-test-only'")
        db.execute('GRANT fw_agenttest_lab_rw TO fw_runtime_test')
        db.execute('INSERT INTO tenants VALUES(%s,%s,%s)',(TENANT,'synthetic-demo','ACTIVE'))
        db.execute('INSERT INTO tenants VALUES(%s,%s,%s)',(other,'synthetic-other','ACTIVE'))
        db.execute('INSERT INTO memberships VALUES(%s,%s,%s,%s)',(TENANT,USER,'editor','ACTIVE'))
    info.update(user='fw_runtime_test',password='synthetic-local-runtime-test-only');runtime=make_conninfo(**info)
    with pytest.raises(ValueError,match='superuser'):PostgresStore(owner)
    # Real PostgreSQL catalog mutations, confined to this disposable fixture.
    # Existing RLS policy text must not hide disabled RLS or missing FORCE RLS.
    for table in REQUIRED_TENANT_TABLES:
        for drift, restore in [('DISABLE ROW LEVEL SECURITY', 'ENABLE ROW LEVEL SECURITY'),
                               ('NO FORCE ROW LEVEL SECURITY', 'FORCE ROW LEVEL SECURITY')]:
            with psycopg.connect(owner) as migration:
                migration.execute(psycopg.sql.SQL('ALTER TABLE {} ' + drift).format(
                    psycopg.sql.Identifier(table)))
            try:
                with pytest.raises(ValueError, match='RUNTIME_TENANT_RLS_REQUIRED'):
                    PostgresStore(runtime)
            finally:
                with psycopg.connect(owner) as migration:
                    migration.execute(psycopg.sql.SQL('ALTER TABLE {} ' + restore).format(
                        psycopg.sql.Identifier(table)))
    with psycopg.connect(owner) as migration:
        migration.execute('ALTER TABLE memberships RENAME TO fw_memberships_drift_probe')
    try:
        with pytest.raises(ValueError, match='RUNTIME_TENANT_TABLES_REQUIRED'):
            PostgresStore(runtime)
    finally:
        with psycopg.connect(owner) as migration:
            migration.execute('ALTER TABLE fw_memberships_drift_probe RENAME TO memberships')
    store=PostgresStore(runtime)
    assert store.member_role(TENANT, USER) == 'editor'
    # Verify an actual status change revokes authorization immediately.
    # This runs against the explicitly disposable localhost PostgreSQL fixture.
    with psycopg.connect(owner) as provisioning:
        result = provisioning.execute(
            "UPDATE memberships SET status='REVOKED' WHERE tenant_id=%s AND user_id=%s",
            (TENANT, USER),
        )
        assert result.rowcount == 1
    assert store.member_role(TENANT, USER) is None
    with psycopg.connect(owner) as provisioning:
        result = provisioning.execute(
            "UPDATE memberships SET status='ACTIVE' WHERE tenant_id=%s AND user_id=%s",
            (TENANT, USER),
        )
        assert result.rowcount == 1
    assert store.member_role(TENANT, USER) == 'editor'

    assert store.member_role(TENANT, 'malformed-subject') is None
    assert not store.member(TENANT, "unmapped-oidc-subject")
    # Runtime login and its group cannot own tenant/provisioning tables either.
    for table, new_owner in [('memberships','fw_runtime_test'),('tenants',ROLE)]:
        with psycopg.connect(owner) as db:
            db.execute(psycopg.sql.SQL('ALTER TABLE {} OWNER TO {}').format(psycopg.sql.Identifier(table),psycopg.sql.Identifier(new_owner)))
        try:
            with pytest.raises(ValueError,match='own product tables'):
                PostgresStore(runtime)
        finally:
            with psycopg.connect(owner) as db:
                db.execute(psycopg.sql.SQL('ALTER TABLE {} OWNER TO postgres').format(psycopg.sql.Identifier(table)))
                db.execute(psycopg.sql.SQL('REVOKE ALL ON {} FROM {}').format(psycopg.sql.Identifier(table),psycopg.sql.Identifier(new_owner)))

    assert store.member(TENANT,USER) and not store.member(other,USER)
    dataset=store.dataset(TENANT,'Synthetic corpus',USER)
    peers=[PostgresStore(runtime),PostgresStore(runtime)]
    source='{"case_key":"case-1","input":"synthetic-a","expected":"a"}\n{"case_key":"case-2","input":"synthetic-b","expected":"b"}\n'
    source_sha=hashlib.sha256(source.encode()).hexdigest()
    with ThreadPoolExecutor(max_workers=4) as pool:
        versions=list(pool.map(lambda index:peers[index%2].version(TENANT,dataset,source_sha,2,source_jsonl=source),range(8)))
    with store.conn(TENANT) as db:
        assert sorted(row['version_number'] for row in db.execute('SELECT * FROM versions WHERE dataset_id=?',(dataset,)).fetchall())==list(range(1,9))
        assert db.execute('UPDATE datasets SET name=? WHERE tenant_id=?',('forbidden',other)).rowcount==0
        assert db.execute('DELETE FROM datasets WHERE tenant_id=?',(other,)).rowcount==0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):db.execute('INSERT INTO datasets VALUES(?,?,?,?,?)',(other,str(uuid4()),'forbidden',USER,0))
    with psycopg.connect(runtime) as db:
        db.execute('SET LOCAL ROLE fw_agenttest_lab_rw')
        assert db.execute('SELECT count(*) FROM datasets').fetchone()[0]==0
    build=store.build(TENANT,'Synthetic build','b'*64,'c'*64,'prompt-v1')
    with store.conn(TENANT) as db:
        assert db.execute('SELECT source_jsonl FROM dataset_sources WHERE version_id=?',(versions[0],)).fetchone()['source_jsonl']==source
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute('UPDATE dataset_sources SET source_jsonl=? WHERE version_id=?',('tampered',versions[0]))
    with store.conn(other) as db:
        assert db.execute('SELECT count(*) FROM dataset_sources').fetchone()[0]==0
    custom_source='{"case_key":"verified.custom","input":"synthetic","expected":"answer"}\n'
    custom_version=store.version(TENANT,dataset,hashlib.sha256(custom_source.encode()).hexdigest(),1,source_jsonl=custom_source)
    custom_run=store.run(TENANT,custom_version,build,'d'*64,results=[{'case_key':'verified.custom','status':'PASS','score':1.0}])
    assert store.cases(TENANT,custom_run['id'])[0]['case_key']=='verified.custom'
    precision_baseline=store.run(TENANT,custom_version,build,'d'*64,results=[{'case_key':'verified.custom','status':'PASS','score':0.12344}])
    precision_candidate=store.run(TENANT,custom_version,build,'d'*64,results=[{'case_key':'verified.custom','status':'PASS','score':0.12346}])
    assert store.cases(TENANT,precision_baseline['id'])[0]['score']==0.1234
    assert store.cases(TENANT,precision_candidate['id'])[0]['score']==0.1235
    precision_comparison=store.compare(TENANT,precision_candidate['id'],precision_baseline['id'],'precision-policy')
    assert precision_comparison['delta']==0.0001
    with store.conn(TENANT) as db:
        precision_export=db.execute('SELECT binding_json FROM artifact_exports WHERE tenant_id=? AND comparison_id=?',(TENANT,precision_comparison['id'])).fetchone()
    assert json.loads(precision_export['binding_json'])['delta']==0.0001
    from agenttest_lab.domain.exact_grader import MODE, GRADER_SHA256
    exact = store.run(TENANT, custom_version, build, GRADER_SHA256, {'mode': MODE},
        [{'case_key':'verified.custom', 'observed_output':'wrong', 'status':'PASS', 'score':1.0}])
    exact_case = store.cases(TENANT, exact['id'])[0]
    assert exact_case['grade_status'] == 'FAIL' and exact_case['score'] == 0.0
    exact_pass = store.run(TENANT, custom_version, build, GRADER_SHA256, {'mode': MODE},
        [{'case_key':'verified.custom', 'observed_output':'answer', 'status':'FAIL', 'score':0.0}])
    assert exact_pass['status'] == 'SUCCEEDED'
    with pytest.raises(StoreError) as mismatch:
        store.compare(TENANT, custom_run['id'], exact_pass['id'], 'mixed-grading-policy')
    assert mismatch.value.code == 'GRADING_MODE_MISMATCH'
    assert store.compare(TENANT, exact['id'], exact_pass['id'], 'computed-grading-policy')['verdict'] == 'FAIL'
    results=[{'case_key':'case-1','status':'PASS','score':1.0},{'case_key':'case-2','status':'PASS','score':1.0}]
    baseline=store.run(TENANT,versions[0],build,'d'*64,results=results,idempotency_key='baseline-001')
    assert store.run(TENANT,versions[0],build,'d'*64,results=results,idempotency_key='baseline-001')['id']==baseline['id']
    with pytest.raises(StoreError) as conflict:store.run(TENANT,versions[0],build,'e'*64,results=results,idempotency_key='baseline-001')
    assert conflict.value.code=='IDEMPOTENCY_KEY_REUSED'
    candidate=store.run(TENANT,versions[0],build,'d'*64,results=results,idempotency_key='candidate-001')
    partial=store.run(TENANT,versions[0],build,'d'*64,results=results[:1])
    assert partial['status']=='PARTIAL' and store.cases(TENANT,partial['id'])[1]['score'] is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids=list(pool.map(lambda index:peers[index].compare(TENANT,candidate['id'],baseline['id'],'synthetic-policy',0.0)['id'],range(2)))
    assert len(set(ids))==1
    assert store.comparison(other,ids[0]) is None
    from fastapi.testclient import TestClient
    from agenttest_lab.main import create_app
    from test_agenttest_flow import h
    monkeypatch.setenv('AGENTTEST_DATABASE_URL',runtime)
    with TestClient(create_app()) as client:
        verdict=client.get(f'/v1/comparisons/{ids[0]}/ci-verdict',headers=h('evaluation:read'))
        assert verdict.status_code==200,verdict.text
        data=verdict.json()
        body=data['signed_payload'].encode()
        assert hashlib.sha256(body).hexdigest()==data['signed_artifact_sha256']
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        key=load_pem_private_key(os.environ['CI_VERDICT_SIGNING_KEY_PEM'].encode(),password=None)
        key.public_key().verify(base64.urlsafe_b64decode(data['signature']),body)

        comparison = store.comparison(TENANT,ids[0])
        intent = client.post(f"/v1/artifacts/{comparison['artifact_id']}/download-intents",headers=h('artifact:download'))
        assert intent.status_code==201,intent.text
        transferred=client.get(intent.json()['download_url'])
        assert transferred.status_code==200 and hashlib.sha256(transferred.content).hexdigest()==comparison['artifact_sha']
