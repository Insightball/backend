from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
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
resend.api_key = os.getenv("RESEND_API_KEY")


def send_welcome_email(user_name: str, user_email: str, plan: str):
    try:
        plan_label = "Coach" if plan == "coach" else "Club"
        resend.Emails.send({
            "from": "INSIGHTBALL <contact@insightball.com>",
            "to": user_email,
            "subject": f"Bienvenue sur INSIGHTBALL — Plan {plan_label}",
            "html": f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0a0908;font-family:monospace;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0908;padding:40px 20px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
        <tr>
          <td style="padding:0 0 32px 0;">
            <span style="font-size:22px;font-weight:900;letter-spacing:.06em;color:#f5f2eb;font-family:monospace;">
              INSIGHT<span style="color:#c9a227;">BALL</span>
            </span>
          </td>
        </tr>
        <tr>
          <td style="background:#0f0e0c;border:1px solid rgba(255,255,255,0.07);border-top:2px solid #c9a227;padding:36px 32px;">
            <p style="margin:0 0 8px 0;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#c9a227;font-family:monospace;">Plan {plan_label}</p>
            <h1 style="margin:0 0 20px 0;font-size:32px;text-transform:uppercase;color:#f5f2eb;font-family:monospace;letter-spacing:.03em;line-height:1.1;">
              Bienvenue,<br/>{user_name} !
            </h1>
            <div style="width:40px;height:2px;background:#c9a227;margin-bottom:24px;"></div>
            <p style="margin:0 0 28px 0;font-size:13px;color:rgba(245,242,235,0.55);line-height:1.7;font-family:monospace;letter-spacing:.03em;">
              Ton compte est prêt. Tu peux dès maintenant analyser tes matchs,
              suivre tes joueurs et améliorer les performances de ton équipe.
            </p>
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:32px;">
              <tr>
                <td style="background:rgba(201,162,39,0.06);border:1px solid rgba(201,162,39,0.15);padding:20px 24px;">
                  <p style="margin:0 0 12px 0;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:#c9a227;font-family:monospace;">Ce que tu peux faire</p>
                  {''.join([f'<p style="margin:0 0 8px 0;font-size:12px;color:rgba(245,242,235,0.6);font-family:monospace;letter-spacing:.03em;">→ {feat}</p>' for feat in ['Uploader et analyser tes matchs', 'Gérer tes joueurs et leurs stats', 'Visualiser les performances', 'Créer des compositions tactiques']])}
                </td>
              </tr>
            </table>
            <table cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#c9a227;">
                  <a href="https://www.insightball.com/x-portal-7f2a/login"
                     style="display:inline-block;padding:14px 32px;color:#0f0f0d;font-family:monospace;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;">
                    ACCÉDER AU DASHBOARD →
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 0 0 0;">
            <p style="margin:0;font-size:10px;color:rgba(245,242,235,0.2);font-family:monospace;letter-spacing:.04em;">
              <a href="mailto:contact@insightball.com" style="color:#c9a227;text-decoration:none;">contact@insightball.com</a>
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
        })
    except Exception as e:
        print(f"⚠️ Email de bienvenue non envoyé : {e}")


@router.post("/signup", response_model=Token)
async def signup(user_data: UserSignup, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    club = None
    if user_data.plan == PlanType.CLUB:
        if not user_data.club_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Club name is required for CLUB plan")
        club = Club(id=str(uuid.uuid4()), name=user_data.club_name, quota_matches=10)
        db.add(club)
        db.flush()

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

    send_welcome_email(user.name, user.email, user.plan.value)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Compte supprimé — message spécifique avec lien de récupération
    if user.deleted_at:
        if user.recovery_token_expires and datetime.utcnow() > user.recovery_token_expires:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ACCOUNT_PERMANENTLY_DELETED"
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"ACCOUNT_DELETED:{user.recovery_token}"
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    user.last_login = datetime.utcnow()
    db.commit()

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        plan=current_user.plan.value,
        role=current_user.role.value if current_user.role else None,
        club_name=current_user.club.name if current_user.club else None,
        club_id=current_user.club_id,
    )
