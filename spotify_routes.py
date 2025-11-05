# Imports
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from database import get_db
from models import User
from spotify_helpers import EnsureFreshAccessToken
from security import verify_session_jwt

import requests

# -------------------------------------------------------------------------
# -- Spotify Routes
# -------------------------------------------------------------------------

router = APIRouter()

def _auth_headers(user: User, db: Session):
    token = EnsureFreshAccessToken(user, db)
    if not token:
        raise HTTPException(status_code=401, detail="No token.")

    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def _require_user(request: Request, db: Session) -> User:
    token = request.cookies.get("ss_session")
    sid = verify_session_jwt(token) if token else None
    if not sid:
        raise HTTPException(status_code=401, detail="Login required.")

    user: User | None = db.query(User).filter_by(spotify_id=sid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    return user

@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    headers = _auth_headers(user, db)
    r = requests.get("https://api.spotify.com/v1/me", headers=headers)

    return r.json()
