"""
app/routes/account.py
Gestion du compte utilisateur — suppression soft delete + récupération
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
import resend
import os

from app.database import get_db
from app.models import User
from app.dependencies import get_current_user

router = APIRouter()
resend.api_key = os.getenv("RESEND_API_KEY")

RECOVERY_DAYS = 30


# ─── Email suppression avec lien de récupération ─────────────────────────────

def send_deletion_email(user_name: str, user_email: str, recovery_token: str):
    recovery_url = f"https://www.insightball.com/recover?token={recovery_token}"
    deadline = (datetime.utcnow() + timedelta(days=RECOVERY_DAYS)).strftime("%d/%m/%Y")

    try:
        resend.Emails.send({
            "from": "INSIGHTBALL <contact@insightball.com>",
            "to": user_email,
            "subject": "Suppression de votre compte INSIGHTBALL",
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
          <td style="background:#0f0e0c;border:1px solid rgba(255,255,255,0.07);border-top:2px solid #ef4444;padding:36px 32px;">

            <p style="margin:0 0 8px 0;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#ef4444;font-family:monospace;">
              Compte supprimé
            </p>

            <h1 style="margin:0 0 20px 0;font-size:28px;text-transform:uppercase;color:#f5f2eb;font-family:monospace;letter-spacing:.03em;line-height:1.1;">
              Au revoir,<br/>{user_name}
            </h1>

            <div style="width:40px;height:2px;background:#ef4444;margin-bottom:24px;"></div>

            <p style="margin:0 0 24px 0;font-size:13px;color:rgba(245,242,235,0.55);line-height:1.7;font-family:monospace;">
              Votre compte a bien été supprimé. Toutes vos données (matchs, joueurs, statistiques)
              sont conservées pendant <strong style="color:#f5f2eb;">{RECOVERY_DAYS} jours</strong> et
              seront définitivement effacées le <strong style="color:#f5f2eb;">{deadline}</strong>.
            </p>

            <!-- Info récupération -->
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:32px;">
              <tr>
                <td style="background:rgba(201,162,39,0.06);border:1px solid rgba(201,162,39,0.15);padding:20px 24px;">
                  <p style="margin:0 0 8px 0;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:#c9a227;font-family:monospace;">
                    Vous avez changé d'avis ?
                  </p>
                  <p style="margin:0;font-size:12px;color:rgba(245,242,235,0.55);font-family:monospace;line-height:1.6;">
                    Récupérez votre compte et toutes vos données avant le {deadline}.
                    Après cette date, la suppression sera définitive et irréversible.
                  </p>
                </td>
              </tr>
            </table>

            <!-- CTA récupération -->
            <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
              <tr>
                <td style="background:#c9a227;">
                  <a href="{recovery_url}"
                     style="display:inline-block;padding:14px 32px;color:#0f0f0d;font-family:monospace;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;">
                    RÉCUPÉRER MON COMPTE →
                  </a>
                </td>
              </tr>
            </table>

            <p style="margin:0;font-size:10px;color:rgba(245,242,235,0.2);font-family:monospace;">
              Si vous n'êtes pas à l'origine de cette demande, récupérez votre compte immédiatement
              et changez votre mot de passe.
            </p>

          </td>
        </tr>

        <tr>
          <td style="padding:24px 0 0 0;">
            <p style="margin:0;font-size:10px;color:rgba(245,242,235,0.2);font-family:monospace;">
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
        print(f"⚠️ Email suppression non envoyé : {e}")


def send_recovery_email(user_name: str, user_email: str):
    try:
        resend.Emails.send({
            "from": "INSIGHTBALL <contact@insightball.com>",
            "to": user_email,
            "subject": "Votre compte INSIGHTBALL a été récupéré",
            "html": f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
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
          <td style="background:#0f0e0c;border:1px solid rgba(255,255,255,0.07);border-top:2px solid #22c55e;padding:36px 32px;">
            <p style="margin:0 0 8px 0;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#22c55e;font-family:monospace;">Compte récupéré</p>
            <h1 style="margin:0 0 20px 0;font-size:28px;text-transform:uppercase;color:#f5f2eb;font-family:monospace;line-height:1.1;">
              Content de vous<br/>revoir, {user_name} !
            </h1>
            <div style="width:40px;height:2px;background:#22c55e;margin-bottom:24px;"></div>
            <p style="margin:0 0 32px 0;font-size:13px;color:rgba(245,242,235,0.55);line-height:1.7;font-family:monospace;">
              Votre compte est restauré avec toutes vos données — matchs, joueurs et statistiques.
            </p>
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
      </table>
    </td></tr>
  </table>
</body>
</html>"""
        })
    except Exception as e:
        print(f"⚠️ Email récupération non envoyé : {e}")


# ─── Endpoints ────────────────────────────────────────────────────────────────


from pydantic import BaseModel
from typing import Optional

class ProfileUpdate(BaseModel):
    role: Optional[str] = None
    level: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    diploma: Optional[str] = None

@router.patch("/profile")
def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Met à jour le profil personnel de l'utilisateur"""
    if data.role is not None: current_user.profile_role = data.role
    if data.level is not None: current_user.profile_level = data.level
    if data.phone is not None: current_user.profile_phone = data.phone
    if data.city is not None: current_user.profile_city = data.city
    if data.diploma is not None: current_user.profile_diploma = data.diploma
    current_user.updated_at = datetime.utcnow()
    db.commit()
    return {
        "role": current_user.profile_role,
        "level": current_user.profile_level,
        "phone": current_user.profile_phone,
        "city": current_user.profile_city,
        "diploma": current_user.profile_diploma,
    }

@router.get("/profile")
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Récupère le profil personnel"""
    return {
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.profile_role,
        "level": current_user.profile_level,
        "phone": current_user.profile_phone,
        "city": current_user.profile_city,
        "diploma": current_user.profile_diploma,
    }

@router.delete("/delete")
def delete_account(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soft delete — conserve les données 30 jours"""
    if current_user.deleted_at:
        raise HTTPException(status_code=400, detail="Compte déjà supprimé")

    recovery_token = secrets.token_urlsafe(32)
    recovery_expires = datetime.utcnow() + timedelta(days=RECOVERY_DAYS)

    current_user.deleted_at = datetime.utcnow()
    current_user.recovery_token = recovery_token
    current_user.recovery_token_expires = recovery_expires
    current_user.is_active = False
    db.commit()

    background_tasks.add_task(
        send_deletion_email,
        current_user.name,
        current_user.email,
        recovery_token
    )

    return {"message": f"Compte supprimé. Récupérable pendant {RECOVERY_DAYS} jours."}


@router.get("/recover")
def recover_account(
    token: str,
    db: Session = Depends(get_db)
):
    """Récupérer un compte supprimé via le token reçu par email"""
    user = db.query(User).filter(User.recovery_token == token).first()

    if not user:
        raise HTTPException(status_code=404, detail="Lien de récupération invalide")

    if not user.deleted_at:
        raise HTTPException(status_code=400, detail="Ce compte n'est pas supprimé")

    if user.recovery_token_expires and datetime.utcnow() > user.recovery_token_expires:
        raise HTTPException(status_code=400, detail="Lien expiré — compte définitivement supprimé")

    # Restaurer le compte
    user.deleted_at = None
    user.recovery_token = None
    user.recovery_token_expires = None
    user.is_active = True
    db.commit()

    send_recovery_email(user.name, user.email)

    return {"message": "Compte récupéré avec succès", "email": user.email}
