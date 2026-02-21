from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base

class NotificationType(str, enum.Enum):
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    type = Column(Enum(NotificationType), nullable=False)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    link = Column(String, nullable=True)
    
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    class Config:
        from_attributes = True
