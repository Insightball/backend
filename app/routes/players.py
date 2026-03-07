from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.database import get_db
from app.models import User
from app.models import Player
from app.models import Match, MatchStatus, MatchType
from app.models.club_member import ClubMember, InviteStatus
from app.schemas.player import PlayerCreate, PlayerResponse, PlayerUpdate
from app.dependencies import get_current_active_user
from app.utils.club import get_managed_category

router = APIRouter()

# _get_managed_category → importé depuis app.utils.club
_get_managed_category = get_managed_category

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
    """Aggregate player stats from all completed matches, separated by type."""

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
    if managed_cat:
        match_query = match_query.filter(Match.category == managed_cat)
    matches = match_query.order_by(Match.date.desc()).all()

    # Séparer les matchs par type
    OFFICIAL_TYPES = {MatchType.CHAMPIONNAT, MatchType.COUPE}

    def _aggregate(match_list):
        """Agrège les stats du joueur depuis une liste de matchs."""
        agg = dict(
            matches_played=0, matches_starter=0, matches_sub=0,
            total_minutes=0, goals=0, assists=0, total_passes=0,
            pass_success_sum=0, pass_success_count=0,
            total_shots=0, shots_on_target=0,
            total_duels=0, duels_won=0, total_distance=0.0,
            total_key_passes=0, total_tackles=0, total_interceptions=0,
            total_saves=0, yellow_cards=0,
        )
        history = []

        for match in match_list:
            ps_list = match.player_stats
            if not isinstance(ps_list, list):
                continue
            for ps in ps_list:
                if ps.get("player_id") != player_id:
                    continue

                agg["matches_played"] += 1
                is_starter = ps.get("starter", False)
                if is_starter:
                    agg["matches_starter"] += 1
                else:
                    agg["matches_sub"] += 1

                minutes = ps.get("minutes", 0)
                agg["total_minutes"] += minutes
                agg["goals"] += ps.get("goals", 0)
                agg["assists"] += ps.get("assists", 0)
                agg["total_passes"] += ps.get("passes", 0)
                if ps.get("pass_success") is not None:
                    agg["pass_success_sum"] += ps["pass_success"]
                    agg["pass_success_count"] += 1
                agg["total_shots"] += ps.get("shots", 0)
                agg["shots_on_target"] += ps.get("shots_on_target", 0)
                agg["total_duels"] += ps.get("duels", 0)
                agg["duels_won"] += ps.get("duels_won", 0)
                agg["total_distance"] += ps.get("distance_km", 0.0)
                agg["total_key_passes"] += ps.get("key_passes", 0)
                agg["total_tackles"] += ps.get("tackles", 0)
                agg["total_interceptions"] += ps.get("interceptions", 0)
                agg["total_saves"] += ps.get("saves", 0)
                if ps.get("yellow_card"):
                    agg["yellow_cards"] += 1

                match_type_val = match.type.value if hasattr(match.type, 'value') else (match.type or 'championnat')
                history.append({
                    "match_id": match.id,
                    "opponent": match.opponent,
                    "date": match.date.isoformat() if match.date else None,
                    "score_home": match.score_home,
                    "score_away": match.score_away,
                    "is_home": match.is_home,
                    "competition": match.competition,
                    "type": match_type_val,
                    "starter": is_starter,
                    "minutes": minutes,
                    "goals": ps.get("goals", 0),
                    "assists": ps.get("assists", 0),
                    "rating": ps.get("rating"),
                })
                break

        avg_pass = round(agg["pass_success_sum"] / agg["pass_success_count"], 1) if agg["pass_success_count"] > 0 else None
        avg_dist = round(agg["total_distance"] / agg["matches_played"], 1) if agg["matches_played"] > 0 else None

        return {
            "matches_played": agg["matches_played"],
            "matches_starter": agg["matches_starter"],
            "matches_sub": agg["matches_sub"],
            "total_minutes": agg["total_minutes"],
            "goals": agg["goals"],
            "assists": agg["assists"],
            "total_passes": agg["total_passes"],
            "avg_pass_success": avg_pass,
            "total_shots": agg["total_shots"],
            "shots_on_target": agg["shots_on_target"],
            "total_duels": agg["total_duels"],
            "duels_won": agg["duels_won"],
            "total_distance_km": round(agg["total_distance"], 1),
            "avg_distance_km": avg_dist,
            "total_key_passes": agg["total_key_passes"],
            "total_tackles": agg["total_tackles"],
            "total_interceptions": agg["total_interceptions"],
            "total_saves": agg["total_saves"],
            "yellow_cards": agg["yellow_cards"],
            "match_history": history,
        }

    official_matches = [m for m in matches if m.type in OFFICIAL_TYPES]
    friendly_matches = [m for m in matches if m.type == MatchType.AMICAL]
    prepa_matches = [m for m in matches if m.type == MatchType.PREPARATION]

    return {
        "player_id": player_id,
        "official": _aggregate(official_matches),
        "friendly": _aggregate(friendly_matches),
        "preparation": _aggregate(prepa_matches),
        "all": _aggregate(matches),
    }
