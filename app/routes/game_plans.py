from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import uuid

from app.database import get_db
from app.models import User
from app.models.game_plan import GamePlan
from app.dependencies import get_current_user

router = APIRouter()


class GamePlanPayload(BaseModel):
    formation: str = "4-3-3"
    category: str = "Seniors"
    principles: List[str] = []
    training_days: List[str] = ["mardi", "jeudi"]
    training_time: str = "19:00"
    start_date: Optional[str] = None
    programming: Optional[dict] = None


class GamePlanResponse(BaseModel):
    id: str
    formation: str
    category: str
    principles: list
    training_days: list
    training_time: str
    start_date: Optional[str] = None
    programming: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("", response_model=Optional[GamePlanResponse])
async def get_game_plan(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Récupère le projet de jeu du coach."""
    plan = db.query(GamePlan).filter(GamePlan.user_id == current_user.id).first()
    if not plan:
        return None
    return GamePlanResponse(
        id=plan.id,
        formation=plan.formation,
        category=plan.category,
        principles=plan.principles or [],
        training_days=plan.training_days or [],
        training_time=plan.training_time or "19:00",
        start_date=plan.start_date.isoformat() if plan.start_date else None,
        programming=plan.programming,
        created_at=plan.created_at.isoformat() if plan.created_at else None,
        updated_at=plan.updated_at.isoformat() if plan.updated_at else None,
    )


@router.put("")
async def save_game_plan(
    body: GamePlanPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crée ou met à jour le projet de jeu du coach (upsert)."""
    plan = db.query(GamePlan).filter(GamePlan.user_id == current_user.id).first()

    start_d = None
    if body.start_date:
        try:
            start_d = date.fromisoformat(body.start_date)
        except (ValueError, TypeError):
            pass

    if plan:
        plan.formation = body.formation
        plan.category = body.category
        plan.principles = body.principles
        plan.training_days = body.training_days
        plan.training_time = body.training_time
        plan.start_date = start_d
        plan.programming = body.programming
        plan.updated_at = datetime.utcnow()
    else:
        plan = GamePlan(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            club_id=current_user.club_id,
            formation=body.formation,
            category=body.category,
            principles=body.principles,
            training_days=body.training_days,
            training_time=body.training_time,
            start_date=start_d,
            programming=body.programming,
        )
        db.add(plan)

    db.commit()
    db.refresh(plan)

    return {
        "message": "Projet de jeu enregistré",
        "id": plan.id,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }
