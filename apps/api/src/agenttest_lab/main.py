from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime,timezone
from uuid import UUID
from typing import Annotated
import jwt
from fastapi import FastAPI,Depends,Header,HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field
from agenttest_lab.infrastructure.store import Store
ROOT=Path(__file__).resolve().parents[4]
class Dataset(BaseModel):model_config=ConfigDict(extra='forbid');name:str
class Version(BaseModel):model_config=ConfigDict(extra='forbid');artifact_id:UUID;sha256:str=Field(pattern=r'^[0-9a-f]{64}$');case_count:int=Field(ge=1)
class Build(BaseModel):model_config=ConfigDict(extra='forbid');name:str;build_sha256:str=Field(pattern=r'^[0-9a-f]{64}$');tool_manifest_sha256:str=Field(pattern=r'^[0-9a-f]{64}$');prompt_version:str
class Run(BaseModel):model_config=ConfigDict(extra='forbid');dataset_version_id:UUID;agent_build_id:UUID;grader_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
class Compare(BaseModel):model_config=ConfigDict(extra='forbid');baseline_run_id:UUID;policy_version:str
def reject(status,code,detail):raise HTTPException(status_code=status,detail={'type':'about:blank','title':'Request rejected','status':status,'code':code,'detail':detail,'request_id':'runtime'})
def auth(authorization:Annotated[str|None,Header()]=None):
 if not authorization or not authorization.startswith('Bearer '):reject(401,'UNAUTHENTICATED','Bearer token is required')
 try:return jwt.decode(authorization[7:],os.getenv('DEV_AUTH_SECRET','forgeworks-development-secret-32-plus'),algorithms=['HS256'],issuer=os.getenv('AUTH_ISSUER','https://issuer.synthetic.invalid'),audience=os.getenv('AUTH_AUDIENCE','forgeworks-api'))
 except jwt.PyJWTError:reject(401,'INVALID_TOKEN','Token signature, issuer, audience, or expiry is invalid')
def scope(required,store):
 def dep(c=Depends(auth)):
  if not c.get('tenant_id') or not c.get('sub') or not store.member(c['tenant_id'],c['sub']):reject(403,'TENANT_CONTEXT_INVALID','Verified membership is required')
  if required not in set(str(c.get('scope','')).split()):reject(403,'INSUFFICIENT_SCOPE',f'Scope {required} is required')
  return c
 return dep
def create_app(db_path=None,seed=False):
 store=Store(db_path or os.getenv('AGENTTEST_DB_PATH',str(ROOT/'.runtime/agenttest.db')))
 if seed:store.seed()
 app=FastAPI(title='AgentTest Lab MVP',version='0.1.0');app.state.store=store
 @app.exception_handler(HTTPException)
 async def errors(_,e):return JSONResponse(status_code=e.status_code,content=e.detail if isinstance(e.detail,dict) else {'type':'about:blank','title':'Request rejected','status':e.status_code,'code':'REQUEST_REJECTED','detail':str(e.detail),'request_id':'runtime'})
 @app.get('/healthz')
 def health():return {'status':'ok','service':'agenttest-lab'}
 @app.post('/v1/datasets',status_code=201)
 def dataset(body:Dataset,c=Depends(scope('dataset:create',store))):
  did=store.dataset(c['tenant_id'],body.name,c['sub']);return {'id':did,'status':'ACTIVE','created_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'name':body.name,'owner_id':c['sub'],'latest_version':0}
 @app.post('/v1/datasets/{did}/versions',status_code=201)
 def version(did:UUID,body:Version,c=Depends(scope('dataset:write',store))):
  vid=store.version(c['tenant_id'],str(did),body.sha256,body.case_count);return {'id':vid,'status':'IMMUTABLE','created_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'dataset_id':str(did),'version_number':1,'sha256':body.sha256,'case_count':body.case_count}
 @app.post('/v1/agent-builds',status_code=201)
 def build(body:Build,c=Depends(scope('build:write',store))):
  bid=store.build(c['tenant_id'],body.name,body.build_sha256,body.tool_manifest_sha256,body.prompt_version);return {'id':bid,'status':'REGISTERED','created_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'name':body.name,'build_sha256':body.build_sha256,'tool_manifest_sha256':body.tool_manifest_sha256,'prompt_version':body.prompt_version}
 @app.post('/v1/evaluation-runs',status_code=202)
 def run(body:Run,c=Depends(scope('evaluation:run',store))):
  r=store.run(c['tenant_id'],str(body.dataset_version_id),str(body.agent_build_id),body.grader_sha256);return {'id':r['id'],'status':r['status'],'created_at':r['created_at'],'dataset_version_id':r['version_id'],'agent_build_id':r['build_id'],'grader_sha256':r['grader_sha'],'job_id':r['job_id']}
 @app.get('/v1/evaluation-runs/{rid}/cases')
 def cases(rid:UUID,c=Depends(scope('evaluation:read',store))):
  items=[{'id':x['id'],'run_id':x['run_id'],'case_key':x['case_key'],'grade_status':x['grade_status'],'score':x['score'],'grader_sha256':x['grader_sha'],'trace_digest':x['trace_digest']} for x in store.cases(c['tenant_id'],str(rid))];return {'items':items,'next_cursor':None,'has_more':False}
 @app.post('/v1/evaluation-runs/{rid}/comparisons',status_code=201)
 def compare(rid:UUID,body:Compare,c=Depends(scope('evaluation:compare',store))):
  row=store.compare(c['tenant_id'],str(rid),str(body.baseline_run_id),body.policy_version);return {'id':row['id'],'status':'COMPUTED','created_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'baseline_run_id':row['baseline_id'],'candidate_run_id':row['candidate_id'],'paired_case_count':row['paired'],'missing_case_count':row['missing'],'delta_score':row['delta'],'policy_version':row['policy']}
 @app.get('/v1/comparisons/{cid}/ci-verdict')
 def verdict(cid:UUID,c=Depends(scope('evaluation:read',store))):
  row=store.comparison(c['tenant_id'],str(cid))
  if not row:return reject(404,'RESOURCE_NOT_FOUND','Comparison is not visible')
  return {'id':row['id'],'status':'SIGNED','created_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'comparison_id':row['id'],'verdict':row['verdict'],'policy_version':row['policy'],'signed_artifact_sha256':row['artifact_sha']}
 @app.get('/v1/jobs/{jid}')
 def job(jid:UUID,c=Depends(scope('job:read',store))):
  with store.conn() as db:r=db.execute('SELECT * FROM runs WHERE tenant_id=? AND job_id=?',(c['tenant_id'],str(jid))).fetchone()
  if not r:return reject(404,'RESOURCE_NOT_FOUND','Job is not visible')
  return {'id':r['job_id'],'kind':'evaluation','state':r['status'],'created_at':r['created_at'],'state_version':1,'attempt_count':1,'last_error_code':None}
 return app
app=create_app(seed=os.getenv('AGENTTEST_SEED_FIXTURE','0')=='1')
