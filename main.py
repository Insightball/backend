from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="INSIGHTBALL API",
    description="API Backend pour la plateforme INSIGHTBALL",
    version="1.0.0"
)

# CORS Configuration - AVANT les routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "INSIGHTBALL API v1.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy"
    }

# Import routes APRÈS le middleware
from app.routes import auth, matches, upload, players, clubs

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(players.router, prefix="/api/players", tags=["players"])
app.include_router(clubs.router, prefix="/api/clubs", tags=["clubs"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )