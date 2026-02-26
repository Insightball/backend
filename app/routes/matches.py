from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime

from app.database import get_db
from app.models import User, Match, MatchStatus
from app.schemas import MatchCreate, MatchResponse, MatchUpdate
from app.dependencies import get_current_active_user
from app.config import settings
import boto3

router = APIRouter()

@router.post("/", response_model=MatchResponse, status_code=status.HTTP_201_CREATED)
async def create_match(
    match_data: MatchCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new match"""
    
    match = Match(
        id=str(uuid.uuid4()),
        club_id=current_user.club_id,
        opponent=match_data.opponent,
        date=match_data.date,
        category=match_data.category,
        type=match_data.type,
        competition=getattr(match_data, 'competition', None),
        location=getattr(match_data, 'location', None),
        is_home=getattr(match_data, 'is_home', True),
        formation=getattr(match_data, 'formation', None),
        score_home=getattr(match_data, 'score_home', None),
        score_away=getattr(match_data, 'score_away', None),
        lineup=getattr(match_data, 'lineup', None),
        events=getattr(match_data, 'events', None),
        video_url=match_data.video_url,
        status=MatchStatus.PENDING
    )
    
    db.add(match)
    db.commit()
    db.refresh(match)

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
    
    # Supprimer la vidéo S3 si elle existe
    if match.video_url:
        try:
            s3 = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            # video_url format: videos/{user_id}/{uuid}.mp4
            file_key = match.video_url
            s3.delete_object(Bucket=settings.AWS_BUCKET_NAME, Key=file_key)
        except Exception:
            pass  # Ne pas bloquer la suppression si S3 échoue

    # Supprimer le PDF S3 si il existe
    if match.pdf_url:
        try:
            s3 = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            s3.delete_object(Bucket=settings.AWS_BUCKET_NAME, Key=match.pdf_url)
        except Exception:
            pass

    db.delete(match)
    db.commit()
    
    return None


@router.patch("/{match_id}/analysis", response_model=MatchResponse)
async def update_match_analysis(
    match_id: str,
    analysis: dict,
    db: Session = Depends(get_db)
):
    """
    Endpoint réservé au worker IA.
    Met à jour les résultats d'analyse d'un match.
    Corps attendu:
    {
        "status": "completed",
        "progress": 100,
        "stats": {...},
        "player_stats": [...],
        "events": [...],
        "analysis_data": {...},
        "ai_insights": "texte généré",
        "pdf_url": "pdfs/{match_id}/rapport.pdf",
        "processed_at": "2026-02-26T22:00:00"
    }
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    allowed = ['status', 'progress', 'stats', 'player_stats', 'events',
               'analysis_data', 'ai_insights', 'pdf_url', 'processed_at',
               'error_message', 'formation', 'opponent_formation']

    for key, value in analysis.items():
        if key in allowed:
            setattr(match, key, value)

    match.updated_at = datetime.utcnow()
    if analysis.get('status') == 'completed':
        match.processed_at = datetime.utcnow()
        match.progress = 100

    db.commit()
    db.refresh(match)
    return match
