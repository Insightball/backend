from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List
import uuid
from datetime import datetime

from app.database import get_db
from app.models import User, Match, MatchStatus
from app.schemas import MatchCreate, MatchResponse, MatchUpdate
from app.dependencies import get_current_active_user

router = APIRouter()

# ─────────────────────────────────────────────
# SOURCE UNIQUE DE VÉRITÉ — quotas par plan
# Toute modification de pricing doit passer ici
# ─────────────────────────────────────────────
PLAN_MATCH_QUOTAS = {
    "COACH": 4,
    "CLUB":  12,
}

def get_monthly_match_count(db: Session, club_id: str) -> int:
    """Compte les matchs uploadés ce mois civil (peu importe le statut)."""
    now = datetime.utcnow()
    return db.query(Match).filter(
        Match.club_id == club_id,
        extract('year',  Match.uploaded_at) == now.year,
        extract('month', Match.uploaded_at) == now.month,
    ).count()

@router.post("/", response_model=MatchResponse, status_code=status.HTTP_201_CREATED)
async def create_match(
    match_data: MatchCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new match — vérifie le quota mensuel avant création."""

    # ── Quota check ──────────────────────────────
    plan_str = (
        current_user.plan.value
        if hasattr(current_user.plan, 'value')
        else str(current_user.plan)
    ).upper()

    quota = PLAN_MATCH_QUOTAS.get(plan_str, 4)  # défaut conservateur : 4
    used  = get_monthly_match_count(db, current_user.club_id)

    if used >= quota:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code":    "QUOTA_EXCEEDED",
                "message": f"Quota mensuel atteint ({used}/{quota} matchs). Passez au plan supérieur pour continuer.",
                "used":    used,
                "quota":   quota,
                "plan":    plan_str,
            }
        )
    # ─────────────────────────────────────────────

    match = Match(
        id=str(uuid.uuid4()),
        club_id=current_user.club_id,
        opponent=match_data.opponent,
        date=match_data.date,
        category=match_data.category,
        type=match_data.type,
        video_url=match_data.video_url,
        status=MatchStatus.PENDING
    )
    
    db.add(match)
    db.commit()
    db.refresh(match)
    
    # TODO: Trigger Celery task for video processing
    # process_video.delay(match.id)
    
    return match

@router.get("/", response_model=List[MatchResponse])
async def get_matches(
    skip: int = 0,
    limit: int = 100,
    category: str = None,
    status: str = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all matches for current user"""
    
    query = db.query(Match).filter(Match.club_id == current_user.club_id)
    
    # Apply filters
    if category:
        query = query.filter(Match.category == category)
    if status:
        query = query.filter(Match.status == status)
    
    # Order by date descending
    matches = query.order_by(Match.uploaded_at.desc()).offset(skip).limit(limit).all()
    
    return matches

@router.get("/{match_id}", response_model=MatchResponse)
async def get_match(
    match_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific match"""
    
    match = db.query(Match).filter(
        Match.id == match_id,
        Match.club_id == current_user.club_id
    ).first()
    
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not found"
        )
    
    return match

@router.patch("/{match_id}", response_model=MatchResponse)
async def update_match(
    match_id: str,
    match_data: MatchUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update a match"""
    
    match = db.query(Match).filter(
        Match.id == match_id,
        Match.club_id == current_user.club_id
    ).first()
    
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not found"
        )
    
    # Update fields
    update_data = match_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(match, field, value)
    
    db.commit()
    db.refresh(match)
    
    return match

@router.delete("/{match_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_match(
    match_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a match"""
    
    match = db.query(Match).filter(
        Match.id == match_id,
        Match.club_id == current_user.club_id
    ).first()
    
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not found"
        )
    
    # TODO: Delete video from S3
    # TODO: Delete PDF from S3
    
    db.delete(match)
    db.commit()
    
    return None

# ─────────────────────────────────────────────
# QUOTA STATUS — appelé par le dashboard
# ─────────────────────────────────────────────
@router.get("/quota/status")
async def get_quota_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Retourne le quota mensuel et l'utilisation courante."""
    plan_str = (
        current_user.plan.value
        if hasattr(current_user.plan, 'value')
        else str(current_user.plan)
    ).upper()

    quota = PLAN_MATCH_QUOTAS.get(plan_str, 4)
    used  = get_monthly_match_count(db, current_user.club_id)

    return {
        "plan":      plan_str,
        "quota":     quota,
        "used":      used,
        "remaining": max(0, quota - used),
        "exceeded":  used >= quota,
    }
