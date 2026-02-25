from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PlayerBase(BaseModel):
    name: str
    number: int
    position: str
    category: Optional[str] = "N3"
    photo_url: Optional[str] = None
    birth_date: Optional[datetime] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    preferred_foot: Optional[str] = None  # 'droit' | 'gauche' | 'ambidextre'

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
    preferred_foot: Optional[str] = None  # 'droit' | 'gauche' | 'ambidextre'

class PlayerResponse(PlayerBase):
    id: str
    club_id: Optional[str] = None
    status: Optional[str] = "actif"
    preferred_foot: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
