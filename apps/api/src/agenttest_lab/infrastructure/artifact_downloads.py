import os
import time
import jwt
from fastapi import HTTPException


def fail(code,status=403):
    raise HTTPException(status_code=status,detail={'type':'about:blank','title':'Artifact transfer rejected','status':status,'code':code,'detail':'Artifact capability is invalid, expired or unavailable','request_id':'runtime'})


def signing_secret():
    secret=os.getenv('ARTIFACT_SIGNING_SECRET','')
    if len(secret.encode())<32 or secret==os.getenv('DEV_AUTH_SECRET'):
        fail('ARTIFACT_SIGNER_NOT_CONFIGURED',503)
    return secret


def issue_download(tenant,actor,rid,sha):
    expiry=int(time.time())+300
    return jwt.encode({'iss':'forgeworks-artifacts','aud':'artifact-download','sub':rid,'tenant_id':tenant,'actor':actor,'sha256':sha,'exp':expiry},signing_secret(),algorithm='HS256'),expiry


def verify_download(token,rid):
    if len(token)>4096:fail('INVALID_ARTIFACT_CAPABILITY')
    try:
        claims=jwt.decode(token,signing_secret(),algorithms=['HS256'],issuer='forgeworks-artifacts',audience='artifact-download',options={'require':['sub','tenant_id','actor','sha256','exp']})
        if claims['sub']!=rid:fail('INVALID_ARTIFACT_CAPABILITY')
        return claims
    except jwt.PyJWTError:
        fail('INVALID_ARTIFACT_CAPABILITY')
