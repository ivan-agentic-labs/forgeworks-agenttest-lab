import os
import time
import jwt
from uuid import UUID
from fastapi import HTTPException


def fail(code,status=403):
    raise HTTPException(status_code=status,detail={'type':'about:blank','title':'Artifact transfer rejected','status':status,'code':code,'detail':'Artifact capability is invalid, expired or unavailable','request_id':'runtime'})


def signing_secret():
    secret=os.getenv('ARTIFACT_SIGNING_SECRET','')
    if len(secret.encode())<32 or secret==os.getenv('DEV_AUTH_SECRET'):
        fail('ARTIFACT_SIGNER_NOT_CONFIGURED',503)
    return secret


def issue_download(tenant,actor,rid,sha,session_id=None):
    # Unlike anonymous file links, Supabase user downloads must stop working
    # as soon as the issuing login session is revoked.
    if os.getenv('AUTH_MODE') == 'supabase':
        try:
            session_id = str(UUID(session_id))
        except (ValueError, TypeError, AttributeError):
            fail('ARTIFACT_SESSION_BINDING_REQUIRED',503)
    expiry=int(time.time())+300
    return jwt.encode({'iss':'forgeworks-artifacts','aud':'artifact-download','sub':rid,'tenant_id':tenant,'actor':actor,'sha256':sha,'exp':expiry,'session_id':session_id},signing_secret(),algorithm='HS256'),expiry


def verify_download(token,rid,store=None):
    if not isinstance(token,str) or len(token)>4096:fail('INVALID_ARTIFACT_CAPABILITY')
    try:
        claims=jwt.decode(token,signing_secret(),algorithms=['HS256'],issuer='forgeworks-artifacts',audience='artifact-download',options={'require':['sub','tenant_id','actor','sha256','exp']})
        if claims['sub']!=rid:fail('INVALID_ARTIFACT_CAPABILITY')
    except jwt.PyJWTError:
        fail('INVALID_ARTIFACT_CAPABILITY')
    if os.getenv('AUTH_MODE') == 'supabase':
        try:
            tenant = str(UUID(claims['tenant_id']))
            actor = str(UUID(claims['actor']))
            session_id = str(UUID(claims['session_id']))
        except (KeyError,ValueError,TypeError,AttributeError):
            fail('INVALID_ARTIFACT_CAPABILITY')
        check = getattr(store, 'session_active', None)
        if not callable(check):
            fail('ARTIFACT_SESSION_CHECK_UNAVAILABLE',503)
        try:
            active = check(tenant,actor,session_id)
        except Exception:
            fail('ARTIFACT_SESSION_CHECK_UNAVAILABLE',503)
        if not active:
            fail('ARTIFACT_SESSION_REVOKED',403)
    return claims
