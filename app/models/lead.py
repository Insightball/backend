from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from app.database import Base

class Lead(Base):
    __tablename__ = "leads"

    id         = Column(String, primary_key=True)
    first_name = Column(String, nullable=True)
    last_name  = Column(String, nullable=True)
    email      = Column(String, nullable=False, index=True)
    club_name  = Column(String, nullable=True)
    role       = Column(String, nullable=True)   # Éducateur | Entraîneur | Directeur Sportif
    category   = Column(String, nullable=True)   # U14 … Séniors
    plan       = Column(String, nullable=True)
    message    = Column(Text, nullable=True)
    type       = Column(String, default="waitlist")
    created_at = Column(DateTime, default=datetime.utcnow)
