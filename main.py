from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
import logging

from app.database import engine, Base
from app.routes import auth, matches, players, club, stats, admin, club_members
from app.routes import account
from app.models import User, Club, Match
from app.models.club_member import ClubMember

logger = logging.getLogger(__name__)


def run_cleanup():
    try:
        from app.tasks.cleanup import purge_deleted_accounts
        count = purge_deleted_accounts()
        logger.info(f"Cleanup: {count} compte(s) purgé(s)")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_cleanup, 'cron', hour=3, minute=0)
    scheduler.start()
    print("✅ Scheduler démarré")

    yield
    scheduler.shutdown()


app = FastAPI(title="INSIGHTBALL API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.insightball.com",
        "https://insightball.com",
        "https://insightball.netlify.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,          prefix="/api/auth",         tags=["auth"])
app.include_router(account.router,       prefix="/api/account",      tags=["account"])
app.include_router(matches.router,       prefix="/api/matches",      tags=["matches"])
app.include_router(players.router,       prefix="/api/players",      tags=["players"])
app.include_router(club.router,          prefix="/api/club",         tags=["club"])
app.include_router(club_members.router,  prefix="/api/club/members", tags=["club-members"])
app.include_router(stats.router,         prefix="/api/stats",        tags=["stats"])
app.include_router(admin.router,         prefix="/api/x-admin",      tags=["admin"])


@app.get("/")
def root():
    return {"status": "ok", "service": "INSIGHTBALL API"}

@app.get("/health")
def health():
    return {"status": "healthy"}
