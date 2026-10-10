import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from agenttest_lab.domain.exact_grader import MODE, GRADER_SHA256, grade, validate_output
from agenttest_lab.infrastructure.store import Store, StoreError, TENANT, USER
from agenttest_lab.main import create_app
from test_agenttest_flow import h


def setup(tmp_path, expected):
    store = Store(str(tmp_path / 'exact.db')); store.seed()
    source = json.dumps({'case_key': 'actual', 'input': {}, 'expected': expected}) + '\n'
    dataset = store.dataset(TENANT, 'Verified exact answers', USER)
    version = store.version(TENANT, dataset, hashlib.sha256(source.encode()).hexdigest(), 1, source_jsonl=source)
    build = store.build(TENANT, 'Recorded agent', 'b'*64, 'c'*64, 'p1')
    return store, version, build


@pytest.mark.parametrize('expected,observed,matched', [
    (True, 1, False), (False, 0, False), (1, 1.0, True),
    ({'a': 1, 'b': 2}, {'b': 2, 'a': 1}, True),
    ([1, 2], [2, 1], False), (None, None, True),
    ({'nested': [True]}, {'nested': [1]}, False), ('1', 1, False),
])
def test_json_semantics(expected, observed, matched):
    assert grade(expected, observed) == (('PASS', 1.0) if matched else ('FAIL', 0.0))


@pytest.mark.parametrize('output', [float('nan'), float('inf'), '\ud800', {1: 'bad'}, (1,), [0]*20001, 'x'*1048577], ids=['nan','infinity','unpaired-unicode','non-string-key','non-json-tuple','too-many-nodes','too-many-bytes'])
def test_invalid_output_is_bounded(output):
    with pytest.raises((ValueError, UnicodeError)):
        validate_output(output)


def test_nested_budget():
    output = 0
    for _ in range(34): output = [output]
    with pytest.raises(ValueError): validate_output(output)


@pytest.mark.parametrize('expected,output,status,score,grade_status', [
    ('correct', 'wrong', 'PASS', 1.0, 'FAIL'),
    ('correct', 'correct', 'FAIL', 0.0, 'PASS'),
    (None, None, 'INVALID_RESULT', None, 'PASS'),
])
def test_scores_computed_from_verified_expected(tmp_path, expected, output, status, score, grade_status):
    store, version, build = setup(tmp_path, expected)
    row = store.run(TENANT, version, build, GRADER_SHA256, {'mode': MODE}, [{'case_key':'actual', 'observed_output':output, 'status':status, 'score':score}])
    case = store.cases(TENANT, row['id'])[0]
    assert case['grade_status'] == grade_status
    assert case['score'] == (1.0 if grade_status == 'PASS' else 0.0)
    assert row['status'] == ('SUCCEEDED' if grade_status == 'PASS' else 'PARTIAL')


def test_missing_output_is_not_null(tmp_path):
    store, version, build = setup(tmp_path, None)
    for results in ([], [{'case_key':'actual', 'status':'PASS', 'score':1}]):
        row = store.run(TENANT, version, build, GRADER_SHA256, {'mode':MODE}, results)
        case = store.cases(TENANT, row['id'])[0]
        assert case['grade_status'] == 'MISSING' and case['score'] is None


def test_grader_identity_and_invalid_input_fail_without_run(tmp_path):
    store, version, build = setup(tmp_path, 1)
    for sha, config, output, code in [
        ('d'*64, {'mode':MODE}, 1, 'GRADER_IMPLEMENTATION_MISMATCH'),
        (GRADER_SHA256, {'mode':'invented'}, 1, 'INVALID_GRADER_CONFIGURATION'),
        (GRADER_SHA256, {'mode':MODE}, float('inf'), 'INVALID_OBSERVED_OUTPUT'),
    ]:
        with pytest.raises(StoreError) as error:
            store.run(TENANT, version, build, sha, config, [{'case_key':'actual','observed_output':output}])
        assert error.value.code == code
    with store.conn() as db: assert db.execute('SELECT count(*) FROM runs').fetchone()[0] == 0


def test_exact_mode_requires_source_even_with_fixture_optin(tmp_path):
    store = Store(str(tmp_path/'fixture.db')); store.seed()
    dataset = store.dataset(TENANT, 'Fixture', USER)
    version = store.version(TENANT, dataset, 'a'*64, 1)
    build = store.build(TENANT, 'Fixture', 'b'*64, 'c'*64, 'p1')
    with pytest.raises(StoreError) as error:
        store.run(TENANT, version, build, GRADER_SHA256, {'mode':MODE}, [{'case_key':'case-1','observed_output':1}])
    assert error.value.code == 'DATASET_SOURCE_REQUIRED'


