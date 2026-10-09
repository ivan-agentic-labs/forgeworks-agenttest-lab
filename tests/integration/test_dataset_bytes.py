import hashlib
import json
import pytest
from agenttest_lab.infrastructure.store import Store, StoreError, TENANT, USER
from agenttest_lab.domain.dataset import parse_dataset


def digest(source):
    return hashlib.sha256(source.encode()).hexdigest()


def test_dataset_custom_keys_bind_evaluation_and_tamper_fails(tmp_path):
    store=Store(str(tmp_path/"source.db"));store.seed();store.allow_fixture_versions=False
    dataset=store.dataset(TENANT,"Synthetic verified bytes",USER)
    source=json.dumps({"case_key":"custom.alpha","input":{"question":"synthetic"},"expected":"answer"})+"\n"
    version=store.version(TENANT,dataset,digest(source),1,source_jsonl=source)
    build=store.build(TENANT,"Synthetic build","b"*64,"c"*64,"v1")
    result=store.run(TENANT,version,build,"d"*64,results=[{"case_key":"custom.alpha","status":"PASS","score":1.0}])
    assert store.cases(TENANT,result["id"])[0]["case_key"]=="custom.alpha"
    with store.conn() as db:
        db.execute("UPDATE dataset_sources SET source_jsonl=? WHERE version_id=?",("tampered",version))
    with pytest.raises(StoreError) as error:
        store.run(TENANT,version,build,"d"*64,results=[{"case_key":"custom.alpha","status":"PASS","score":1.0}])
    assert error.value.code=="DATASET_SOURCE_INTEGRITY_FAILED"


def test_metadata_only_version_rejected_without_explicit_fixture_seed(tmp_path):
    store=Store(str(tmp_path/"metadata.db"))
    with pytest.raises(StoreError) as error:
        store.version(TENANT,"dataset-id","a"*64,1)
    assert error.value.code=="DATASET_SOURCE_REQUIRED"


@pytest.mark.parametrize("source", ['{"case_key":"a","input":1,"input":2,"expected":3}', '{"case_key":"a","input":NaN,"expected":3}', '{"case_key":"a","input":1e999,"expected":3}', '{"case_key":"a","input":1}', '\n'], ids=["duplicate-json","nan","infinity","schema","blank"])
def test_invalid_source_rejected(source):
    with pytest.raises(ValueError):
        parse_dataset(source,digest(source),1)


def test_repeated_case_keys_and_claimed_count_rejected():
    line='{"case_key":"a","input":1,"expected":2}\n'
    with pytest.raises(ValueError):parse_dataset(line*2,digest(line*2),2)
    with pytest.raises(ValueError):parse_dataset(line,digest(line),2)
