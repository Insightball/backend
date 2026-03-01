from sqlalchemy import Column, String, Integer, DateTime, Enum
from datetime import datetime
import enum
from app.database import Base


class ClubInviteStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"


class ClubInvite(Base):
    __tablename__ = "club_invites"

    id = Column(String, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)

    # Infos du contact club (remplies par l'admin)
    email = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    function = Column(String, nullable=True)  # Responsable Technique, Directeur Sportif, Président

    # Infos club
    club_name = Column(String, nullable=False)
    city = Column(String, nullable=True)
    nb_teams_11 = Column(Integer, nullable=True)  # Nombre d'équipes foot à 11
    nb_matches_estimated = Column(Integer, nullable=True)

    # Palier négocié par l'admin
    plan_tier = Column(String, nullable=False)  # CLUB ou CLUB_PRO
    plan_price = Column(Integer, nullable=False)  # 99 ou 139 (en euros)
    quota_matches = Column(Integer, nullable=False)  # 10 ou 15

    # Stripe Price ID créé pour ce palier
    stripe_price_id = Column(String, nullable=True)

    # État
    status = Column(Enum(ClubInviteStatus), default=ClubInviteStatus.PENDING, nullable=False)

    # Si le DS a déjà un compte Coach → upgrade
    existing_user_id = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
