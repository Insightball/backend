from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="INSIGHTBALL API",
    description="API Backend pour la plateforme INSIGHTBALL",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.database import Base, engine
from app.models import User, Club, Match, Player, Notification

@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")

@app.get("/")
async def root():
    return {
        "message": "INSIGHTBALL API v1.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Routes publiques
from app.routes import auth, matches, upload, players, clubs, notifications, subscription

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(players.router, prefix="/api/players", tags=["players"])
app.include_router(clubs.router, prefix="/api/clubs", tags=["clubs"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(subscription.router, prefix="/api/subscription", tags=["subscription"])

# Route admin — invisible dans /docs (include_in_schema=False)
from app.routes import admin
app.include_router(admin.router, prefix="/api/x-admin", include_in_schema=False)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
