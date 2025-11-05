# Imports
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine
from auth_routes import router as auth_router
from mood_routes import router as mood_router
from spotify_routes import router as spotify_router

# ----------------------------------------------------------------------------------
# -- Main
# ----------------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Synaptic Sound Backend", version="1.0.0")

ALLOWED_ORIGINS = [
    "https://synaptic-sound.com",
    "https://www.synaptic-sound.com",
]

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True, "service": "Synaptic Sound API"}

@app.get("/.well-known/health")
def health():
    return {"status": "healthy"}

# Routers
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(mood_router, prefix="/mood", tags=["Mood"])
app.include_router(spotify_router, prefix="/spotify", tags=["Spotify"])
