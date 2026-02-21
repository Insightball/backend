"""
app/routes/admin.py
Routes admin — accès restreint aux superadmins uniquement
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.models import User, Club
from app.routes.auth import get_current_user  # adapte selon ton chemin

router = APIRouter()


# ─── Dependency: vérifie que l'utilisateur est superadmin ───────────────────

def require_superadmin(current_user: User = Depends(get_current_user)):
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé"
        )
    return current_user


# ─── Schemas de réponse ─────────────────────────────────────────────────────

class UserAdminView(BaseModel):
    id: str
    email: str
    name: str
    plan: str
    role: str
    is_active: bool
    is_superadmin: bool
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]
    last_login: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class DashboardStats(BaseModel):
    total_users: int
    active_users: int
    coach_plan_count: int
    club_plan_count: int
    users_last_7_days: int
    users_last_30_days: int
    paying_users: int


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardStats)
def admin_dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin)
):
    """Stats globales pour le dashboard admin"""
    now = datetime.utcnow()
    
    total = db.query(func.count(User.id)).scalar()
    active = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    coach_count = db.query(func.count(User.id)).filter(User.plan == "coach").scalar()
    club_count = db.query(func.count(User.id)).filter(User.plan == "club").scalar()
    last_7 = db.query(func.count(User.id)).filter(
        User.created_at >= now - timedelta(days=7)
    ).scalar()
    last_30 = db.query(func.count(User.id)).filter(
        User.created_at >= now - timedelta(days=30)
    ).scalar()
    paying = db.query(func.count(User.id)).filter(
        User.stripe_subscription_id != None
    ).scalar()

    return DashboardStats(
        total_users=total,
        active_users=active,
        coach_plan_count=coach_count,
        club_plan_count=club_count,
        users_last_7_days=last_7,
        users_last_30_days=last_30,
        paying_users=paying
    )


@router.get("/users", response_model=List[UserAdminView])
def admin_list_users(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    plan: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin)
):
    """Liste tous les utilisateurs avec filtres"""
    query = db.query(User)
    
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%")) | 
            (User.name.ilike(f"%{search}%"))
        )
    if plan:
        query = query.filter(User.plan == plan)
    
    return query.order_by(desc(User.created_at)).offset(skip).limit(limit).all()


@router.get("/users/{user_id}", response_model=UserAdminView)
def admin_get_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return user


@router.patch("/users/{user_id}/toggle-active")
def admin_toggle_user_active(
    user_id: str,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_superadmin)
):
    """Activer / désactiver un compte utilisateur"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="Impossible de modifier son propre compte")
    
    user.is_active = not user.is_active
    db.commit()
    return {"id": user_id, "is_active": user.is_active}


@router.get("/payments")
def admin_payments(
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin)
):
    """Utilisateurs avec abonnement Stripe actif"""
    users = db.query(User).filter(
        User.stripe_subscription_id != None
    ).order_by(desc(User.created_at)).all()
    
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "plan": u.plan,
            "stripe_customer_id": u.stripe_customer_id,
            "stripe_subscription_id": u.stripe_subscription_id,
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.get("/logins")
def admin_recent_logins(
    days: int = 30,
    db: Session = Depends(get_db),
    _: User = Depends(require_superadmin)
):
    """Utilisateurs connectés récemment"""
    since = datetime.utcnow() - timedelta(days=days)
    users = db.query(User).filter(
        User.last_login >= since
    ).order_by(desc(User.last_login)).all()
    
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "plan": u.plan,
            "last_login": u.last_login,
            "is_active": u.is_active,
        }
        for u in users
    ]
