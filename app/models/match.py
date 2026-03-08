from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Enum, JSON, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base

class MatchStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"

class MatchType(str, enum.Enum):
    CHAMPIONNAT = "championnat"
    COUPE = "coupe"
    AMICAL = "amical"
    PREPARATION = "preparation"

def compute_season(date: datetime) -> str:
    """Calcule la saison FFF depuis une date. Ex: mars 2026 → '2025-26', sept 2025 → '2025-26'"""
    if date.month >= 7:
        return f"{date.year}-{str(date.year + 1)[-2:]}"
    else:
        return f"{date.year - 1}-{str(date.year)[-2:]}"

class Match(Base):
    __tablename__ = "matches"
    
    id = Column(String, primary_key=True, index=True)
    club_id = Column(String, ForeignKey("clubs.id"), nullable=False)
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Match info
    opponent = Column(String, nullable=False)
    date = Column(DateTime, nullable=False)
    category = Column(String, default="N3")
    type = Column(Enum(MatchType), default=MatchType.CHAMPIONNAT)
    competition = Column(String, nullable=True)
    location = Column(String, nullable=True)

    # Saison FFF — calculée automatiquement depuis la date du match
    # Format : "2025-26", "2024-25", etc.
    season = Column(String, nullable=True, index=True)
    
    # Score
    score_home = Column(Integer, nullable=True)
    score_away = Column(Integer, nullable=True)
    
    # Conditions
    weather = Column(String, nullable=True)
    pitch_type = Column(String, nullable=True)
    
    # Files
    video_url = Column(String, nullable=True)
    pdf_url = Column(String, nullable=True)
    
    # Processing
    status = Column(Enum(MatchStatus), default=MatchStatus.PENDING)
    progress = Column(Integer, default=0)
    error_message = Column(String, nullable=True)
    
    # Lineup
    lineup = Column(JSON, nullable=True)
    
    # Stats
    stats = Column(JSON, nullable=True)
    
    # Match context
    is_home = Column(Boolean, default=True)
    formation = Column(String, nullable=True)
    opponent_formation = Column(String, nullable=True)
    
    # IA Analysis output
    analysis_data = Column(JSON, nullable=True)
    ai_insights = Column(Text, nullable=True)
    player_stats = Column(JSON, nullable=True)
    events = Column(JSON, nullable=True)
    
    # Metadata
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    club = relationship("Club", back_populates="matches")
    
    class Config:
        from_attributes = True
