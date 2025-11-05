# Imports
from fastapi import APIRouter, UploadFile, File, Form, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import MoodEntry, User, TrackLog
from spotify_helpers import AutoCreatePlaylistIfEnabled, EnsureFreshAccessToken
from security import verify_session_jwt
from datetime import datetime, timedelta, timezone
from deepface import DeepFace

import tempfile, shutil, os, random, requests

# ---------------------------------------------------------------------
# -- Mood Routes
# ---------------------------------------------------------------------

router = APIRouter()

EMOJI_TO_MOOD = {
    "😊": "happy",
    "😔": "sad",
    "🔥": "energetic",
    "😎": "chill",
    "❤️": "romantic",
    "😤": "confident",
    "😢": "tearful",
    "🤔": "reflective",
    "😌": "relaxed",
    "😩": "stressed",
    "🤩": "excited",
    "😴": "tired",
    "🤗": "grateful",
    "🤯": "overwhelmed"
}

MOODS = list(set(EMOJI_TO_MOOD.values()))

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

    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)

    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f, length=1024 * 1024)

    try:
        analysis = DeepFace.analyze(img_path=temp_path, actions=["emotion"], detector_backend="opencv", enforce_detection=False)
        detected = analysis[0]["dominant_emotion"]
        confidence = float(analysis[0]["emotion"].get(detected, 0))
    except Exception as e:
        print(f"DeepFace analysis failed:  {e}")
        detected = random.choice(MOODS)
        confidence = None

    finally:
        shutil.rmtree(temp_dir)

    entry = MoodEntry(user_id=user.id, image_url=file.filename, detected_mood=detected, confidence=confidence)
    db.add(entry); db.commit(); db.refresh(entry)

    try:
        headers = {"Authorization": f"Bearer {user.access_token}"}
        r = requests.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers)
        if r.status_code == 200:

            data = r.json()
            if data.get("item"):
                item = data["item"]
                track = TrackLog(
                    user_id=user.id,
                    mood_id=entry.id,
                    track_id=item["id"],
                    track_name=item["name"],
                    artist_name=", ".join(a["name"] for a in item["artists"]),
                    album_name=item["album"]["name"],
                    album_image=item["album"]["images"][0]["url"],
                    spotify_url=item["external_urls"]["spotify"]
                )
                db.add(track); db.commit()
    except Exception as e:
        print("Spotify logging failed:", e)

    playlist_url = AutoCreatePlaylistIfEnabled(user, detected, db)

    return {
        "detected_mood": detected,
        "confidence": confidence,
        "entry_id": entry.id,
        "playlist_url": playlist_url
    }

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

    mood_counts = (
        db.query(MoodEntry.detected_mood, func.count(MoodEntry.id))
        .filter_by(user_id=user.id)
        .group_by(MoodEntry.detected_mood)
        .all()
    )

    total = sum(c for _, c in mood_counts)
    mood_stats = [
        {"mood": mood, "count": count, "percent": round(count / total * 100, 1)}
        for mood, count, in mood_counts
    ]

    track_count = db.query(TrackLog).filter_by(user_id=user.id).count()

    return {
        "total_moods": total,
        "total_tracks_logged": track_count,
        "moods": mood_stats,
    }

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

@router.get("/tracks")
def get_tracks(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    tracks = (
        db.query(TrackLog)
        .filter_by(user_id=user.id)
        .order_by(TrackLog.created_at.desc())
        .limit(20)
        .all()
    )

    return [
        {
            "track_name": t.track_name,
            "artist": t.artist_name,
            "album": t.album_name,
            "image": t.album_image,
            "mood": t.mood.detected_mood if t.mood else None,
            "time": t.created_at.isoformat(),
        }
        for t in tracks
    ]
