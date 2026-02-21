from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PlayerBase(BaseModel):
    name: str
    number: int
    position: str
    category: str = "N3"
    photo_url: Optional[str] = None
    birth_date: Optional[datetime] = None
    height: Optional[float] = None
    weight: Optional[float] = None

class PlayerCreate(PlayerBase):
    pass

class PlayerUpdate(BaseModel):
    name: Optional[str] = None
    number: Optional[int] = None
    position: Optional[str] = None
    category: Optional[str] = None
    photo_url: Optional[str] = None
    birth_date: Optional[datetime] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    status: Optional[str] = None

class PlayerResponse(PlayerBase):
    id: str
    club_id: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
