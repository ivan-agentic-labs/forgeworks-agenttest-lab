from __future__ import annotations
import base64
import hashlib
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException


def sign_export(document: str, expected_sha: str) -> dict:
    payload = document.encode('utf-8')
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        raise HTTPException(409, detail={'code':'VERDICT_INTEGRITY_FAILURE','detail':'Immutable verdict export digest mismatch'})
    try:
        key = serialization.load_pem_private_key(os.environ['CI_VERDICT_SIGNING_KEY_PEM'].encode(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError('Expected Ed25519')
    except (KeyError, ValueError, TypeError):
        raise HTTPException(503, detail={'code':'VERDICT_SIGNER_NOT_CONFIGURED','detail':'An Ed25519 signing key must be configured outside the repository'})
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {'signature_algorithm':'Ed25519','signature':base64.urlsafe_b64encode(key.sign(payload)).decode(), 'signing_key_id':hashlib.sha256(public).hexdigest(),'signed_payload':document}
