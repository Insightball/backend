from sqlalchemy import Column, String, Boolean, DateTime, Enum
from datetime import datetime
import enum
from app.database import Base

class NotificationType(str, enum.Enum):
    SUCCESS = "success"  # Match analysé
    WARNING = "warning"  # Quota bientôt atteint
    ERROR = "error"      # Erreur analyse
    INFO = "info"        # Info générale

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    
    # Content
    type = Column(Enum(NotificationType), nullable=False)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    
    # Link (optional)
    link = Column(String, nullable=True)
    
    # Status
    read = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    class Config:
        from_attributes = True
