from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Enum, JSON, Float
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base

class PlanType(str, enum.Enum):
    COACH = "coach"
    CLUB = "club"

class MatchStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"

class MatchType(str, enum.Enum):
    CHAMPIONNAT = "championnat"
    COUPE = "coupe"
    AMICAL = "amical"

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    COACH = "coach"
    ANALYST = "analyst"

# User Model
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
    matches = relationship("Match", back_populates="user", cascade="all, delete-orphan")

# Club Model (for CLUB plan)
class Club(Base):
    __tablename__ = "clubs"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    
    # Identité visuelle
    logo_url = Column(String, nullable=True)
    primary_color = Column(String, nullable=True)  # Hex color #5EEAD4
    secondary_color = Column(String, nullable=True)
    
    # Stripe info
    stripe_customer_id = Column(String, unique=True)
    stripe_subscription_id = Column(String)
    
    # Quotas
    quota_matches = Column(Integer, default=10)  # Monthly quota
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    members = relationship("User", back_populates="club")
    matches = relationship("Match", back_populates="club", cascade="all, delete-orphan")

# Match Model
class Match(Base):
    __tablename__ = "matches"
    
    id = Column(String, primary_key=True, index=True)
    
    # User/Club
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    club_id = Column(String, ForeignKey("clubs.id"), nullable=True)
    
    # Match info
    opponent = Column(String, nullable=False)
    date = Column(DateTime, nullable=False)
    category = Column(String, nullable=False)  # N3, U19, U17, etc.
    type = Column(Enum(MatchType), nullable=False)
    
    # Files
    video_url = Column(String, nullable=False)  # S3 URL
    pdf_url = Column(String, nullable=True)  # Generated PDF
    
    # Processing
    status = Column(Enum(MatchStatus), default=MatchStatus.PENDING)
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(String, nullable=True)
    
    # Stats (JSON field)
    stats = Column(JSON, nullable=True)
    # Example: {"possession": 58, "passes": 482, "shots": 18, ...}
    
    # Metadata
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="matches")
    club = relationship("Club", back_populates="matches")