def test_evidence_and_replay_bind_actual_output(tmp_path):
    store, version, build = setup(tmp_path, 1)
    def run(output, key):
        return store.run(TENANT, version, build, GRADER_SHA256, {'mode':MODE}, [{'case_key':'actual','observed_output':output}], idempotency_key=key)
    baseline = run(1, 'baseline'); assert run(1, 'baseline')['id'] == baseline['id']
    with pytest.raises(StoreError) as error: run(0, 'baseline')
    assert error.value.code == 'IDEMPOTENCY_KEY_REUSED'
    candidate = run(0, 'candidate')
    assert store.cases(TENANT, baseline['id'])[0]['trace_digest'] != store.cases(TENANT, candidate['id'])[0]['trace_digest']
    comparison = store.compare(TENANT, candidate['id'], baseline['id'], 'exact-policy')
    assert comparison['verdict'] == 'FAIL'


def test_http_preserves_explicit_null(tmp_path):
    store, version, build = setup(tmp_path, None)
    with TestClient(create_app(str(tmp_path/'exact.db'), seed=True)) as client:
        body = {'dataset_version_id':version, 'agent_build_id':build, 'grader_sha256':GRADER_SHA256,
                'grader_config':{'mode':MODE}, 'case_results':[{'case_key':'actual','observed_output':None}]}
        result = client.post('/v1/evaluation-runs', headers=h('evaluation:run'), json=body)
        assert result.status_code == 202, result.text
        assert result.json()['status'] == 'SUCCEEDED'
        body['case_results'] = [{'case_key':'actual'}]
        missing = client.post('/v1/evaluation-runs', headers=h('evaluation:run'), json=body)
        assert missing.status_code == 202 and missing.json()['status'] == 'PARTIAL'


def test_output_aggregate_budget(tmp_path):
    store, version, build = setup(tmp_path, 1)
    results = [{'case_key':f'case-{i}', 'observed_output':'x'*900000} for i in range(5)]
    with pytest.raises(StoreError) as error:
        store.run(TENANT, version, build, GRADER_SHA256, {'mode':MODE}, results)
    assert error.value.code == 'EVALUATION_OUTPUT_BUDGET_EXCEEDED'


def test_invalid_trace_cannot_be_overridden_by_matching_output(tmp_path):
    store, version, build = setup(tmp_path, 1)
    row = store.run(TENANT, version, build, GRADER_SHA256, {'mode':MODE},
                    [{'case_key':'actual', 'observed_output':1, 'trace_jsonl':'{"case_key":"different"}\n'}])
    case = store.cases(TENANT, row['id'])[0]
    assert case['grade_status'] == 'INVALID_RESULT' and case['error_code'] == 'INVALID_TRACE'
    assert row['status'] == 'PARTIAL'


def test_grader_sha_tracks_implementation():
    from pathlib import Path
    import agenttest_lab.domain.exact_grader as module
    assert GRADER_SHA256 == hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()


@pytest.mark.parametrize('reverse', [False, True])
def test_external_scores_cannot_pass_against_computed_baseline(tmp_path, reverse):
    store, version, build = setup(tmp_path, 1)
    exact = store.run(TENANT, version, build, GRADER_SHA256, {'mode':MODE}, [{'case_key':'actual','observed_output':1}])
    external = store.run(TENANT, version, build, 'd'*64, results=[{'case_key':'actual','status':'PASS','score':1}])
    candidate, baseline = (exact, external) if reverse else (external, exact)
    with pytest.raises(StoreError) as error:
        store.compare(TENANT, candidate['id'], baseline['id'], 'computed-policy')
    assert error.value.code == 'GRADING_MODE_MISMATCH'
    with store.conn() as db: assert db.execute('SELECT count(*) FROM comparisons').fetchone()[0] == 0


def test_exact_comparison_rejects_changed_implementation(tmp_path):
    store, version, build = setup(tmp_path, 1)
    results = [{'case_key':'actual','observed_output':1}]
    baseline = store.run(TENANT, version, build, GRADER_SHA256, {'mode':MODE}, results)
    candidate = store.run(TENANT, version, build, GRADER_SHA256, {'mode':MODE}, results)
    # Model an immutable run produced by an older deployed grader revision.
    with store.conn() as db:
        db.execute('UPDATE runs SET grader_sha=? WHERE tenant_id=? AND id=?', ('d'*64,TENANT,baseline['id']))
    with pytest.raises(StoreError) as error:
        store.compare(TENANT,candidate['id'],baseline['id'],'computed-policy')
    assert error.value.code == 'GRADER_IMPLEMENTATION_MISMATCH'
