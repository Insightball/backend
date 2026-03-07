"""
utils/club.py — Helpers partagés entre les routes matches.py et players.py.
Ne pas dupliquer ces fonctions dans les routes.
"""

from sqlalchemy.orm import Session
from app.models import User
from app.models.club_member import ClubMember, InviteStatus


def get_managed_category(user: User, db: Session) -> str | None:
    """
    Retourne la catégorie assignée au coach membre via ClubMember.
    - Superadmin       → None (voit tout)
    - DS admin (ADMIN) → None (voit tout)
    - Coach membre     → sa catégorie assignée (ex: 'U19', 'Seniors')
    - Coach solo       → None
    """
    if user.is_superadmin:
        return None
    role_val = user.role.value if hasattr(user.role, "value") else user.role
    if role_val == "ADMIN":
        return None
    if not user.club_id:
        return None
    member = db.query(ClubMember).filter(
        ClubMember.user_id == user.id,
        ClubMember.club_id == user.club_id,
        ClubMember.status == InviteStatus.ACCEPTED,
    ).first()
    if member and member.category:
        return member.category
    return None
