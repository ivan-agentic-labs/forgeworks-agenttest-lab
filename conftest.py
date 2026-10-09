# Explicit synthetic credentials used only by automated tests.
import os
from pathlib import Path
import sys
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AUTH_MODE", "development")
os.environ.setdefault("DEV_AUTH_SECRET", "forgeworks-development-secret-32-plus")
os.environ.setdefault("AUTH_ISSUER", "https://issuer.synthetic.invalid")
os.environ.setdefault("AUTH_AUDIENCE", "forgeworks-api")
os.environ.setdefault("ARTIFACT_SIGNING_SECRET", "synthetic-artifact-signing-secret-for-tests-only")
ROOT = Path(__file__).resolve().parent
for path in (ROOT / "apps/worker/src", ROOT / "apps/api/src"):
    sys.path.insert(0, str(path))

os.environ.setdefault("AGENTTEST_SYNTHETIC_MODE", "1")
# Generate ephemeral signing material at test runtime; no private key is committed.
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
os.environ.setdefault("CI_VERDICT_SIGNING_KEY_PEM", Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
