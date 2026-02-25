from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
import logging

from app.database import engine, Base
from app.routes import auth, matches, players, clubs, subscription, upload, leads, admin, club_members, account, notifications
from app.models import User, Club, Match
from app.models.club_member import ClubMember

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


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


app = FastAPI(
    title="INSIGHTBALL API",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(GZipMiddleware, minimum_size=1000)

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

app.include_router(auth.router,          prefix="/api/auth",          tags=["auth"])
app.include_router(account.router,       prefix="/api/account",       tags=["account"])
app.include_router(matches.router,       prefix="/api/matches",       tags=["matches"])
app.include_router(players.router,       prefix="/api/players",       tags=["players"])
app.include_router(clubs.router,         prefix="/api/club",          tags=["club"])
app.include_router(club_members.router,  prefix="/api/club/members",  tags=["club-members"])
app.include_router(subscription.router,  prefix="/api/subscription",  tags=["subscription"])
app.include_router(upload.router,        prefix="/api/upload",        tags=["upload"])
app.include_router(leads.router,         prefix="/api/leads",         tags=["leads"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(admin.router,         prefix="/api/x-admin",       tags=["admin"])


@app.get("/", include_in_schema=False)
def root():
    return {"status": "ok", "service": "INSIGHTBALL API"}

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "healthy"}
