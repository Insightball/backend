from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
import uuid
import resend
import os

from app.database import get_db
from app.models import User, Club, PlanType
from app.schemas import UserSignup, UserLogin, Token, UserResponse
from app.utils.auth import verify_password, get_password_hash, create_access_token
from app.dependencies import get_current_user
from app.config import settings

router = APIRouter()

# Resend setup
resend.api_key = os.getenv("RESEND_API_KEY")


def send_welcome_email(user_name: str, user_email: str, plan: str):
    """Envoie un email de bienvenue après inscription"""
    try:
        plan_label = "Coach" if plan == "coach" else "Club"
        resend.Emails.send({
            "from": "INSIGHTBALL <contact@insightball.com>",
            "to": user_email,
            "subject": "Bienvenue sur INSIGHTBALL 🎉",
            "html": f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0f1117; color: #e2e8f0; padding: 40px; border-radius: 12px;">
                <div style="text-align: center; margin-bottom: 32px;">
                    <h1 style="color: #c9a227; font-size: 28px; margin: 0; font-family: monospace; letter-spacing: .06em;">⚽ INSIGHTBALL</h1>
                </div>
                
                <h2 style="font-size: 22px; margin-bottom: 8px;">Bienvenue, {user_name} ! 👋</h2>
                <p style="color: #94a3b8; line-height: 1.6;">
                    Ton compte <strong style="color: #e2e8f0;">Plan {plan_label}</strong> est prêt. 
                    Tu peux dès maintenant analyser tes matchs, suivre tes joueurs et améliorer les performances de ton équipe.
                </p>

                <div style="background: #1a1d27; border: 1px solid #2d3148; border-radius: 8px; padding: 24px; margin: 24px 0;">
                    <h3 style="margin: 0 0 12px 0; color: #c9a227;">Ce que tu peux faire :</h3>
                    <ul style="color: #94a3b8; line-height: 2; padding-left: 20px; margin: 0;">
                        <li>📹 Uploader et analyser tes matchs</li>
                        <li>👥 Gérer tes joueurs et leurs stats</li>
                        <li>📊 Visualiser les performances</li>
                        <li>🗺️ Créer des compositions tactiques</li>
                    </ul>
                </div>

                <div style="text-align: center; margin-top: 32px;">
                    <a href="https://www.insightball.com/dashboard" 
                       style="background: #c9a227; color: #0f0f0d; padding: 14px 32px; border-radius: 4px; text-decoration: none; font-weight: bold; font-size: 14px; font-family: monospace; letter-spacing: .08em; text-transform: uppercase;">
                        Accéder à mon dashboard →
                    </a>
                </div>

                <p style="color: #475569; font-size: 12px; text-align: center; margin-top: 32px;">
                    Une question ? Réponds à cet email ou contacte-nous à contact@insightball.com
                </p>
            </div>
            """
        })
    except Exception as e:
        print(f"⚠️ Email de bienvenue non envoyé : {e}")


@router.post("/signup", response_model=Token)
async def signup(user_data: UserSignup, db: Session = Depends(get_db)):
    """Create a new user account"""

    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create club if CLUB plan
    club = None
    if user_data.plan == PlanType.CLUB:
        if not user_data.club_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Club name is required for CLUB plan"
            )

        club = Club(
            id=str(uuid.uuid4()),
            name=user_data.club_name,
            quota_matches=10
        )
        db.add(club)
        db.flush()

    # Create user
    user = User(
        id=str(uuid.uuid4()),
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        name=user_data.name,
        plan=user_data.plan,
        club_id=club.id if club else None
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Envoyer email de bienvenue
    send_welcome_email(user.name, user.email, user.plan.value)

    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token"""

    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # Update last_login
    from datetime import datetime
    user.last_login = datetime.utcnow()
    db.commit()

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user info"""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        plan=current_user.plan.value,
        role=current_user.role.value if current_user.role else None,
        club_name=current_user.club.name if current_user.club else None,
        club_id=current_user.club_id,
    )
