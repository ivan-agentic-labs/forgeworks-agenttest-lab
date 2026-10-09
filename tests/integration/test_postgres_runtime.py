"""Actual disposable PostgreSQL evaluation/export/signature/concurrency and RLS proof."""
import base64,hashlib,os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from agenttest_lab.infrastructure.store import TENANT,USER,StoreError
from agenttest_lab.infrastructure.postgres_store import PostgresStore


def test_postgres_versions_evaluation_comparison_signature_and_tenant_isolation(monkeypatch):
    owner=os.getenv('AGENTTEST_DISPOSABLE_OWNER_DSN')
    if not owner:pytest.skip('Disposable PostgreSQL unavailable; NOT a runtime pass')
    info=conninfo_to_dict(owner)
    if os.getenv('G1_DISPOSABLE_DB')!='yes' or info.get('host') not in {'localhost','127.0.0.1'} or info.get('dbname')!='forgeworks_runtime':pytest.fail('Refusing non-disposable database')
    root=Path(__file__).resolve().parents[2];other=str(uuid4())
    with psycopg.connect(owner) as db:
        if db.execute("SELECT to_regclass('datasets')").fetchone()[0]:pytest.fail('Proof requires a fresh empty database')
        for name in ['001_agenttest_mvp.sql','002_agenttest_runtime.sql']:db.execute((root/'migrations/versions'/name).read_text())
        db.execute("CREATE ROLE fw_runtime_test LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'synthetic-local-runtime-test-only'")
        db.execute('GRANT fw_agenttest_lab_rw TO fw_runtime_test')
        db.execute('INSERT INTO tenants VALUES(%s,%s,%s)',(TENANT,'synthetic-demo','ACTIVE'))
        db.execute('INSERT INTO tenants VALUES(%s,%s,%s)',(other,'synthetic-other','ACTIVE'))
        db.execute('INSERT INTO memberships VALUES(%s,%s,%s,%s)',(TENANT,USER,'editor','ACTIVE'))
    info.update(user='fw_runtime_test',password='synthetic-local-runtime-test-only');runtime=make_conninfo(**info)
    with pytest.raises(ValueError,match='superuser'):PostgresStore(owner)
    store=PostgresStore(runtime)
    assert not store.member(TENANT, "unmapped-oidc-subject")
    # Even ownership of a different product table is forbidden to runtime login/group.
    with psycopg.connect(owner) as db:
        db.execute('ALTER TABLE memberships OWNER TO fw_runtime_test')
    try:
        with pytest.raises(ValueError,match='own product tables'):
            PostgresStore(runtime)
    finally:
        with psycopg.connect(owner) as db:
            db.execute('ALTER TABLE memberships OWNER TO postgres')

    assert store.member(TENANT,USER) and not store.member(other,USER)
    dataset=store.dataset(TENANT,'Synthetic corpus',USER)
    peers=[PostgresStore(runtime),PostgresStore(runtime)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        versions=list(pool.map(lambda index:peers[index%2].version(TENANT,dataset,'a'*64,2),range(8)))
    with store.conn(TENANT) as db:
        assert sorted(row['version_number'] for row in db.execute('SELECT * FROM versions WHERE dataset_id=?',(dataset,)).fetchall())==list(range(1,9))
        assert db.execute('UPDATE datasets SET name=? WHERE tenant_id=?',('forbidden',other)).rowcount==0
        assert db.execute('DELETE FROM datasets WHERE tenant_id=?',(other,)).rowcount==0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):db.execute('INSERT INTO datasets VALUES(?,?,?,?,?)',(other,str(uuid4()),'forbidden',USER,0))
    with psycopg.connect(runtime) as db:
        db.execute('SET LOCAL ROLE fw_agenttest_lab_rw')
        assert db.execute('SELECT count(*) FROM datasets').fetchone()[0]==0
    build=store.build(TENANT,'Synthetic build','b'*64,'c'*64,'prompt-v1')
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
