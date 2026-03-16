"""Modèle SQLAlchemy — Séances d'entraînement et présences."""

from sqlalchemy import Column, String, Date, Integer, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    club_id = Column(String, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True)
    category = Column(String, nullable=False, default="Seniors")
    date = Column(Date, nullable=False)
    session_type = Column(String, default="entrainement")  # entrainement | match | physique | video | autre
    start_time = Column(String, default="19:00")
    duration_minutes = Column(Integer, default=90)
    notes = Column(Text, nullable=True)
    theme = Column(String, nullable=True)  # lien avec Projet de Jeu (pressing, construction, etc.)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    attendances = relationship("Attendance", back_populates="session", cascade="all, delete-orphan")


class Attendance(Base):
    __tablename__ = "attendances"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(String, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default="present")  # present | absent | excused | injured
    absence_reason = Column(String, nullable=True)  # scolaire | blessure | non_justifiee | familiale | selection | autre
    noted_at = Column(DateTime, default=datetime.utcnow)

    # Relations
    session = relationship("TrainingSession", back_populates="attendances")

    __table_args__ = (
        UniqueConstraint("session_id", "player_id", name="uq_attendance_session_player"),
    )
