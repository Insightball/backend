from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base


class MemberRole(str, enum.Enum):
    ADMIN    = "admin"
    COACH    = "coach"
    ANALYST  = "analyst"


class InviteStatus(str, enum.Enum):
    PENDING  = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class ClubMember(Base):
    __tablename__ = "club_members"

    id          = Column(String, primary_key=True, index=True)
    club_id     = Column(String, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    user_id     = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)  # NULL tant que non accepté

    # Invitation
    email       = Column(String, nullable=False)        # email invité
    role        = Column(Enum(MemberRole), nullable=False, default=MemberRole.COACH)
    category    = Column(String, nullable=True)         # ex: "U17", "N3" — pour rôle Coach

    # Statut
    status      = Column(Enum(InviteStatus), default=InviteStatus.PENDING)
    invite_token = Column(String, unique=True, nullable=True)  # token lien email

    # Traçabilité
    invited_by  = Column(String, ForeignKey("users.id"), nullable=False)
    invited_at  = Column(DateTime, default=datetime.utcnow)
    accepted_at = Column(DateTime, nullable=True)

    # Relationships
    club        = relationship("Club", foreign_keys=[club_id])
    user        = relationship("User", foreign_keys=[user_id])
    inviter     = relationship("User", foreign_keys=[invited_by])

    class Config:
        from_attributes = True
