from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.database import get_db
from app.models import User
from app.models import Player
from app.models import Match, MatchStatus
from app.models.club_member import ClubMember, InviteStatus
from app.schemas.player import PlayerCreate, PlayerResponse, PlayerUpdate
from app.dependencies import get_current_active_user

router = APIRouter()


def _get_managed_category(user: User, db: Session) -> str | None:
    """
    Retourne la catégorie assignée au coach membre via ClubMember.
    DS admin / superadmin → None (voit tout).
    Coach membre → sa catégorie (ex: 'U19', 'Seniors').
    """
    if user.is_superadmin:
        return None
    role_val = user.role.value if hasattr(user.role, 'value') else user.role
    if role_val == 'ADMIN':
        return None
    # Coach membre → chercher sa catégorie dans club_members
    member = db.query(ClubMember).filter(
        ClubMember.user_id == user.id,
        ClubMember.club_id == user.club_id,
        ClubMember.status == InviteStatus.ACCEPTED,
    ).first()
    if member and member.category:
        return member.category
    return None

@router.post("/", response_model=PlayerResponse, status_code=status.HTTP_201_CREATED)
async def create_player(
    player_data: PlayerCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new player"""
    
    # Coach membre → force la catégorie assignée
    managed_cat = _get_managed_category(current_user, db)
    if managed_cat and player_data.category != managed_cat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vous ne pouvez créer des joueurs que dans la catégorie {managed_cat}"
        )
    
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
        preferred_foot=player_data.preferred_foot,
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
    
    # Coach membre → ne voit que les joueurs de sa catégorie
    managed_cat = _get_managed_category(current_user, db)
    if managed_cat:
        query = query.filter(Player.category == managed_cat)
    
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
    
    # Coach membre → accès uniquement aux joueurs de sa catégorie
    managed_cat = _get_managed_category(current_user, db)
    if managed_cat and player.category != managed_cat:
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
    
    # Coach membre → modification uniquement dans sa catégorie
    managed_cat = _get_managed_category(current_user, db)
    if managed_cat and player.category != managed_cat:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez modifier que les joueurs de votre catégorie"
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
    
    # Coach membre → suppression uniquement dans sa catégorie
    managed_cat = _get_managed_category(current_user, db)
    if managed_cat and player.category != managed_cat:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez supprimer que les joueurs de votre catégorie"
        )
    
    db.delete(player)
    db.commit()
    
    return None


@router.get("/{player_id}/stats")
async def get_player_stats(
    player_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Aggregate player stats from all completed matches"""

    # Vérifier que le joueur appartient au club
    player = db.query(Player).filter(
        Player.id == player_id,
        Player.club_id == current_user.club_id
    ).first()

    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Joueur non trouvé"
        )

    # Coach membre → accès uniquement aux joueurs de sa catégorie
    managed_cat = _get_managed_category(current_user, db)
    if managed_cat and player.category != managed_cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Joueur non trouvé"
        )

    # Récupérer tous les matchs completed du club qui ont des player_stats
    match_query = db.query(Match).filter(
        Match.club_id == current_user.club_id,
        Match.status == MatchStatus.COMPLETED,
        Match.player_stats != None,
    )
    # Coach membre → uniquement les matchs de sa catégorie
    if managed_cat:
        match_query = match_query.filter(Match.category == managed_cat)
    matches = match_query.order_by(Match.date.desc()).all()

    # Agréger les stats
    total_matches = 0
    total_starter = 0
    total_sub = 0
    total_minutes = 0
    total_goals = 0
    total_assists = 0
    total_passes = 0
    total_pass_success_sum = 0
    total_pass_success_count = 0
    total_shots = 0
    total_shots_on_target = 0
    total_duels = 0
    total_duels_won = 0
    total_distance = 0.0
    total_key_passes = 0
    total_tackles = 0
    total_interceptions = 0
    total_saves = 0
    total_yellow_cards = 0
    match_history = []

    for match in matches:
        ps_list = match.player_stats
        if not isinstance(ps_list, list):
            continue

        for ps in ps_list:
            if ps.get("player_id") != player_id:
                continue

            # Ce joueur a participé à ce match
            total_matches += 1
            is_starter = ps.get("starter", False)
            if is_starter:
                total_starter += 1
            else:
                total_sub += 1

            minutes = ps.get("minutes", 0)
            total_minutes += minutes
            total_goals += ps.get("goals", 0)
            total_assists += ps.get("assists", 0)
            total_passes += ps.get("passes", 0)
            if ps.get("pass_success") is not None:
                total_pass_success_sum += ps["pass_success"]
                total_pass_success_count += 1
            total_shots += ps.get("shots", 0)
            total_shots_on_target += ps.get("shots_on_target", 0)
            total_duels += ps.get("duels", 0)
            total_duels_won += ps.get("duels_won", 0)
            total_distance += ps.get("distance_km", 0.0)
            total_key_passes += ps.get("key_passes", 0)
            total_tackles += ps.get("tackles", 0)
            total_interceptions += ps.get("interceptions", 0)
            total_saves += ps.get("saves", 0)
            if ps.get("yellow_card"):
                total_yellow_cards += 1

            # Historique match
            match_history.append({
                "match_id": match.id,
                "opponent": match.opponent,
                "date": match.date.isoformat() if match.date else None,
                "score_home": match.score_home,
                "score_away": match.score_away,
                "is_home": match.is_home,
                "competition": match.competition,
                "starter": is_starter,
                "minutes": minutes,
                "goals": ps.get("goals", 0),
                "assists": ps.get("assists", 0),
                "rating": ps.get("rating"),
            })
            break  # Un joueur ne peut apparaître qu'une fois par match

    avg_pass_success = round(total_pass_success_sum / total_pass_success_count, 1) if total_pass_success_count > 0 else None
    avg_distance = round(total_distance / total_matches, 1) if total_matches > 0 else None

    return {
        "player_id": player_id,
        "matches_played": total_matches,
        "matches_starter": total_starter,
        "matches_sub": total_sub,
        "total_minutes": total_minutes,
        "goals": total_goals,
        "assists": total_assists,
        "total_passes": total_passes,
        "avg_pass_success": avg_pass_success,
        "total_shots": total_shots,
        "shots_on_target": total_shots_on_target,
        "total_duels": total_duels,
        "duels_won": total_duels_won,
        "total_distance_km": round(total_distance, 1),
        "avg_distance_km": avg_distance,
        "total_key_passes": total_key_passes,
        "total_tackles": total_tackles,
        "total_interceptions": total_interceptions,
        "total_saves": total_saves,
        "yellow_cards": total_yellow_cards,
        "match_history": match_history,
    }
