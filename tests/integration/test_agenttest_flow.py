from datetime import datetime,timedelta,timezone
import jwt
from fastapi.testclient import TestClient
from agenttest_lab.main import create_app
from agenttest_lab.infrastructure.store import TENANT,USER
S='forgeworks-development-secret-32-plus';ISS='https://issuer.synthetic.invalid';AUD='forgeworks-api'
def h(scope,tenant=TENANT):
 t=jwt.encode({'sub':USER,'tenant_id':tenant,'scope':scope,'iss':ISS,'aud':AUD,'exp':datetime.now(timezone.utc)+timedelta(minutes=5)},S,algorithm='HS256');return {'Authorization':'Bearer '+t}
def test_evaluation_comparison_verdict(tmp_path):
 app=create_app(str(tmp_path/'db.sqlite'),seed=True)
 with TestClient(app) as c:
  d=c.post('/v1/datasets',headers=h('dataset:create'),json={'name':'golden'}).json();did=d['id']
  v=c.post(f'/v1/datasets/{did}/versions',headers=h('dataset:write'),json={'artifact_id':'33333333-3333-3333-3333-333333333333','sha256':'a'*64,'case_count':2}).json();vid=v['id']
  b=c.post('/v1/agent-builds',headers=h('build:write'),json={'name':'candidate','build_sha256':'b'*64,'tool_manifest_sha256':'c'*64,'prompt_version':'p1'}).json();bid=b['id']
  base=c.post('/v1/evaluation-runs',headers=h('evaluation:run'),json={'dataset_version_id':vid,'agent_build_id':bid,'grader_sha256':'d'*64}).json();cand=c.post('/v1/evaluation-runs',headers=h('evaluation:run'),json={'dataset_version_id':vid,'agent_build_id':bid,'grader_sha256':'e'*64}).json()
  cases=c.get(f"/v1/evaluation-runs/{cand['id']}/cases",headers=h('evaluation:read')).json()['items'];assert len(cases)==2 and all(x['trace_digest'] for x in cases)
  comp=c.post(f"/v1/evaluation-runs/{cand['id']}/comparisons",headers=h('evaluation:compare'),json={'baseline_run_id':base['id'],'policy_version':'deterministic-v1'}).json();ver=c.get(f"/v1/comparisons/{comp['id']}/ci-verdict",headers=h('evaluation:read')).json();assert ver['verdict']=='PASS'
def test_missing_scope_and_tenant_fail_closed(tmp_path):
 app=create_app(str(tmp_path/'db.sqlite'),seed=True)
 with TestClient(app) as c:
  assert c.post('/v1/datasets',headers=h('evaluation:run'),json={'name':'x'}).status_code==403
  assert c.post('/v1/datasets',headers=h('dataset:create','00000000-0000-0000-0000-000000000099'),json={'name':'x'}).status_code==403



def test_version_numbers_and_real_verdict_signature(tmp_path,monkeypatch):
 import base64,hashlib,os
 from cryptography.hazmat.primitives import serialization
 from cryptography.exceptions import InvalidSignature
 import pytest
 with TestClient(create_app(str(tmp_path/'signed.sqlite'),seed=True)) as c:
  d=c.post('/v1/datasets',headers=h('dataset:create'),json={'name':'golden'}).json()
  versions=[c.post(f"/v1/datasets/{d['id']}/versions",headers=h('dataset:write'),json={'artifact_id':'33333333-3333-3333-3333-333333333333','sha256':str(i)*64,'case_count':2}).json() for i in (1,2)]
  assert [v['version_number'] for v in versions]==[1,2]
  b=c.post('/v1/agent-builds',headers=h('build:write'),json={'name':'candidate','build_sha256':'b'*64,'tool_manifest_sha256':'c'*64,'prompt_version':'p1'}).json()
  runs=[c.post('/v1/evaluation-runs',headers=h('evaluation:run'),json={'dataset_version_id':versions[0]['id'],'agent_build_id':b['id'],'grader_sha256':sha*64}).json() for sha in ('d','e')]
  comp=c.post(f"/v1/evaluation-runs/{runs[1]['id']}/comparisons",headers=h('evaluation:compare'),json={'baseline_run_id':runs[0]['id'],'policy_version':'deterministic-v1'}).json()
  url=f"/v1/comparisons/{comp['id']}/ci-verdict"
  signed=c.get(url,headers=h('evaluation:read')).json()
  key=serialization.load_pem_private_key(os.environ['CI_VERDICT_SIGNING_KEY_PEM'].encode(),password=None).public_key()
  body=signed['signed_payload'].encode()
  assert hashlib.sha256(body).hexdigest()==signed['signed_artifact_sha256']
  key.verify(base64.urlsafe_b64decode(signed['signature']),body)
  with pytest.raises(InvalidSignature):key.verify(base64.urlsafe_b64decode(signed['signature']),body+b'changed')
  monkeypatch.delenv('CI_VERDICT_SIGNING_KEY_PEM')
  assert c.get(url,headers=h('evaluation:read')).status_code==503
