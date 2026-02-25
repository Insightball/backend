from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base

class PlanType(str, enum.Enum):
    COACH = "COACH"
    CLUB = "CLUB"

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    COACH = "COACH"
    ANALYST = "ANALYST"

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
    
    # Superadmin
    is_superadmin = Column(Boolean, default=False)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Soft delete — récupérable 30 jours
    deleted_at = Column(DateTime, nullable=True)
    recovery_token = Column(String, nullable=True, unique=True)
    recovery_token_expires = Column(DateTime, nullable=True)
    
    # Relationships
    club = relationship("Club", back_populates="members")
    
    class Config:
        from_attributes = True
