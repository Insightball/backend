from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr
import uuid

from app.database import get_db
from app.models import User, Club
from app.models.club_member import ClubMember
from app.utils.auth import get_password_hash
from app.dependencies import get_current_user

router = APIRouter()


def require_superadmin(current_user: User = Depends(get_current_user)):
    if not current_user.is_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé")
    return current_user


class UserAdminView(BaseModel):
    id: str
    email: str
    name: str
    plan: str
    role: str
    is_active: bool
    is_superadmin: bool
    club_id: Optional[str] = None
    club_name: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    profile_role: Optional[str] = None
    profile_level: Optional[str] = None
    profile_phone: Optional[str] = None
    profile_city: Optional[str] = None
    profile_diploma: Optional[str] = None
    trial_match_used: Optional[bool] = None
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

class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    plan: str
    role: str = "ADMIN"
    club_name: Optional[str] = None
    club_id: Optional[str] = None
    is_superadmin: bool = False

class UpdateUserPlanRequest(BaseModel):
    plan: str
    club_name: Optional[str] = None
    club_id: Optional[str] = None
    role: Optional[str] = None


@router.get("/dashboard", response_model=DashboardStats)
def admin_dashboard(db: Session = Depends(get_db), _: User = Depends(require_superadmin)):
    now = datetime.utcnow()
    return DashboardStats(
        total_users=db.query(func.count(User.id)).scalar(),
        active_users=db.query(func.count(User.id)).filter(User.is_active == True).scalar(),
        coach_plan_count=db.query(func.count(User.id)).filter(User.plan == "COACH").scalar(),
        club_plan_count=db.query(func.count(User.id)).filter(User.plan == "CLUB").scalar(),
        users_last_7_days=db.query(func.count(User.id)).filter(User.created_at >= now - timedelta(days=7)).scalar(),
        users_last_30_days=db.query(func.count(User.id)).filter(User.created_at >= now - timedelta(days=30)).scalar(),
        paying_users=db.query(func.count(User.id)).filter(User.stripe_subscription_id != None).scalar(),
    )


@router.get("/users", response_model=List[UserAdminView])
def admin_list_users(skip: int = 0, limit: int = 50, search: Optional[str] = None, plan: Optional[str] = None,
                     db: Session = Depends(get_db), _: User = Depends(require_superadmin)):
    query = db.query(User)
    if search:
        query = query.filter((User.email.ilike(f"%{search}%")) | (User.name.ilike(f"%{search}%")))
    if plan:
        query = query.filter(User.plan == plan.upper())
    users = query.order_by(desc(User.created_at)).offset(skip).limit(limit).all()
    return [UserAdminView(
        id=u.id, email=u.email, name=u.name,
        plan=u.plan.value if hasattr(u.plan, 'value') else u.plan,
        role=u.role.value if hasattr(u.role, 'value') else (u.role or 'ADMIN'),
        is_active=u.is_active, is_superadmin=u.is_superadmin,
        club_id=u.club_id, club_name=u.club.name if u.club else None,
        stripe_customer_id=u.stripe_customer_id, stripe_subscription_id=u.stripe_subscription_id,
        last_login=u.last_login, created_at=u.created_at,
        profile_role=u.profile_role, profile_level=u.profile_level,
        profile_phone=u.profile_phone, profile_city=u.profile_city,
        profile_diploma=u.profile_diploma,
        trial_match_used=getattr(u, 'trial_match_used', False),
    ) for u in users]


