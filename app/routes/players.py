from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.database import get_db
from app.models import User
from app.models import Player
from app.schemas.player import PlayerCreate, PlayerResponse, PlayerUpdate
from app.dependencies import get_current_active_user

router = APIRouter()

@router.post("/", response_model=PlayerResponse, status_code=status.HTTP_201_CREATED)
async def create_player(
    player_data: PlayerCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new player"""
    
    # Check if number already exists for this category
    existing = db.query(Player).filter(
        Player.club_id == current_user.club_id,
        Player.category == player_data.category,
        Player.number == player_data.number
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Le numéro {player_data.number} est déjà utilisé dans {player_data.category}"
        )
    
    player = Player(
        id=str(uuid.uuid4()),
        club_id=current_user.club_id,
        name=player_data.name,
        number=player_data.number,
        position=player_data.position,
        category=player_data.category,
        photo_url=player_data.photo_url,
        birth_date=player_data.birth_date,
        height=player_data.height,
        weight=player_data.weight,
status="actif"
    )
    
    db.add(player)
    db.commit()
    db.refresh(player)
    
    return player

@router.get("/", response_model=List[PlayerResponse])
async def get_players(
    category: str = None,
    status: str = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all players for current user's club"""
    
    query = db.query(Player).filter(Player.club_id == current_user.club_id)
    
    # Apply filters
    if category:
        query = query.filter(Player.category == category)
    if status:
        query = query.filter(Player.status == status)
    
    # Order by number
    players = query.order_by(Player.number).all()
    
    return players

@router.get("/{player_id}", response_model=PlayerResponse)
async def get_player(
    player_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific player"""
    
    player = db.query(Player).filter(
        Player.id == player_id,
        Player.club_id == current_user.club_id
    ).first()
    
    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Joueur non trouvé"
        )
    
    return player

@router.patch("/{player_id}", response_model=PlayerResponse)
async def update_player(
    player_id: str,
    player_data: PlayerUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update a player"""
    
    player = db.query(Player).filter(
        Player.id == player_id,
        Player.club_id == current_user.club_id
    ).first()
    
    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Joueur non trouvé"
        )
    
    # Check if number change conflicts
    if player_data.number and player_data.number != player.number:
        existing = db.query(Player).filter(
            Player.club_id == current_user.club_id,
            Player.category == player.category,
            Player.number == player_data.number,
            Player.id != player_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Le numéro {player_data.number} est déjà utilisé"
            )
    
    # Update fields
    update_data = player_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(player, field, value)
    
    db.commit()
    db.refresh(player)
    
    return player

@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_player(
    player_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a player"""
    
    player = db.query(Player).filter(
        Player.id == player_id,
        Player.club_id == current_user.club_id
    ).first()
    
    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Joueur non trouvé"
        )
    
    db.delete(player)
    db.commit()
    
    return None
