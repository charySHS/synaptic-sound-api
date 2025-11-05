# Imports
from fastapi import APIRouter, UploadFile, File, Form, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import MoodEntry, User
from spotify_helpers import AutoCreatePlaylistIfEnabled, EnsureFreshAccessToken
from security import verify_session_jwt

import random

# ---------------------------------------------------------------------
# -- Mood Routes
# ---------------------------------------------------------------------

router = APIRouter()

MOODS = ["happy", "sad", "energetic", "chill", "romantic", "neutral"]
EMOJI_TO_MOOD = {"😊": "happy", "😔": "sad", "🔥": "energetic", "😎": "chill", "❤️": "romantic"}

def _require_user(request: Request, db: Session) -> User:
    token = request.cookies.get("ss_session")
    sid = verify_session_jwt(token) if token else None
    if not sid:
        raise HTTPException(status_code=401, detail="Login required.")

    user : User | None = db.query(User).filter_by(spotify_id=sid).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found.")

    EnsureFreshAccessToken(user, db)

    return user

@router.post("/emoji")
def mood_from_emoji(request: Request, emoji: str = Form(...), db: Session = Depends(get_db)):
    user = _require_user(request, db)
    detected = EMOJI_TO_MOOD.get(emoji, "neutral")
    entry = MoodEntry(user_id=user.id, emoji=emoji, detected_mood=detected, confidence=None)
    db.add(entry); db.commit(); db.refresh(entry)

    playlist_url = AutoCreatePlaylistIfEnabled(user, detected, db)
    if playlist_url:
        entry.playlist = entry.playlist or None

    return {"detected_mood": detected, "entry_id": entry.id, "playlist_url": playlist_url}

@router.post("/selfie")
def mood_from_selfie(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = _require_user(request, db)

    # TODO: Utilize DeepFace later
    detected = random.choice(MOODS)
    entry = MoodEntry(user_id=user.id, image_url=file.filename, detected_mood=detected, confidence=None)
    db.add(entry); db.commit(); db.refresh(entry)

    playlist_url = AutoCreatePlaylistIfEnabled(user, detected, db)

    return {"detected_mood": detected, "entry_id": entry.id, "playlist_url": playlist_url}
