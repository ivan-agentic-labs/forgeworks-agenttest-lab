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


def test_escaped_unpaired_surrogate_rejected_before_persistence():
    source='{"case_key":"a","input":"\\ud800","expected":2}\n'
    with pytest.raises(ValueError,match="DATASET_INVALID_UNICODE"):
        parse_dataset(source,digest(source),1)


@pytest.mark.parametrize("literal", [
    "0.10000000000000001",
    "1.0000000000000001",
    "1e-999",
    "1e999",
    "-0.0000000000000000000000000100000000000000001",
])
def test_exact_dataset_rejects_lossy_binary64_numeric_literals(literal):
    source = '{"case_key":"float","input":{},"expected":{"score":' + literal + '}}\n'
    with pytest.raises(ValueError, match="DATASET_NUMERIC_PRECISION_LOSS|DATASET_NONFINITE_NUMBER"):
        parse_dataset(source, digest(source), 1)


@pytest.mark.parametrize("literal,expected", [
    ("0.1", 0.1),
    ("1e-7", 1e-7),
    ("-0.00000000000000000000000001", -1e-26),
    ("1.25", 1.25),
    ("0.30000000000000004", 0.30000000000000004),
])
def test_exact_dataset_accepts_roundtripping_floats(literal, expected):
    source = '{"case_key":"float","input":{},"expected":{"score":' + literal + '}}\n'
    rows = parse_dataset(source, digest(source), 1)
    assert rows[0]["expected"]["score"] == expected


def test_lossy_golden_dataset_upload_fails_before_version_or_source_write(tmp_path):
    store = Store(str(tmp_path / "lossy-dataset.sqlite"))
    store.seed()
    did = store.dataset(TENANT, "Synthetic exact golden case", USER)
    source = '{"case_key":"a","input":{},"expected":0.10000000000000001}\n'
    with pytest.raises(StoreError) as error:
        store.version(TENANT, did, digest(source), 1, source_jsonl=source)
    assert error.value.code == "DATASET_SOURCE_INVALID"
    with store.conn() as db:
        assert db.execute("SELECT count(*) FROM versions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM dataset_sources").fetchone()[0] == 0


@pytest.mark.parametrize("source", [
    "invalid" + chr(0xD800) + "case",
    "invalid" + chr(0xDFFF) + "case",
])
def test_actual_unpaired_unicode_is_typed_dataset_failure(source):
    with pytest.raises(ValueError, match="DATASET_INVALID_UNICODE"):
        parse_dataset(source, "0" * 64, 1)


@pytest.mark.parametrize("source", [None, b"not-a-text-dataset", ["not", "jsonl"]])
def test_nontext_dataset_source_fails_with_stable_error(source):
    with pytest.raises(ValueError, match="DATASET_SOURCE_INVALID"):
        parse_dataset(source, "0" * 64, 1)


def test_oversized_json_integer_has_stable_validation_error():
    literal = "9" * 5000
    source = '{"case_key":"large-int","input":{},"expected":' + literal + '}\n'
    with pytest.raises(ValueError, match="DATASET_INTEGER_BUDGET_EXCEEDED"):
        parse_dataset(source, digest(source), 1)


def test_large_but_bounded_exact_json_integer_is_accepted():
    literal = "9" * 128
    source = '{"case_key":"bounded-int","input":{},"expected":' + literal + '}\n'
    rows = parse_dataset(source, digest(source), 1)
    assert rows[0]["expected"] == int(literal)
