# Imports
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from typing import Optional

import base64, os, time
import jwt

# -----------------------------------------------------------------------------
# -- Security
# -----------------------------------------------------------------------------

key_b64 = os.getenv("ENCRYPTION_KEY", "")
if not key_b64:
    raise RuntimeError("ENCRYPTION_KEY must be set")

AES_KEY = base64.b64decode(key_b64) # 32 bytes

def encrypt_token(plaintext: str) -> str:
    aes = AESGCM(AES_KEY)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode(), None)

    return base64.b64encode(nonce + ct).decode()

def decrypt_token(blob_64: str) -> str:
    raw = base64.b64decode(blob_64)
    nonce, ct = raw[:12], raw[12:]
    aes = AESGCM(AES_KEY)

    return aes.decrypt(nonce, ct, None).decode()


SESSION_SECRET = os.getenv("SESSION_SECRET", "")
if not SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET must be set")

ISS = "synaptic-sound-api"

def issue_session_jwt(spotify_id: str, ttl_sec: int = 60 * 60 * 24 * 30) -> str:
    now = int(time.time())
    payload = {"iss": ISS, "sub": "session", "spotify_id": spotify_id, "iat": now, "exp": now + ttl_sec}

    return jwt.encode(payload, SESSION_SECRET, algorithm="HS256")

def verify_session_jwt(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=["HS256"], options={"require": ["exp", "iat"]})
        if payload.get("iss") != ISS or payload.get("sub") != "session":
            return None

        return payload.get("spotify_id")
    except jwt.PyJWTError:
        return None
