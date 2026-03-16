"""Modèle SQLAlchemy — Feuille de match."""

from sqlalchemy import Column, String, Date, Float, Integer, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class MatchSheet(Base):
    __tablename__ = "match_sheets"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    club_id = Column(String, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True)
    match_id = Column(String, ForeignKey("matches.id", ondelete="SET NULL"), nullable=True)
    category = Column(String, nullable=False, default="Seniors")
    date = Column(Date, nullable=False)
    opponent = Column(String, nullable=True)
    formation = Column(String, default="4-3-3")
    competition = Column(String, nullable=True)
    venue = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    players = relationship("MatchSheetPlayer", back_populates="sheet", cascade="all, delete-orphan")
    subs = relationship("MatchSheetSub", back_populates="sheet", cascade="all, delete-orphan")


class MatchSheetPlayer(Base):
    __tablename__ = "match_sheet_players"

    id = Column(String, primary_key=True, index=True)
    sheet_id = Column(String, ForeignKey("match_sheets.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(String, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False, default="starter")  # starter | substitute
    position = Column(String, nullable=True)
    position_x = Column(Float, nullable=True)
    position_y = Column(Float, nullable=True)
    instructions = Column(Text, nullable=True)
    shirt_number = Column(Integer, nullable=True)

    # Relations
    sheet = relationship("MatchSheet", back_populates="players")

    __table_args__ = (
        UniqueConstraint("sheet_id", "player_id", name="uq_sheet_player"),
    )


class MatchSheetSub(Base):
    __tablename__ = "match_sheet_subs"

    id = Column(String, primary_key=True, index=True)
    sheet_id = Column(String, ForeignKey("match_sheets.id", ondelete="CASCADE"), nullable=False)
    player_in_id = Column(String, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    player_out_id = Column(String, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    minute = Column(Integer, nullable=False)
    reason = Column(String, nullable=True)

    # Relations
    sheet = relationship("MatchSheet", back_populates="subs")