@router.get("/users/{user_id}", response_model=UserAdminView)
def admin_get_user(user_id: str, db: Session = Depends(get_db), _: User = Depends(require_superadmin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return UserAdminView(
        id=u.id, email=u.email, name=u.name,
        plan=u.plan.value if hasattr(u.plan, 'value') else u.plan,
        role=u.role.value if hasattr(u.role, 'value') else (u.role or 'ADMIN'),
        is_active=u.is_active, is_superadmin=u.is_superadmin,
        club_id=u.club_id, club_name=u.club.name if u.club else None,
        stripe_customer_id=u.stripe_customer_id, stripe_subscription_id=u.stripe_subscription_id,
        last_login=u.last_login, created_at=u.created_at,
        profile_role=u.profile_role, profile_level=u.profile_level,
        profile_phone=u.profile_phone, profile_city=u.profile_city,
        profile_diploma=u.profile_diploma,
        trial_match_used=getattr(u, 'trial_match_used', False),
    )


@router.post("/users", status_code=201)
def admin_create_user(body: CreateUserRequest, db: Session = Depends(get_db), _: User = Depends(require_superadmin)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    club_id = body.club_id
    if body.plan.upper() == "CLUB":
        if not club_id:
            if not body.club_name:
                raise HTTPException(status_code=400, detail="club_name ou club_id requis pour le plan Club")
            club = Club(id=str(uuid.uuid4()), name=body.club_name, quota_matches=10)
            db.add(club); db.flush()
            club_id = club.id
    user = User(
        id=str(uuid.uuid4()), email=body.email,
        hashed_password=get_password_hash(body.password),
        name=body.name, plan=body.plan.upper(), role=body.role.upper(),
        club_id=club_id, is_superadmin=body.is_superadmin, is_active=True,
    )
    db.add(user); db.commit()
    return {"message": "Utilisateur créé", "id": user.id}


@router.patch("/users/{user_id}/plan")
def admin_update_user_plan(user_id: str, body: UpdateUserPlanRequest,
                            db: Session = Depends(get_db), current_admin: User = Depends(require_superadmin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    user.plan = body.plan.upper()
    if body.plan.upper() == "CLUB":
        club_id = body.club_id
        if not club_id:
            if not body.club_name:
                raise HTTPException(status_code=400, detail="club_name ou club_id requis pour le plan Club")
            club = Club(id=str(uuid.uuid4()), name=body.club_name, quota_matches=10)
            db.add(club); db.flush()
            club_id = club.id
        user.club_id = club_id
        user.role = (body.role or "ADMIN").upper()
    else:
        user.club_id = None
        user.role = "ADMIN"
    db.commit()
    return {"message": "Plan mis à jour", "plan": body.plan}


@router.patch("/users/{user_id}/toggle-active")
def admin_toggle_user_active(user_id: str, db: Session = Depends(get_db), current_admin: User = Depends(require_superadmin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="Impossible de modifier son propre compte")
    user.is_active = not user.is_active
    db.commit()
    return {"id": user_id, "is_active": user.is_active}


@router.delete("/users/{user_id}", status_code=204)
def admin_delete_user(user_id: str, db: Session = Depends(get_db), current_admin: User = Depends(require_superadmin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="Impossible de supprimer son propre compte")
    db.query(ClubMember).filter((ClubMember.user_id == user_id) | (ClubMember.invited_by == user_id)).delete()
    db.delete(user); db.commit()


@router.get("/payments")
def admin_payments(db: Session = Depends(get_db), _: User = Depends(require_superadmin)):
    users = db.query(User).filter(User.stripe_subscription_id != None).order_by(desc(User.created_at)).all()
    return [{"id": u.id, "name": u.name, "email": u.email,
             "plan": u.plan.value if hasattr(u.plan, 'value') else u.plan,
             "stripe_customer_id": u.stripe_customer_id,
             "stripe_subscription_id": u.stripe_subscription_id,
             "created_at": u.created_at} for u in users]


@router.get("/logins")
def admin_recent_logins(days: int = 30, db: Session = Depends(get_db), _: User = Depends(require_superadmin)):
    since = datetime.utcnow() - timedelta(days=days)
    users = db.query(User).filter(User.last_login >= since).order_by(desc(User.last_login)).all()
    return [{"id": u.id, "name": u.name, "email": u.email,
             "plan": u.plan.value if hasattr(u.plan, 'value') else u.plan,
             "last_login": u.last_login, "is_active": u.is_active} for u in users]
