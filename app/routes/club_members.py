"""
app/routes/club_members.py
Gestion des membres d'un club — invitations, rôles, suppressions
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr
import uuid
import secrets
import resend
import os

from app.database import get_db
from app.models import User, Club
from app.models.club_member import ClubMember, MemberRole, InviteStatus
from app.dependencies import get_current_user

router = APIRouter()
resend.api_key = os.getenv("RESEND_API_KEY")


# ─── Dependencies ────────────────────────────────────────────────────────────

def require_club_admin(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.club_id:
        raise HTTPException(status_code=403, detail="Aucun club associé")
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux admins du club")
    return current_user

def require_club_member(current_user: User = Depends(get_current_user)):
    if not current_user.club_id:
        raise HTTPException(status_code=403, detail="Aucun club associé")
    return current_user


# ─── Schemas ─────────────────────────────────────────────────────────────────

class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: MemberRole
    category: Optional[str] = None

class UpdateMemberRequest(BaseModel):
    role: Optional[MemberRole] = None
    category: Optional[str] = None

class MemberResponse(BaseModel):
    id: str
    email: str
    role: str
    category: Optional[str]
    status: str
    invited_at: datetime
    accepted_at: Optional[datetime]
    user_name: Optional[str] = None
    user_id: Optional[str] = None

    class Config:
        from_attributes = True


# ─── Email invitation ─────────────────────────────────────────────────────────

def send_invitation_email(invitee_email: str, club_name: str, inviter_name: str, role: str, category: Optional[str], token: str):
    role_labels = {"admin": "Administrateur", "coach": "Coach", "analyst": "Analyste"}
    role_label = role_labels.get(role, role)
    category_text = f" — {category}" if category else ""
    accept_url = f"https://www.insightball.com/join?token={token}"

    try:
        resend.Emails.send({
            "from": "INSIGHTBALL <contact@insightball.com>",
            "to": invitee_email,
            "subject": f"Invitation INSIGHTBALL — {club_name}",
            "html": f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0a0908;font-family:monospace;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0908;padding:40px 20px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

        <!-- Logo -->
        <tr>
          <td style="padding:0 0 32px 0;">
            <span style="font-size:22px;font-weight:900;letter-spacing:.06em;color:#f5f2eb;font-family:monospace;">
              INSIGHT<span style="color:#c9a227;">BALL</span>
            </span>
          </td>
        </tr>

        <!-- Card -->
        <tr>
          <td style="background:#0f0e0c;border:1px solid rgba(255,255,255,0.07);border-top:2px solid #c9a227;padding:36px 32px;">

            <!-- Subtitle -->
            <p style="margin:0 0 8px 0;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#c9a227;font-family:monospace;">
              Invitation reçue
            </p>

            <!-- Title -->
            <h1 style="margin:0 0 20px 0;font-size:28px;text-transform:uppercase;color:#f5f2eb;font-family:monospace;letter-spacing:.03em;line-height:1.1;">
              Rejoignez<br/>{club_name}
            </h1>

            <!-- Separator -->
            <div style="width:40px;height:2px;background:#c9a227;margin-bottom:24px;"></div>

            <!-- Body -->
            <p style="margin:0 0 24px 0;font-size:13px;color:rgba(245,242,235,0.55);line-height:1.7;font-family:monospace;letter-spacing:.03em;">
              <strong style="color:#f5f2eb;">{inviter_name}</strong> vous invite à rejoindre
              <strong style="color:#f5f2eb;">{club_name}</strong> sur INSIGHTBALL.
            </p>

            <!-- Role card -->
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:32px;">
              <tr>
                <td style="background:rgba(201,162,39,0.06);border:1px solid rgba(201,162,39,0.15);padding:20px 24px;">
                  <p style="margin:0 0 6px 0;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:rgba(245,242,235,0.35);font-family:monospace;">Votre rôle</p>
                  <p style="margin:0;font-size:18px;text-transform:uppercase;color:#c9a227;font-family:monospace;font-weight:700;letter-spacing:.06em;">
                    {role_label}{category_text}
                  </p>
                </td>
              </tr>
            </table>

            <!-- CTA -->
            <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
              <tr>
                <td style="background:#c9a227;">
                  <a href="{accept_url}"
                     style="display:inline-block;padding:14px 32px;color:#0f0f0d;font-family:monospace;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;text-decoration:none;">
                    ACCEPTER L'INVITATION →
                  </a>
                </td>
              </tr>
            </table>

            <!-- Note expiration -->
            <p style="margin:0;font-size:10px;color:rgba(245,242,235,0.2);font-family:monospace;letter-spacing:.03em;">
              Ce lien est valable 7 jours. Si vous n'attendiez pas cette invitation, ignorez cet email.
            </p>

          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:24px 0 0 0;">
            <p style="margin:0;font-size:10px;color:rgba(245,242,235,0.2);font-family:monospace;letter-spacing:.04em;">
              Une question ?
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
        print(f"⚠️ Email invitation non envoyé : {e}")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[MemberResponse])
def list_members(current_user: User = Depends(require_club_member), db: Session = Depends(get_db)):
    members = db.query(ClubMember).filter(ClubMember.club_id == current_user.club_id).order_by(ClubMember.invited_at).all()
    return [MemberResponse(
        id=m.id, email=m.email, role=m.role.value, category=m.category,
        status=m.status.value, invited_at=m.invited_at, accepted_at=m.accepted_at,
        user_name=m.user.name if m.user else None, user_id=m.user_id,
    ) for m in members]


@router.post("/invite", status_code=201)
def invite_member(body: InviteMemberRequest, current_user: User = Depends(require_club_admin), db: Session = Depends(get_db)):
    if body.role == MemberRole.COACH and not body.category:
        raise HTTPException(status_code=400, detail="Une catégorie est requise pour le rôle Coach")

    existing = db.query(ClubMember).filter(
        and_(ClubMember.club_id == current_user.club_id, ClubMember.email == body.email, ClubMember.status != InviteStatus.DECLINED)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Cet email a déjà une invitation active dans ce club")

    club = db.query(Club).filter(Club.id == current_user.club_id).first()
    token = secrets.token_urlsafe(32)

    member = ClubMember(
        id=str(uuid.uuid4()), club_id=current_user.club_id, email=body.email,
        role=body.role, category=body.category, status=InviteStatus.PENDING,
        invite_token=token, invited_by=current_user.id,
    )
    db.add(member)
    db.commit()

    send_invitation_email(
        invitee_email=body.email, club_name=club.name, inviter_name=current_user.name,
        role=body.role.value, category=body.category, token=token,
    )
    return {"message": "Invitation envoyée", "id": member.id}


@router.get("/accept")
def accept_invitation(token: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    member = db.query(ClubMember).filter(ClubMember.invite_token == token).first()
    if not member:
        raise HTTPException(status_code=404, detail="Invitation introuvable ou expirée")
    if member.status != InviteStatus.PENDING:
        raise HTTPException(status_code=400, detail="Invitation déjà traitée")
    if member.email != current_user.email:
        raise HTTPException(status_code=403, detail="Cette invitation ne vous est pas destinée")

    member.status = InviteStatus.ACCEPTED
    member.user_id = current_user.id
    member.accepted_at = datetime.utcnow()
    member.invite_token = None
    current_user.club_id = member.club_id
    current_user.role = member.role
    db.commit()
    return {"message": "Invitation acceptée", "club_id": member.club_id, "role": member.role.value}


@router.patch("/{member_id}")
def update_member(member_id: str, body: UpdateMemberRequest, current_user: User = Depends(require_club_admin), db: Session = Depends(get_db)):
    member = db.query(ClubMember).filter(and_(ClubMember.id == member_id, ClubMember.club_id == current_user.club_id)).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    if member.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Impossible de modifier son propre rôle")

    if body.role is not None:
        member.role = body.role
        if member.user_id:
            user = db.query(User).filter(User.id == member.user_id).first()
            if user: user.role = body.role
    if body.category is not None:
        member.category = body.category
    db.commit()
    return {"message": "Membre mis à jour"}


@router.delete("/{member_id}", status_code=204)
def remove_member(member_id: str, current_user: User = Depends(require_club_admin), db: Session = Depends(get_db)):
    member = db.query(ClubMember).filter(and_(ClubMember.id == member_id, ClubMember.club_id == current_user.club_id)).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    if member.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Impossible de se retirer soi-même")

    if member.user_id:
        user = db.query(User).filter(User.id == member.user_id).first()
        if user: user.club_id = None
    db.delete(member)
    db.commit()
