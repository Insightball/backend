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


# ─── Dependency : accès club requis ─────────────────────────────────────────

def require_club_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vérifie que l'utilisateur est Admin de son club"""
    if not current_user.club_id:
        raise HTTPException(status_code=403, detail="Aucun club associé")
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux admins du club")
    return current_user


def require_club_member(
    current_user: User = Depends(get_current_user),
):
    """Vérifie que l'utilisateur appartient à un club"""
    if not current_user.club_id:
        raise HTTPException(status_code=403, detail="Aucun club associé")
    return current_user


# ─── Schemas ─────────────────────────────────────────────────────────────────

class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: MemberRole
    category: Optional[str] = None  # obligatoire si role == coach


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


# ─── Helpers ─────────────────────────────────────────────────────────────────

def send_invitation_email(
    invitee_email: str,
    club_name: str,
    inviter_name: str,
    role: str,
    category: Optional[str],
    token: str
):
    """Envoie l'email d'invitation à rejoindre un club"""
    role_labels = {"admin": "Administrateur", "coach": "Coach", "analyst": "Analyste"}
    role_label = role_labels.get(role, role)
    category_text = f" — catégorie {category}" if category else ""
    accept_url = f"https://www.insightball.com/join?token={token}"

    try:
        resend.Emails.send({
            "from": "INSIGHTBALL <contact@insightball.com>",
            "to": invitee_email,
            "subject": f"Invitation INSIGHTBALL — {club_name}",
            "html": f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;
                        background: #0f0f0d; color: #f5f2eb; padding: 40px; border-radius: 4px;">
                <div style="margin-bottom: 32px;">
                    <span style="font-family: monospace; font-size: 22px; font-weight: 900; letter-spacing: .04em;">
                        INSIGHT<span style="color: #c9a227;">BALL</span>
                    </span>
                </div>

                <h2 style="font-size: 20px; margin-bottom: 8px; color: #f5f2eb;">
                    Vous êtes invité(e) à rejoindre {club_name}
                </h2>
                <p style="color: rgba(245,242,235,0.6); line-height: 1.6; margin-bottom: 24px;">
                    <strong style="color:#f5f2eb">{inviter_name}</strong> vous invite à rejoindre
                    <strong style="color:#f5f2eb"> {club_name}</strong> sur INSIGHTBALL
                    en tant que <strong style="color:#c9a227">{role_label}{category_text}</strong>.
                </p>

                <div style="text-align: center; margin: 32px 0;">
                    <a href="{accept_url}"
                       style="background: #c9a227; color: #0f0f0d; padding: 14px 32px;
                              text-decoration: none; font-weight: 700; font-size: 13px;
                              letter-spacing: .1em; text-transform: uppercase; font-family: monospace;">
                        Accepter l'invitation →
                    </a>
                </div>

                <p style="color: rgba(245,242,235,0.35); font-size: 11px; text-align: center; margin-top: 32px;">
                    Ce lien est valable 7 jours. Si vous n'attendiez pas cette invitation, ignorez cet email.
                </p>
            </div>
            """
        })
    except Exception as e:
        print(f"⚠️ Email invitation non envoyé : {e}")


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("", response_model=List[MemberResponse])
def list_members(
    current_user: User = Depends(require_club_member),
    db: Session = Depends(get_db)
):
    """Liste tous les membres (acceptés + en attente) du club"""
    members = db.query(ClubMember).filter(
        ClubMember.club_id == current_user.club_id
    ).order_by(ClubMember.invited_at).all()

    result = []
    for m in members:
        result.append(MemberResponse(
            id=m.id,
            email=m.email,
            role=m.role.value,
            category=m.category,
            status=m.status.value,
            invited_at=m.invited_at,
            accepted_at=m.accepted_at,
            user_name=m.user.name if m.user else None,
            user_id=m.user_id,
        ))
    return result


@router.post("/invite", status_code=201)
def invite_member(
    body: InviteMemberRequest,
    current_user: User = Depends(require_club_admin),
    db: Session = Depends(get_db)
):
    """Inviter un nouveau membre dans le club"""
    # Vérif : coach doit avoir une catégorie
    if body.role == MemberRole.COACH and not body.category:
        raise HTTPException(status_code=400, detail="Une catégorie est requise pour le rôle Coach")

    # Vérif : déjà invité ou membre ?
    existing = db.query(ClubMember).filter(
        and_(
            ClubMember.club_id == current_user.club_id,
            ClubMember.email == body.email,
            ClubMember.status != InviteStatus.DECLINED
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Cet email a déjà une invitation active dans ce club")

    # Récupérer le club
    club = db.query(Club).filter(Club.id == current_user.club_id).first()

    # Créer l'invitation
    token = secrets.token_urlsafe(32)
    member = ClubMember(
        id=str(uuid.uuid4()),
        club_id=current_user.club_id,
        email=body.email,
        role=body.role,
        category=body.category,
        status=InviteStatus.PENDING,
        invite_token=token,
        invited_by=current_user.id,
    )
    db.add(member)
    db.commit()

    # Envoyer email
    send_invitation_email(
        invitee_email=body.email,
        club_name=club.name,
        inviter_name=current_user.name,
        role=body.role.value,
        category=body.category,
        token=token,
    )

    return {"message": "Invitation envoyée", "id": member.id}


@router.get("/accept")
def accept_invitation(
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Accepter une invitation via token (utilisateur connecté)"""
    member = db.query(ClubMember).filter(ClubMember.invite_token == token).first()

    if not member:
        raise HTTPException(status_code=404, detail="Invitation introuvable ou expirée")
    if member.status != InviteStatus.PENDING:
        raise HTTPException(status_code=400, detail="Invitation déjà traitée")
    if member.email != current_user.email:
        raise HTTPException(status_code=403, detail="Cette invitation ne vous est pas destinée")

    # Mettre à jour le membre
    member.status = InviteStatus.ACCEPTED
    member.user_id = current_user.id
    member.accepted_at = datetime.utcnow()
    member.invite_token = None  # invalider le token

    # Rattacher l'utilisateur au club
    current_user.club_id = member.club_id
    current_user.role = member.role

    db.commit()
    return {"message": "Invitation acceptée", "club_id": member.club_id, "role": member.role.value}


@router.patch("/{member_id}")
def update_member(
    member_id: str,
    body: UpdateMemberRequest,
    current_user: User = Depends(require_club_admin),
    db: Session = Depends(get_db)
):
    """Modifier le rôle ou la catégorie d'un membre"""
    member = db.query(ClubMember).filter(
        and_(ClubMember.id == member_id, ClubMember.club_id == current_user.club_id)
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable")

    # Empêcher de modifier son propre rôle
    if member.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Impossible de modifier son propre rôle")

    if body.role is not None:
        member.role = body.role
        # Sync sur le user si accepté
        if member.user_id:
            user = db.query(User).filter(User.id == member.user_id).first()
            if user:
                user.role = body.role

    if body.category is not None:
        member.category = body.category

    db.commit()
    return {"message": "Membre mis à jour"}


@router.delete("/{member_id}", status_code=204)
def remove_member(
    member_id: str,
    current_user: User = Depends(require_club_admin),
    db: Session = Depends(get_db)
):
    """Retirer un membre du club"""
    member = db.query(ClubMember).filter(
        and_(ClubMember.id == member_id, ClubMember.club_id == current_user.club_id)
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    if member.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Impossible de se retirer soi-même")

    # Détacher l'utilisateur du club si accepté
    if member.user_id:
        user = db.query(User).filter(User.id == member.user_id).first()
        if user:
            user.club_id = None

    db.delete(member)
    db.commit()
