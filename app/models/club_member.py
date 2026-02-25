from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base


class MemberRole(str, enum.Enum):
    ADMIN   = "ADMIN"
    COACH   = "COACH"
    ANALYST = "ANALYST"


class InviteStatus(str, enum.Enum):
    PENDING  = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


class ClubMember(Base):
    __tablename__ = "club_members"

    id           = Column(String, primary_key=True, index=True)
    club_id      = Column(String, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    user_id      = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    email        = Column(String, nullable=False)
    role         = Column(Enum(MemberRole), nullable=False, default=MemberRole.COACH)
    category     = Column(String, nullable=True)

    status       = Column(Enum(InviteStatus), default=InviteStatus.PENDING)
    invite_token = Column(String, unique=True, nullable=True)

    invited_by  = Column(String, ForeignKey("users.id"), nullable=False)
    invited_at  = Column(DateTime, default=datetime.utcnow)
    accepted_at = Column(DateTime, nullable=True)

    club    = relationship("Club", foreign_keys=[club_id])
    user    = relationship("User", foreign_keys=[user_id])
    inviter = relationship("User", foreign_keys=[invited_by])

    class Config:
        from_attributes = True
