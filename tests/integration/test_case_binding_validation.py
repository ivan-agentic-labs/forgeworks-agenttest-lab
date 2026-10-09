import pytest
from agenttest_lab.infrastructure.store import Store, StoreError, TENANT, USER


def setup(tmp_path):
    store = Store(str(tmp_path / "cases.db")); store.seed()
    dataset = store.dataset(TENANT, "Synthetic case binding proof", USER)
    version = store.version(TENANT, dataset, "a" * 64, 2)
    build = store.build(TENANT, "Synthetic build", "b" * 64, "c" * 64, "v1")
    return store, version, build


@pytest.mark.parametrize("keys,code", [(["case-1", "case-1"], "DUPLICATE_CASE_RESULT"), (["case-1", "case-3"], "UNKNOWN_CASE_RESULT"), (["", "case-1"], "INVALID_CASE_BINDING")])
def test_invalid_results_rejected_without_persisting_run(tmp_path, keys, code):
    store, version, build = setup(tmp_path)
    with pytest.raises(StoreError) as error:
        store.run(TENANT, version, build, "d" * 64, results=[{"case_key": key, "status": "PASS", "score": 1.0} for key in keys])
    assert error.value.code == code
    with store.conn() as db:
        assert db.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_missing_case_stays_partial_instead_of_inventing_result(tmp_path):
    store, version, build = setup(tmp_path)
    row = store.run(TENANT, version, build, "d" * 64, results=[{"case_key": "case-1", "status": "PASS", "score": 1.0}])
    assert row["status"] == "PARTIAL"
    missing = next(case for case in store.cases(TENANT, row["id"]) if case["case_key"] == "case-2")
    assert missing["grade_status"] == "MISSING" and missing["score"] is None


@pytest.mark.parametrize("seed", [2**63, -(2**63)-1, True])
def test_out_of_range_seed_is_typed_failure(tmp_path, seed):
    store, version, build = setup(tmp_path)
    with pytest.raises(StoreError) as error:
        store.run(TENANT, version, build, "d" * 64, grader_config={"seed": seed}, results=[{"case_key": "case-1", "status": "PASS", "score": 1.0}])
    assert error.value.code == "INVALID_GRADER_CONFIGURATION"
