from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

# Player Schemas
class PlayerCreate(BaseModel):
    name: str
    number: int
    position: str  # "Gardien", "Défenseur", "Milieu", "Attaquant"
    category: str  # "N3", "U19", "U17", etc.
    photo_url: Optional[str] = None
    birth_date: Optional[date] = None
    height: Optional[int] = None
    weight: Optional[int] = None

class PlayerUpdate(BaseModel):
    name: Optional[str] = None
    number: Optional[int] = None
    position: Optional[str] = None
    category: Optional[str] = None
    photo_url: Optional[str] = None
    birth_date: Optional[date] = None
    height: Optional[int] = None
    weight: Optional[int] = None
    status: Optional[str] = None

class PlayerResponse(BaseModel):
    id: str
    name: str
    number: int
    position: str
    category: str
    photo_url: Optional[str]
    birth_date: Optional[date]
    height: Optional[int]
    weight: Optional[int]
    status: str
    matches_played: int
    minutes_played: int
    created_at: datetime
    
    class Config:
        from_attributes = True
