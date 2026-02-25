from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import PlanType, MatchStatus, MatchType

# Auth Schemas
class UserSignup(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    plan: PlanType
    club_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    plan: str
    role: Optional[str] = None
    club_name: Optional[str] = None
    club_id: Optional[str] = None

    class Config:
        from_attributes = True

# Match Schemas
class MatchCreate(BaseModel):
    opponent: str
    date: datetime
    category: str
    type: Optional[MatchType] = None
    video_url: Optional[str] = None

class MatchUpdate(BaseModel):
    opponent: Optional[str] = None
    date: Optional[datetime] = None
    category: Optional[str] = None
    type: Optional[MatchType] = None
    score_home: Optional[int] = None
    score_away: Optional[int] = None
    competition: Optional[str] = None
    location: Optional[str] = None

class MatchResponse(BaseModel):
    id: str
    opponent: str
    date: datetime
    category: Optional[str] = None
    type: Optional[str] = None
    status: str
    progress: Optional[int] = 0
    video_url: Optional[str] = None
    pdf_url: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    score_home: Optional[int] = None
    score_away: Optional[int] = None
    competition: Optional[str] = None
    location: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Club Schemas
class ClubCreate(BaseModel):
    name: str

class ClubResponse(BaseModel):
    id: str
    name: str
    quota_matches: int
    created_at: datetime

    class Config:
        from_attributes = True

# Upload Schemas
class S3PresignedUrlRequest(BaseModel):
    filename: str
    content_type: str

class S3PresignedUrlResponse(BaseModel):
    upload_url: str
    file_key: str
    expires_in: int
