"""Modèle SQLAlchemy — Profil joueur enrichi, notes et objectifs."""

from sqlalchemy import Column, String, Float, Integer, Text, Date, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.database import Base


class PlayerEvaluation(Base):
    __tablename__ = "player_evaluations"

    id = Column(String, primary_key=True, index=True)
    player_id = Column(String, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Radar overrides : le coach surcharge les axes auto-calculés
    # Format: {"technique": 4, "physique": 3, "efficacite": 2, ...}
    # Valeurs 1-5, null = auto-calculé
    radar_overrides = Column(JSONB, default={})
    # Config radar personnalisée par catégorie
    # Format: {"axes": ["technique","initiative","engagement","temps_jeu","assiduite","progression"]}
    radar_config = Column(JSONB, nullable=True)
    # Forces/faiblesses manuelles
    # Format: {"forces": ["Bon jeu de tête"], "faiblesses": ["Pied gauche faible"]}
    manual_traits = Column(JSONB, default={})
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("player_id", "user_id", name="uq_eval_player_user"),
    )


class PlayerNote(Base):
    __tablename__ = "player_notes"

    id = Column(String, primary_key=True, index=True)
    player_id = Column(String, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    match_id = Column(String, ForeignKey("matches.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PlayerObjective(Base):
    __tablename__ = "player_objectives"

    id = Column(String, primary_key=True, index=True)
    player_id = Column(String, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # stat | attendance | playtime | educational | qualitative
    # Pour type 'stat' : la métrique à suivre (pass_success_rate, shots_on_target, etc.)
    metric = Column(String, nullable=True)
    # Pour type 'educational' : description qualitative
    description = Column(Text, nullable=True)
    target_value = Column(Float, nullable=True)
    current_value = Column(Float, default=0)
    period_matches = Column(Integer, default=4)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    # Pour educational : évaluation par match
    # Format: [{"match_id": "...", "date": "...", "status": "en_cours"}]
    evaluations = Column(JSONB, default=[])
    status = Column(String, default="active")  # active | completed | failed | paused
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
