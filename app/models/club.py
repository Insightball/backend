from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Club(Base):
    __tablename__ = "clubs"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    
    # Identité visuelle
    logo_url = Column(String, nullable=True)
    primary_color = Column(String, nullable=True)
    secondary_color = Column(String, nullable=True)
    
    # Stripe info
    stripe_customer_id = Column(String, unique=True)
    stripe_subscription_id = Column(String)
    
    # Quotas
    quota_matches = Column(Integer, default=10)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    members = relationship("User", back_populates="club")
    matches = relationship("Match", back_populates="club", cascade="all, delete-orphan")
    players = relationship("Player", back_populates="club", cascade="all, delete-orphan")
    
    class Config:
        from_attributes = True
