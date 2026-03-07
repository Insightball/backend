from sqlalchemy import Column, String, Date, DateTime, ForeignKey, JSON
from datetime import datetime
from app.database import Base


class GamePlan(Base):
    __tablename__ = "game_plans"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    club_id = Column(String, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True)

    formation = Column(String, default="4-3-3")
    category = Column(String, default="Seniors")
    principles = Column(JSON, default=[])
    training_days = Column(JSON, default=["mardi", "jeudi"])
    training_time = Column(String, default="19:00")
    start_date = Column(Date, nullable=True)
    programming = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class Config:
        from_attributes = True
