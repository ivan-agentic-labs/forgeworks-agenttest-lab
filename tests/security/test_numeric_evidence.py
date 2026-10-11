import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from agenttest_lab.infrastructure.store import TENANT, USER
from agenttest_lab.main import CaseResultInput, GraderConfig, Run, Compare, create_app

IDENTIFIER = '33333333-3333-3333-3333-333333333333'


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    app = create_app(str(tmp_path_factory.mktemp('numeric') / 'db.sqlite'), seed=True)
    with TestClient(app, raise_server_exceptions=False) as value:
        yield value


def authorization():
    token = jwt.encode({'sub': USER, 'tenant_id': TENANT, 'scope': 'evaluation:run evaluation:compare',
                        'iss': 'https://issuer.synthetic.invalid', 'aud': 'forgeworks-api',
                        'exp': datetime.now(timezone.utc) + timedelta(minutes=5)},
                       'forgeworks-development-secret-32-plus', algorithm='HS256')
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


@pytest.mark.parametrize('surface', ['score', 'grader_threshold', 'run_threshold', 'compare_threshold'])
@pytest.mark.parametrize('value', [True, False, '0.5', '1', float('inf')])
def test_non_numeric_or_nonfinite_evidence_is_rejected_without_writes(client, surface, value):
    body = {'dataset_version_id': IDENTIFIER, 'agent_build_id': IDENTIFIER, 'grader_sha256': 'a' * 64}
    path = '/v1/evaluation-runs'
    if surface == 'score':
        body['case_results'] = [{'case_key': 'case-1', 'score': value}]
    elif surface == 'grader_threshold':
        body['grader_config'] = {'threshold': value}
    elif surface == 'run_threshold':
        body['threshold'] = value
    else:
        body = {'baseline_run_id': IDENTIFIER, 'policy_version': 'strict-v1', 'threshold': value}
        path += f'/{IDENTIFIER}/comparisons'
    # 1e400 is syntactically valid JSON; parsing it must not produce an HTTP 500.
    wire = json.dumps(body).replace('Infinity', '1e400')
    with client.app.state.store.conn() as db:
        before = [db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('runs', 'comparisons', 'cases')]
    response = client.post(path, headers=authorization(), content=wire)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_REQUEST'
    assert 'input' not in response.json()
    with client.app.state.store.conn() as db:
        after = [db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('runs', 'comparisons', 'cases')]
    assert after == before


@pytest.mark.parametrize('value', [0, 1, 0.0, 0.5, 1.0])
def test_real_json_numbers_remain_accepted_by_models(value):
    assert CaseResultInput(case_key='case-1', score=value).score == value
    assert GraderConfig(threshold=value).threshold == value
    assert Run(dataset_version_id=IDENTIFIER, agent_build_id=IDENTIFIER, grader_sha256='a' * 64, threshold=value).threshold == value
    assert Compare(baseline_run_id=IDENTIFIER, policy_version='v1', threshold=value).threshold == value


def test_optional_score_and_threshold_stay_nullable():
    assert CaseResultInput(case_key='case-1', score=None).score is None
    assert Run(dataset_version_id=IDENTIFIER, agent_build_id=IDENTIFIER, grader_sha256='a' * 64, threshold=None).threshold is None
    assert Compare(baseline_run_id=IDENTIFIER, policy_version='v1', threshold=None).threshold is None
