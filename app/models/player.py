from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Player(Base):
    __tablename__ = "players"
    
    id = Column(String, primary_key=True, index=True)
    club_id = Column(String, ForeignKey("clubs.id"), nullable=False)
    
    # Info personnelle
    name = Column(String, nullable=False)
    number = Column(Integer, nullable=True)
    position = Column(String, nullable=False)
    category = Column(String, default="N3")
    
    # Physique
    birth_date = Column(DateTime, nullable=True)
    height = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)
    
    # Média
    photo_url = Column(String, nullable=True)
    
    # Status - NOW STRING NOT ENUM
    status = Column(String, default="actif")
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    club = relationship("Club", back_populates="players")
    
    class Config:
        from_attributes = True
