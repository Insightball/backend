from fastapi import APIRouter, Depends, HTTPException, status
import uuid
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Club
from app.dependencies import get_current_active_user

router = APIRouter()

class ClubCreate(BaseModel):
    name: str
    primary_color: Optional[str] = '#c9a227'
    secondary_color: Optional[str] = '#0f0f0d'

class ClubUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None

class ClubResponse(BaseModel):
    id: str
    name: str
    logo_url: Optional[str]
    primary_color: Optional[str]
    secondary_color: Optional[str]
    quota_matches: int
    class Config:
        from_attributes = True

@router.post("/", response_model=ClubResponse)
async def create_club(club_data: ClubCreate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Crée un club et l'associe à l'utilisateur courant"""
    if current_user.club_id:
        # Club déjà existant — juste mettre à jour
        club = db.query(Club).filter(Club.id == current_user.club_id).first()
        if club:
            club.name = club_data.name
            if club_data.primary_color: club.primary_color = club_data.primary_color
            if club_data.secondary_color: club.secondary_color = club_data.secondary_color
            db.commit(); db.refresh(club)
            return club
    # Créer le club
    club = Club(
        id=str(uuid.uuid4()),
        name=club_data.name,
        primary_color=club_data.primary_color,
        secondary_color=club_data.secondary_color,
        quota_matches=10,
    )
    db.add(club)
    db.flush()
    # Associer l'utilisateur
    current_user.club_id = club.id
    from app.models.user import RoleType
    current_user.role = RoleType.ADMIN
    db.commit(); db.refresh(club)
    return club

@router.get("/me", response_model=ClubResponse)
async def get_my_club(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not current_user.club_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vous n'êtes pas dans un club")
    club = db.query(Club).filter(Club.id == current_user.club_id).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Club non trouvé")
    return club

@router.patch("/me", response_model=ClubResponse)
async def update_my_club(club_data: ClubUpdate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not current_user.club_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vous n'êtes pas dans un club")
    role_val = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if role_val != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seul l'administrateur peut modifier le club")
    club = db.query(Club).filter(Club.id == current_user.club_id).first()
    if not club:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Club non trouvé")
    update_data = club_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(club, field, value)
    db.commit()
    db.refresh(club)
    return club
