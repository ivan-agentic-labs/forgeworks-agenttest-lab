"""Upload real JSONL bytes, commit and bind an immutable dataset version."""
import hashlib
from fastapi.testclient import TestClient
from agenttest_lab.main import create_app, auth
from agenttest_lab.infrastructure.store import TENANT, USER
from agenttest_lab.infrastructure.object_storage import ObjectStorage


def test_s3_dataset_upload_commit_and_version(tmp_path,monkeypatch):
    for key,value in {"S3_ENDPOINT":"https://storage.example.invalid","S3_BUCKET":"private-bucket","S3_ACCESS_KEY_ID":"synthetic-access","S3_SECRET_ACCESS_KEY":"synthetic-secret"}.items():
        monkeypatch.setenv(key,value)
    data={}
    def transfer(self,method,key,body=None):
        if method=="PUT":data[key]=body;return b""
        return data[key]
    monkeypatch.setattr(ObjectStorage,"transfer",transfer)
    app=create_app(str(tmp_path/'test.db'),seed=True)
    app.dependency_overrides[auth]=lambda:{"tenant_id":TENANT,"sub":USER,"scope":"dataset:create dataset:write artifact:create artifact:commit artifact:read artifact:download"}
    monkeypatch.setenv("APP_ENV","staging")
    source=b'{"case_key":"uploaded-case","input":"hello","expected":"hello"}\n'
    digest=hashlib.sha256(source).hexdigest()
    with TestClient(app) as client:
        dataset=client.post('/v1/datasets',json={"name":"Uploaded dataset"}).json()['id']
        intent=client.post('/v1/artifacts/upload-intents',json={"kind":"dataset","filename":"cases.jsonl","size_bytes":len(source),"sha256":digest}).json()
        uploaded=client.put(intent['upload_url'],content=source)
        assert uploaded.status_code==201,uploaded.text
        commit=client.post('/v1/artifacts/'+intent['artifact_id']+'/commit',json={"sha256":digest,"size_bytes":len(source),"object_generation":uploaded.json()['object_generation']})
        assert commit.status_code==200 and commit.json()['status']=='AVAILABLE',commit.text
        version=client.post('/v1/datasets/'+dataset+'/versions',json={"artifact_id":intent['artifact_id'],"sha256":digest,"case_count":1})
        assert version.status_code==201,version.text
        download=client.post('/v1/artifacts/'+intent['artifact_id']+'/download-intents')
        assert download.status_code==201,download.text
        assert client.get(download.json()['download_url']).content==source
        assert data and all(key.startswith('agenttest-lab/') for key in data)
