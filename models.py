# Import
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base
from typing import Optional

# ------------------------------------------------------------------------
# -- Models app
# ------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    spotify_id = Column(String, unique=True, nullable=False)
    display_name = Column(String)

    access_token = Column(String)
    refresh_token_enc = Column(String)
    token_expires_at = Column(DateTime)

    auto_create_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    moods = relationship("MoodEntry", back_populates="user", cascade="all,delete")
    playlists = relationship("Playlist", back_populates="user", cascade="all,delete")

class MoodEntry(Base):
    __tablename__ = "mood_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    emoji = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    detected_mood = Column(String, nullable=False)
    confidence: Optional[float] = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="moods")
    playlist = relationship("Playlist", back_populates="moods", uselist=False)

class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    mood_id = Column(Integer, ForeignKey("mood_entries.id", ondelete="SET NULL"))

    playlist_name = Column(String)
    playlist_url = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="playlists")
    mood = relationship("MoodEntry", back_populates="playlists")
