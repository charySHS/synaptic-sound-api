# Imports
from sqlalchemy.orm import Session
from security import encrypt_token, decrypt_token
from models import User, Playlist

import os, datetime, requests

# -----------------------------------------------------------------------------
# -- Spotify Helpers
# -----------------------------------------------------------------------------

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "https://synaptic-sound.com/callback")

def GetOrCreateUser(spotify_id: str, db: Session, display_name=None) -> User:
    user = db.query(User).filter_by(spotify_id=spotify_id).first()
    if not user:
        user = User(spotify_id=spotify_id, display_name=display_name)
        db.add(user); db.commit(); db.refresh(user)

    return user

def _get_refresh_token(user: User) -> str | None:
    if not user.refresh_token_enc:
        return None

    return decrypt_token(user.refresh_token_enc)

def _set_refresh_token(user: User, refresh_token: str, db: Session) -> None:
    user.refresh_token_enc = encrypt_token(refresh_token)
    db.commit(); db.refresh(user)

def EnsureFreshAccessToken(user: User, db: Session) -> str | None:
    if user.access_token and user.token_expires_at:
        delta = (user.token_expires_at - datetime.datetime.now()).total_seconds()
        if delta > 300:   # > 5 minutes left
            return user.access_token

    refresh_token = _get_refresh_token(user)
    if not refresh_token:
        return None

    r = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": SPOTIFY_CLIENT_ID,
            "client_secret": SPOTIFY_CLIENT_SECRET,
        },
    )

    if r.status_code != 200:
        return None

    data = r.json()
    user.access_token = data.get("access_token")
    if data.get("refresh_token"):
        _set_refresh_token(user, data["refresh_token"], db)

    user.token_expires_at = datetime.datetime.now() + datetime.timedelta(seconds=data.get("expires_in", 3600))
    db.commit(); db.refresh(user)

    return user.access_token

def AutoCreatePlaylistIfEnabled(user: User, mood: str, db: Session) -> str | None:
    if not user.auto_create_enabled:
        return None

    token = EnsureFreshAccessToken(user, db)
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    name = f"{mood.capitalize()} Vibes 🎧"
    payload = {"name": name, "description": f"Synaptic Sound - mood: {mood}", "public": True}
    r = requests.post(f"https://api.spotify.com/v1/users/{user.spotify_id}/playlists", headers=headers, json=payload)
    if r.status_code not in (200, 201):
        return None

    pl = r.json()
    rec = Playlist(
        user_id=user.id,
        playlist_name=pl["name"],
        playlist_url=pl["external_urls"]["spotify"],
    )

    db.add(rec); db.commit(); db.refresh(rec)

    return rec.playlist_url