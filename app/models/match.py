from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum, JSON
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

class Match(Base):
    __tablename__ = "matches"
    
    id = Column(String, primary_key=True, index=True)
    club_id = Column(String, ForeignKey("clubs.id"), nullable=False)
    
    # Match info
    opponent = Column(String, nullable=False)
    date = Column(DateTime, nullable=False)
    category = Column(String, default="N3")
    type = Column(Enum(MatchType), default=MatchType.CHAMPIONNAT)
    competition = Column(String, nullable=True)
    location = Column(String, nullable=True)
    
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
    
    # Lineup - NOUVEAU
    lineup = Column(JSON, nullable=True)
    
    # Stats
    stats = Column(JSON, nullable=True)
    
    # Metadata
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    club = relationship("Club", back_populates="matches")
    
    class Config:
        from_attributes = True
