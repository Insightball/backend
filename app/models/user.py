from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base

class PlanType(str, enum.Enum):
    COACH = "coach"
    CLUB = "club"

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    COACH = "coach"
    ANALYST = "analyst"

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    
    # Plan info
    plan = Column(Enum(PlanType), nullable=False)
    stripe_customer_id = Column(String, unique=True)
    stripe_subscription_id = Column(String)
    
    # For CLUB plan
    club_id = Column(String, ForeignKey("clubs.id"), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.ADMIN)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    club = relationship("Club", back_populates="members")
    
    class Config:
        from_attributes = True
