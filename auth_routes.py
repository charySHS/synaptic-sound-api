# Imports
from fastapi import APIRouter, Response, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import User
from spotify_helpers import GetOrCreateUser
from security import issue_session_jwt, verify_session_jwt, encrypt_token
from typing import Literal

import os, datetime, requests

# ----------------------------------------------------------------------------------
# -- Authorization Routes
# ----------------------------------------------------------------------------------

router = APIRouter()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "https://synaptic-sound.com/callback")

COOKIE_NAME = "ss_session"
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", "synaptic-sound.com")
COOKIE_SECURE = True
COOKIE_SAMESITE = "lax"

VALID_SAMESITE: dict[str, Literal["lax", "strict", "none"]] = {
    "lax": "lax",
    "strict": "strict",
    "none": "none",
}

@router.get("/login")
def login():
    scopes = "user-read-email playlist-modify-public playlist-modify-private"
    url = (
        "https://accounts.spotify.com/authorize"
        f"?client_id={SPOTIFY_CLIENT_ID}&response_type=code&redirect_uri={SPOTIFY_REDIRECT_URI}&scope={scopes}"
    )

    return {"auth_url": url}

@router.get("/callback")
def callback(code: str, response: Response, db: Session = Depends(get_db)):
    token_res = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": SPOTIFY_REDIRECT_URI,
            "client_id": SPOTIFY_CLIENT_ID,
            "client_secret": SPOTIFY_CLIENT_SECRET,
        },
    )
    if token_res.status_code != 200:
        raise HTTPException(status_code=400, detail="Token exchange failed.")

    data = token_res.json()

    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    me = requests.get("https://api.spotify.com/v1/me", headers={"Authorization": f"Bearer {access_token}"}).json()
    user = GetOrCreateUser(me["id"], db, display_name=me.get("display_name"))
    user.access_token = access_token
    if refresh_token:
        user.refresh_token_enc = encrypt_token(refresh_token)

    user.token_expires_at = datetime.datetime.now() + datetime.timedelta(seconds=data.get("expires_in", 3600))
    db.commit(); db.refresh(user)

    jwt_cookie = issue_session_jwt(user.spotify_id)

    samesite_value = VALID_SAMESITE.get(str(COOKIE_SAMESITE).lower(), "lax")

    response.set_cookie(
        key=COOKIE_NAME, value=jwt_cookie, httponly=True, secure=COOKIE_SECURE,
        samesite=samesite_value, domain=COOKIE_DOMAIN, max_age=60*60*24*30
    )

    return {"ok": True, "display_name": user.display_name}

@router.get("/session")
def session(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="No session.")

    spotify_id = verify_session_jwt(token)
    if not spotify_id:
        raise HTTPException(status_code=401, detail="Invalid session.")

    user = db.query(User).filter_by(spotify_id=spotify_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    return {"ok": True, "spotify_id": spotify_id, "display_name": user.display_name}

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, domain=COOKIE_DOMAIN)

    return {"ok": True}
