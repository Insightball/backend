from fastapi import APIRouter, Depends, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
import re
import resend
import os

import urllib.request
import urllib.error
import urllib.parse
import json as _json

from app.database import get_db
from app.models import User, Club, PlanType
from app.models.club_member import ClubMember, InviteStatus
from app.schemas import UserSignup, UserLogin, Token, UserResponse
from app.utils.auth import verify_password, get_password_hash, create_access_token
from app.dependencies import get_current_user
from app.config import settings
from app.constants import PLAN_QUOTAS

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
resend.api_key = os.getenv("RESEND_API_KEY")


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
    """Email post-signup (avant approbation) — template crème, accueil + attente validation."""
    try:
        first_name = user_name.split()[0] if user_name else "Coach"
        resend.Emails.send({
            "from": "Insightball <contact@insightball.com>",
            "to": user_email,
            "subject": "Bienvenue sur Insightball",
            "html": f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f2eb;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f2eb;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">
        <tr>
          <td style="padding:0 0 32px 0;">
            <span style="font-size:22px;font-weight:900;letter-spacing:.06em;color:#1a1916;font-family:'Courier New',monospace;">
              INSIGHT<span style="color:#c9a227;">BALL</span>
            </span>
          </td>
        </tr>
        <tr>
          <td style="background:#ffffff;border:1px solid rgba(26,25,22,0.09);border-top:2px solid #c9a227;padding:36px 32px;">
            <p style="margin:0 0 10px 0;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#c9a227;font-family:'Courier New',monospace;">Inscription confirmée</p>
            <h1 style="margin:0 0 20px 0;font-size:28px;color:#1a1916;font-family:'Courier New',monospace;letter-spacing:.02em;line-height:1.2;">
              Bienvenue,<br/>{first_name} !
            </h1>
            <div style="width:40px;height:2px;background:#c9a227;margin-bottom:24px;"></div>
            <p style="margin:0 0 24px 0;font-size:14px;color:rgba(26,25,22,0.6);line-height:1.75;">
              Merci d'avoir rejoint Insightball.<br/>
              Votre compte est en cours de validation. Vous recevrez un email de confirmation dès que votre accès sera activé.
            </p>
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
              <tr>
                <td style="background:rgba(201,162,39,0.06);border:1px solid rgba(201,162,39,0.18);border-left:3px solid #c9a227;padding:18px 22px;">
                  <p style="margin:0 0 6px 0;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#c9a227;font-family:'Courier New',monospace;font-weight:700;">Prochaine étape</p>
                  <p style="margin:0;font-size:16px;color:#1a1916;font-family:'Courier New',monospace;font-weight:900;letter-spacing:.02em;">Validation en cours</p>
                  <p style="margin:6px 0 0 0;font-size:12px;color:rgba(26,25,22,0.45);">Nous vérifions votre profil. Vous serez notifié très rapidement.</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 0 0 0;">
            <p style="margin:0;font-size:10px;color:rgba(26,25,22,0.3);font-family:'Courier New',monospace;letter-spacing:.04em;">
              Insightball · Du terrain à l'analyse.<br/>
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
        print(f"[WARN] Email de bienvenue non envoyé : {e}")


def _send_admin_new_signup_email(user_name: str, user_email: str, profile_role: str = None, profile_city: str = None, profile_phone: str = None, club_name: str = None):
    """Notification admin — nouvel inscrit en attente de validation."""
    try:
        resend.Emails.send({
            "from": "Insightball <contact@insightball.com>",
            "to": "contact@insightball.com",
            "subject": f"Nouvelle inscription — {user_name}",
            "html": f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0a0908;font-family:monospace;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0908;padding:40px 20px;">
    <tr><td align="center">
      <table width="500" cellpadding="0" cellspacing="0" style="max-width:500px;width:100%;">
        <tr>
          <td style="padding:0 0 24px 0;">
            <span style="font-size:18px;font-weight:900;letter-spacing:.06em;color:#f5f2eb;font-family:monospace;">
              INSIGHT<span style="color:#c9a227;">BALL</span>
            </span>
          </td>
        </tr>
        <tr>
          <td style="background:#0f0e0c;border:1px solid rgba(255,255,255,0.07);border-top:2px solid #c9a227;padding:28px 24px;">
            <p style="margin:0 0 8px 0;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#c9a227;font-family:monospace;">Nouvelle inscription</p>
            <h1 style="margin:0 0 16px 0;font-size:22px;color:#f5f2eb;font-family:monospace;letter-spacing:.02em;line-height:1.2;">
              {user_name}
            </h1>
            <div style="width:40px;height:2px;background:#c9a227;margin-bottom:20px;"></div>
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
              <tr><td style="font-size:11px;color:rgba(245,242,235,0.4);font-family:monospace;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">Email</td><td align="right" style="font-size:12px;color:#f5f2eb;font-family:monospace;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">{user_email}</td></tr>
              <tr><td style="font-size:11px;color:rgba(245,242,235,0.4);font-family:monospace;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">Téléphone</td><td align="right" style="font-size:12px;color:#f5f2eb;font-family:monospace;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">{profile_phone or '—'}</td></tr>
              <tr><td style="font-size:11px;color:rgba(245,242,235,0.4);font-family:monospace;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">Club</td><td align="right" style="font-size:12px;color:#f5f2eb;font-family:monospace;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">{club_name or '—'}</td></tr>
              <tr><td style="font-size:11px;color:rgba(245,242,235,0.4);font-family:monospace;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">Ville</td><td align="right" style="font-size:12px;color:#f5f2eb;font-family:monospace;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">{profile_city or '—'}</td></tr>
              <tr><td style="font-size:11px;color:rgba(245,242,235,0.4);font-family:monospace;padding:8px 0;">Poste</td><td align="right" style="font-size:12px;color:#f5f2eb;font-family:monospace;padding:8px 0;">{profile_role or '—'}</td></tr>
            </table>
            <table cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#c9a227;">
                  <a href="https://insightball.com/admin"
                     style="display:inline-block;padding:12px 24px;color:#0f0f0d;font-family:monospace;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;text-decoration:none;">
                    Valider dans l'admin
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
        })
    except Exception as e:
        print(f"[WARN] Email notif admin non envoyé : {e}")


def _send_account_approved_email(user_name: str, user_email: str):
    """Email envoyé à l'utilisateur quand son compte est approuvé."""
    try:
        first_name = user_name.split()[0] if user_name else "Coach"
        resend.Emails.send({
            "from": "Insightball <contact@insightball.com>",
            "to": user_email,
            "subject": "Ton compte Insightball est activé",
            "html": f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f2eb;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f2eb;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">
        <tr>
          <td style="padding:0 0 32px 0;">
            <span style="font-size:22px;font-weight:900;letter-spacing:.06em;color:#1a1916;font-family:'Courier New',monospace;">
              INSIGHT<span style="color:#c9a227;">BALL</span>
            </span>
          </td>
        </tr>
        <tr>
          <td style="background:#ffffff;border:1px solid rgba(26,25,22,0.09);border-top:2px solid #c9a227;padding:36px 32px;">
            <p style="margin:0 0 10px 0;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#c9a227;font-family:'Courier New',monospace;">Compte activé</p>
            <h1 style="margin:0 0 20px 0;font-size:28px;color:#1a1916;font-family:'Courier New',monospace;letter-spacing:.02em;line-height:1.2;">
              C'est parti,<br/>{first_name} !
            </h1>
            <div style="width:40px;height:2px;background:#c9a227;margin-bottom:24px;"></div>
            <p style="margin:0 0 24px 0;font-size:14px;color:rgba(26,25,22,0.6);line-height:1.75;">
              Ton compte a été validé. Tu peux maintenant activer ton essai gratuit et lancer ta première analyse de match.
            </p>
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
              <tr>
                <td style="background:rgba(201,162,39,0.06);border:1px solid rgba(201,162,39,0.18);border-left:3px solid #c9a227;padding:18px 22px;">
                  <p style="margin:0 0 6px 0;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#c9a227;font-family:'Courier New',monospace;font-weight:700;">Ton offre de bienvenue</p>
                  <p style="margin:0;font-size:20px;color:#1a1916;font-family:'Courier New',monospace;font-weight:900;letter-spacing:.02em;">7 jours d'essai + 1 match offert</p>
                  <p style="margin:6px 0 0 0;font-size:12px;color:rgba(26,25,22,0.45);">Rapport tactique complet · Heatmaps · Stats · Export PDF</p>
                </td>
              </tr>
            </table>
            <table cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#c9a227;">
                  <a href="https://insightball.com/dashboard"
                     style="display:inline-block;padding:14px 28px;color:#0f0f0d;font-family:'Courier New',monospace;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;text-decoration:none;">
                    Accéder à mon tableau de bord
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 0 0 0;">
            <p style="margin:0;font-size:10px;color:rgba(26,25,22,0.3);font-family:'Courier New',monospace;letter-spacing:.04em;">
              Insightball · Du terrain à l'analyse.<br/>
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
        print(f"[WARN] Email approbation non envoyé : {e}")


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

    # ── Anti-doublon email (actif + soft-deleted) ──
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        if existing_user.deleted_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce compte a été désactivé. Contacte le support à contact@insightball.com"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un compte existe déjà avec cet email"
        )

    # ── Anti-doublon téléphone ──
    if user_data.phone:
        phone_digits = re.sub(r'\D', '', user_data.phone)
        if len(phone_digits) >= 10:
            existing_phone = db.query(User).filter(
                User.deleted_at == None,
                User.profile_phone != None,
            ).all()
            for u in existing_phone:
                if re.sub(r'\D', '', u.profile_phone or '') == phone_digits:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Un compte existe déjà avec ce numéro de téléphone"
                    )

    # ── Validation mot de passe (aligné avec reset-password) ──
    if len(user_data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le mot de passe doit contenir au moins 8 caractères"
        )

    club = None
    user_id = str(uuid.uuid4())

    if user_data.plan == PlanType.CLUB:
        if not user_data.club_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Club name is required for CLUB plan")
        club = Club(id=str(uuid.uuid4()), name=user_data.club_name, quota_matches=PLAN_QUOTAS["CLUB"])
        db.add(club)
        db.flush()
    else:
        # Plan COACH — créer le solo club dès le signup
        solo_club_name = (user_data.club_name or "").strip()
        club = Club(
            id=user_id,
            name=solo_club_name,
            quota_matches=PLAN_QUOTAS["COACH"],
        )
        db.add(club)
        db.flush()

    user = User(
        id=user_id,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        name=user_data.name,
        plan=user_data.plan,
        club_id=club.id,
        is_approved=False,  # Validation manuelle requise
        profile_phone=user_data.phone,
        profile_city=user_data.city,
        profile_role=user_data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Email de bienvenue (attente validation) + notification admin
    send_welcome_email(user.name, user.email, user.plan.value)
    _send_admin_new_signup_email(
        user.name, user.email,
        profile_role=user_data.role,
        profile_city=user_data.city,
        profile_phone=user_data.phone,
        club_name=user_data.club_name,
    )

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

    # NOTE : on ne bloque PAS les users is_approved=False au login.
    # Ils doivent pouvoir se connecter pour voir l'écran d'attente.
    # La protection se fait côté frontend (ProtectedRoute).

    user.last_login = datetime.utcnow()
    db.commit()

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Récupérer la catégorie assignée pour les coachs membres
    managed_category = None
    if current_user.club_id:
        role_val = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
        if role_val != 'ADMIN' and not current_user.is_superadmin:
            member = db.query(ClubMember).filter(
                ClubMember.user_id == current_user.id,
                ClubMember.club_id == current_user.club_id,
                ClubMember.status == InviteStatus.ACCEPTED,
            ).first()
            if member:
                managed_category = member.category

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        plan=current_user.plan.value,
        role=current_user.role.value if current_user.role else None,
        club_name=current_user.club.name if current_user.club else None,
        club_id=current_user.club_id,
        club_logo=current_user.club.logo_url if current_user.club else None,
        managed_category=managed_category,
        is_approved=current_user.is_approved,
        profile_role=current_user.profile_role,
        profile_level=current_user.profile_level,
        profile_phone=current_user.profile_phone,
        profile_city=current_user.profile_city,
        profile_diploma=current_user.profile_diploma,
        trial_ends_at=current_user.trial_ends_at.isoformat() if current_user.trial_ends_at else None,
        trial_match_used=current_user.trial_match_used,
        stripe_subscription_id=current_user.stripe_subscription_id,
    )


# ─── Validation manuelle des comptes ───────────────────────────────────────────

@router.get("/pending-users")
async def get_pending_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Liste des comptes en attente de validation. Superadmin only."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Accès refusé")
    users = db.query(User).filter(
        User.is_approved == False,
        User.deleted_at == None,
    ).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "plan": u.plan.value if hasattr(u.plan, 'value') else u.plan,
            "profile_role": u.profile_role,
            "profile_level": u.profile_level,
            "profile_phone": u.profile_phone,
            "profile_city": u.profile_city,
            "profile_diploma": u.profile_diploma,
            "club_name": u.club.name if u.club else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/approve/{user_id}")
async def approve_user(user_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Approuve un compte + démarre le trial 7 jours. Superadmin only."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Accès refusé")

    user = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    if user.is_approved:
        raise HTTPException(status_code=400, detail="Ce compte est déjà approuvé")

    # Approuver + démarrer le trial
    user.is_approved = True
    user.trial_ends_at = datetime.utcnow() + timedelta(days=7)
    db.commit()

    # Email de confirmation à l'utilisateur
    _send_account_approved_email(user.name, user.email)

    return {"success": True, "message": f"Compte de {user.name} approuvé. Trial 7 jours activé."}


@router.post("/reject/{user_id}")
async def reject_user(user_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rejette un compte (soft delete). Superadmin only."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Accès refusé")

    user = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user.deleted_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": f"Compte de {user.name} rejeté."}


# ─── Mot de passe ──────────────────────────────────────────────────────────────

def send_reset_email(user_name: str, user_email: str, reset_token: str):
    try:
        reset_url = f"https://insightball.com/reset-password?token={reset_token}"
        resend.Emails.send({
            "from": "Insightball <contact@insightball.com>",
            "to": user_email,
            "subject": "Réinitialisation de votre mot de passe — Insightball",
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
                    RÉINITIALISER MON MOT DE PASSE
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
        print(f"[WARN] Email reset non envoyé : {e}")


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
