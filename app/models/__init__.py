from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Enum, JSON, Float, Date
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
    players = relationship("Player", back_populates="user", cascade="all, delete-orphan")

# Club Model (for CLUB plan)
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
    category = Column(String, nullable=False)
    type = Column(Enum(MatchType), nullable=False)
    
    # Files
    video_url = Column(String, nullable=False)
    pdf_url = Column(String, nullable=True)
    
    # Processing
    status = Column(Enum(MatchStatus), default=MatchStatus.PENDING)
    progress = Column(Integer, default=0)
    error_message = Column(String, nullable=True)
    
    # Stats (JSON field)
    stats = Column(JSON, nullable=True)
    
    # Metadata
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="matches")
    club = relationship("Club", back_populates="matches")

# Player Model
class PlayerPosition(str, enum.Enum):
    GK = "Gardien"
    DEF = "Défenseur"
    MID = "Milieu"
    ATT = "Attaquant"

class PlayerStatus(str, enum.Enum):
    ACTIVE = "actif"
    INJURED = "blessé"
    SUSPENDED = "suspendu"
    INACTIVE = "inactif"

class Player(Base):
    __tablename__ = "players"
    
    id = Column(String, primary_key=True, index=True)
    
    # Club/User
    club_id = Column(String, ForeignKey("clubs.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    # Info joueur
    name = Column(String, nullable=False)
    number = Column(Integer, nullable=False)
    position = Column(Enum(PlayerPosition), nullable=False)
    
    # Catégorie
    category = Column(String, nullable=False)
    
    # Photo
    photo_url = Column(String, nullable=True)
    
    # Infos complémentaires
    birth_date = Column(Date, nullable=True)
    height = Column(Integer, nullable=True)
    weight = Column(Integer, nullable=True)
    
    # Status
    status = Column(Enum(PlayerStatus), default=PlayerStatus.ACTIVE)
    
    # Stats agrégées
    matches_played = Column(Integer, default=0)
    minutes_played = Column(Integer, default=0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    club = relationship("Club", back_populates="players")
    user = relationship("User", back_populates="players")