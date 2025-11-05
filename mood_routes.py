# Imports
from fastapi import APIRouter, UploadFile, File, Form, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import MoodEntry, User
from spotify_helpers import AutoCreatePlaylistIfEnabled, EnsureFreshAccessToken
from security import verify_session_jwt
from datetime import datetime, timedelta, timezone

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

@router.get("/history")
def get_mood_history(request: Request, days: int | None = None, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    query = db.query(MoodEntry).filter_by(user_id=user.id).order_by(MoodEntry.created_at.desc())

    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(MoodEntry.created_at >= cutoff)

    moods = query.all()

    return [
        {
            "id": m.id,
            "emoji": m.emoji,
            "detected_mood": m.detected_mood,
            "confidence": m.confidence,
            "created_at": m.created_at.isoformat(),
        }
        for m in moods
    ]

@router.get("/stats")
def get_mood_stats(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)

    results = (
        db.query(MoodEntry.detected_mood, func.count(MoodEntry.id))
        .filter_by(user_id=user.id)
        .group_by(MoodEntry.detected_mood)
        .all()
    )

    total = sum(count for _, count in results)
    stats = [
        {"mood": mood, "count": count, "percent": round((count / total)* 100, 1)}
        for mood, count in results
    ]

    return {"total_entries": total, "stats": stats}

@router.get("/trends")
def get_mood_trends(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)

    results = (
        db.query(func.date(MoodEntry.created_at).label("date"), MoodEntry.detected_mood, func.count(MoodEntry.id).label("count"))
        .filter_by(user_id=user.id)
        .group_by("date", MoodEntry.detected_mood)
        .order_by("date")
        .all()
    )

    grouped = {}
    for date, mood, count in results:
        grouped.setdefault(str(date), {})[mood] = count

    return grouped
