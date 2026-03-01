from fastapi import APIRouter, Depends, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
import resend
import os

import urllib.request
import urllib.error
import urllib.parse
import json as _json

from app.database import get_db
from app.models import User, Club, PlanType
from app.schemas import UserSignup, UserLogin, Token, UserResponse
from app.utils.auth import verify_password, get_password_hash, create_access_token
from app.dependencies import get_current_user
from app.config import settings

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
resend.api_key = os.getenv("RESEND_API_KEY")

# Source de vérité pour les quotas — aligné avec matches.py
PLAN_QUOTAS = {
    PlanType.COACH: 4,
    PlanType.CLUB: 12,
}


def _verify_recaptcha(token: str) -> bool:
    """Vérifie le token reCAPTCHA v3 auprès de Google. Score >= 0.5 = humain."""
    secret = os.getenv("RECAPTCHA_SECRET_KEY")
    if not secret:
        return True  # Pas de clé configurée → on laisse passer (dev local)
    if not token:
        return False
    try:
        data = urllib.parse.urlencode({
            "secret": secret,
            "response": token,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://www.google.com/recaptcha/api/siteverify",
            data=data,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            result = _json.loads(r.read().decode("utf-8"))
            return result.get("success", False) and result.get("score", 0) >= 0.5
    except Exception as e:
        print(f"[ERR] reCAPTCHA verify failed: {e}")
        return True  # Fail open — ne pas bloquer les vrais users si Google est down


def send_welcome_email(user_name: str, user_email: str, plan: str):
    try:
        plan_label = "Coach" if plan == "COACH" else "Club"
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
@limiter.limit("3/minute")
async def signup(request: Request, user_data: UserSignup, db: Session = Depends(get_db)):
    # ── reCAPTCHA v3 — anti-bot (activé uniquement si RECAPTCHA_SECRET_KEY configuré) ──
    recaptcha_token = getattr(user_data, 'recaptcha_token', None) or ''
    if os.getenv("RECAPTCHA_SECRET_KEY") and not _verify_recaptcha(recaptcha_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vérification anti-bot échouée. Réessayez."
        )

    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # ── Validation mot de passe (aligné avec reset-password) ──
    if len(user_data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le mot de passe doit contenir au moins 8 caractères"
        )

    club = None
    if user_data.plan == PlanType.CLUB:
        if not user_data.club_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Club name is required for CLUB plan")
        # ── FIX : quota_matches aligné avec PLAN_QUOTAS (était hardcodé à 10) ──
        club = Club(id=str(uuid.uuid4()), name=user_data.club_name, quota_matches=PLAN_QUOTAS[PlanType.CLUB])
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
@limiter.limit("5/minute")
async def login(request: Request, credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Compte supprimé
    if user.deleted_at:
        if user.recovery_token_expires and datetime.utcnow() > user.recovery_token_expires:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ACCOUNT_PERMANENTLY_DELETED")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"ACCOUNT_DELETED:{user.recovery_token}")

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
        club_logo=current_user.club.logo_url if current_user.club else None,
        profile_role=current_user.profile_role,
        profile_level=current_user.profile_level,
        profile_phone=current_user.profile_phone,
        profile_city=current_user.profile_city,
        profile_diploma=current_user.profile_diploma,
        trial_ends_at=current_user.trial_ends_at.isoformat() if current_user.trial_ends_at else None,
        trial_match_used=current_user.trial_match_used,
    )


def send_reset_email(user_name: str, user_email: str, reset_token: str):
    try:
        reset_url = f"https://www.insightball.com/reset-password?token={reset_token}"
        resend.Emails.send({
            "from": "INSIGHTBALL <contact@insightball.com>",
            "to": user_email,
            "subject": "Réinitialisation de votre mot de passe — INSIGHTBALL",
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
            <p style="margin:0 0 8px 0;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#c9a227;font-family:monospace;">Sécurité du compte</p>
            <h1 style="margin:0 0 20px 0;font-size:28px;text-transform:uppercase;color:#f5f2eb;font-family:monospace;letter-spacing:.03em;line-height:1.1;">
              Réinitialiser<br/>votre mot de passe
            </h1>
            <div style="width:40px;height:2px;background:#c9a227;margin-bottom:24px;"></div>
            <p style="margin:0 0 28px 0;font-size:13px;color:rgba(245,242,235,0.55);line-height:1.7;font-family:monospace;letter-spacing:.03em;">
              Bonjour {user_name},<br/><br/>
              Vous avez demandé la réinitialisation de votre mot de passe.
              Ce lien est valable <strong style="color:#f5f2eb;">30 minutes</strong>.
            </p>
            <table cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
              <tr>
                <td style="background:#c9a227;">
                  <a href="{reset_url}"
                     style="display:inline-block;padding:14px 32px;color:#0f0f0d;font-family:monospace;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;">
                    RÉINITIALISER MON MOT DE PASSE →
                  </a>
                </td>
              </tr>
            </table>
            <p style="margin:0;font-size:11px;color:rgba(245,242,235,0.30);font-family:monospace;line-height:1.6;">
              Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.<br/>
              Votre mot de passe restera inchangé.
            </p>
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
        print(f"⚠️ Email reset non envoyé : {e}")


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, body: dict, db: Session = Depends(get_db)):
    email = body.get("email", "").strip().lower()
    # Toujours répondre 200 pour ne pas révéler si l'email existe
    user = db.query(User).filter(User.email == email, User.deleted_at == None).first()
    if user:
        reset_token = str(uuid.uuid4())
        user.recovery_token = reset_token
        user.recovery_token_expires = datetime.utcnow() + timedelta(minutes=30)
        db.commit()
        send_reset_email(user.name, user.email, reset_token)
    return {"message": "Si cet email existe, un lien a été envoyé."}


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, body: dict, db: Session = Depends(get_db)):
    token = body.get("token", "").strip()
    new_password = body.get("password", "").strip()

    if not token or not new_password or len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Token ou mot de passe invalide")

    user = db.query(User).filter(
        User.recovery_token == token,
        User.deleted_at == None
    ).first()

    if not user:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré")

    if user.recovery_token_expires and datetime.utcnow() > user.recovery_token_expires:
        raise HTTPException(status_code=400, detail="Lien expiré")

    user.hashed_password = get_password_hash(new_password)
    user.recovery_token = None
    user.recovery_token_expires = None
    db.commit()

    return {"message": "Mot de passe réinitialisé avec succès"}
