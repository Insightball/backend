from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="INSIGHTBALL API",
    description="API Backend pour la plateforme INSIGHTBALL",
    version="1.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Frontend dev
        "https://insightball.com",  # Production
        "https://*.vercel.app"  # Vercel preview
    ],
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
        "status": "healthy",
        "database": "connected",  # TODO: check real DB connection
        "redis": "connected"  # TODO: check real Redis connection
    }

# Import routes (will be created later)
# from app.routes import auth, matches, clubs, stripe_webhooks
# app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
# app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
# app.include_router(clubs.router, prefix="/api/clubs", tags=["clubs"])
# app.include_router(stripe_webhooks.router, prefix="/api/webhooks", tags=["webhooks"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
