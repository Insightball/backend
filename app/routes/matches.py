from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from app.database import get_db
from app.models import Match, MatchStatus, MatchType, User, PlanType, Club
from app.dependencies import get_current_user

router = APIRouter()

PLAN_QUOTAS = {
    PlanType.COACH:    4,
    PlanType.CLUB:     10,
    PlanType.CLUB_PRO: 15,
}

TRIAL_MATCH_LIMIT = 1


def get_user_quota(user: User) -> int:
    if user.quota_override is not None and user.quota_override > 0:
        return user.quota_override
    return PLAN_QUOTAS.get(user.plan, PLAN_QUOTAS[PlanType.COACH])


def get_billing_user(user: User, db: Session) -> User:
    """Pool commun club : membres partagent le quota du DS admin."""
    if user.stripe_subscription_id:
        return user
    if not user.club_id:
        return user
    club_admin = db.query(User).filter(
        User.club_id == user.club_id,
        User.stripe_subscription_id != None,
        User.plan.in_([PlanType.CLUB, PlanType.CLUB_PRO]),
    ).first()
    if club_admin:
        return club_admin
    return user


def get_billing_period(user: User):
    if user.current_period_start and user.current_period_end:
        return user.current_period_start, user.current_period_end
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        end = start.replace(year=now.year + 1, month=1)
    else:
        end = start.replace(month=now.month + 1)
    return start, end


def _is_club_admin(user: User) -> bool:
    return (
        user.plan in [PlanType.CLUB, PlanType.CLUB_PRO]
        and user.role in ['ADMIN', 'admin']
    )


def check_and_consume_quota(user: User, db: Session) -> None:
    if user.is_superadmin:
        return
    if not user.plan:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="NO_ACTIVE_PLAN")

    billing_user = get_billing_user(user, db)

    if billing_user.stripe_subscription_id:
        now = datetime.utcnow()
        if billing_user.trial_ends_at and now < billing_user.trial_ends_at:
            if user.trial_match_used:
                raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="TRIAL_EXHAUSTED")
            updated = db.query(User).filter(
                User.id == user.id,
                User.trial_match_used == False
            ).update({"trial_match_used": True})
            db.commit()
            if updated == 0:
                raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="TRIAL_EXHAUSTED")
            return

        quota = get_user_quota(billing_user)
        start, end = get_billing_period(billing_user)
        club_id = billing_user.club_id or _get_solo_club_id(user, db)
        trial_cutoff = billing_user.trial_ends_at or start
        count = db.query(Match).filter(
            Match.club_id == club_id,
            Match.created_at >= start,
            Match.created_at < end,
            Match.created_at >= trial_cutoff,
        ).count()
        if count >= quota:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "plan": billing_user.plan.value if hasattr(billing_user.plan, 'value') else billing_user.plan,
                    "quota": quota,
                    "used": count,
                    "resets_at": end.isoformat() + "Z",
                    "message": f"Quota atteint ({quota} matchs). Renouvellement le {end.strftime('%d/%m/%Y')}."
                }
            )
        return

    now = datetime.utcnow()
    if user.trial_ends_at and now < user.trial_ends_at:
        updated = db.query(User).filter(
            User.id == user.id,
            User.trial_match_used == False
        ).update({"trial_match_used": True})
        db.commit()
        if updated == 0:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="TRIAL_EXHAUSTED")
        return

    raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="NO_SUBSCRIPTION")


def _get_solo_club_id(user: User, db: Session) -> str:
    if user.club_id:
        return user.club_id
    solo_club = db.query(Club).filter(Club.id == user.id).first()
    if not solo_club:
        solo_club = Club(
            id=user.id,
            name=f"Coach — {user.name}",
            quota_matches=PLAN_QUOTAS[PlanType.COACH],
        )
        db.add(solo_club)
        db.flush()
    user.club_id = solo_club.id
    db.flush()
    return solo_club.id


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_match(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_and_consume_quota(current_user, db)
    club_id = _get_solo_club_id(current_user, db)
    match = Match(
        id=str(uuid.uuid4()),
        club_id=club_id,
        created_by=current_user.id,
        opponent=payload.get("opponent"),
        date=datetime.fromisoformat(payload["date"]) if payload.get("date") else datetime.utcnow(),
        category=payload.get("category", "N3"),
        type=payload.get("type", MatchType.CHAMPIONNAT),
        competition=payload.get("competition"),
        location=payload.get("location"),
        is_home=payload.get("is_home", True),
        formation=payload.get("formation"),
        status=MatchStatus.PENDING,
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return {
        "id": match.id,
        "status": match.status,
        "club_id": match.club_id,
        "created_at": match.created_at.isoformat() + "Z",
    }


@router.get("/")
async def list_matches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    club_id = _get_solo_club_id(current_user, db)
    query = db.query(Match).filter(Match.club_id == club_id)

    # DS admin et superadmin voient tous les matchs du club
    # Coaches membres voient uniquement leurs propres matchs
    if not current_user.is_superadmin and not _is_club_admin(current_user):
        query = query.filter(Match.created_by == current_user.id)

    matches = query.order_by(Match.date.desc()).all()
    return matches


@router.get("/quota")
async def get_quota_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    billing_user = get_billing_user(current_user, db)

    if billing_user.stripe_subscription_id:
        is_trialing = (
            billing_user.trial_ends_at is not None
            and now < billing_user.trial_ends_at
        )
        if is_trialing:
            return {
                "plan": "TRIAL",
                "quota": TRIAL_MATCH_LIMIT,
                "used": 1 if current_user.trial_match_used else 0,
                "remaining": 0 if current_user.trial_match_used else 1,
                "resets_at": None,
            }
        quota = get_user_quota(billing_user)
        start, end = get_billing_period(billing_user)
        club_id = billing_user.club_id or _get_solo_club_id(current_user, db)
        trial_cutoff = billing_user.trial_ends_at or start
        used = db.query(Match).filter(
            Match.club_id == club_id,
            Match.created_at >= start,
            Match.created_at < end,
            Match.created_at >= trial_cutoff,
        ).count()
        plan_label = billing_user.plan.value if hasattr(billing_user.plan, 'value') else billing_user.plan
        return {
            "plan": plan_label,
            "quota": quota,
            "used": used,
            "remaining": max(0, quota - used),
            "resets_at": end.isoformat() + "Z",
        }

    if current_user.trial_ends_at and now < current_user.trial_ends_at:
        return {
            "plan": "TRIAL",
            "quota": TRIAL_MATCH_LIMIT,
            "used": 1 if current_user.trial_match_used else 0,
            "remaining": 0 if current_user.trial_match_used else 1,
            "resets_at": None,
        }

    return {
        "plan": "NO_SUBSCRIPTION",
        "quota": 0,
        "used": 0,
        "remaining": 0,
        "resets_at": None,
    }


@router.get("/{match_id}")
async def get_match(
    match_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    club_id = _get_solo_club_id(current_user, db)
    query = db.query(Match).filter(
        Match.id == match_id,
        Match.club_id == club_id,
    )
    # Coach membre : accès uniquement à ses propres matchs
    if not current_user.is_superadmin and not _is_club_admin(current_user):
        query = query.filter(Match.created_by == current_user.id)

    match = query.first()
    if not match:
        raise HTTPException(status_code=404, detail="Match introuvable")
    return match


@router.delete("/{match_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_match(
    match_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    club_id = _get_solo_club_id(current_user, db)
    query = db.query(Match).filter(
        Match.id == match_id,
        Match.club_id == club_id,
    )
    # Coach membre : suppression uniquement de ses propres matchs
    if not current_user.is_superadmin and not _is_club_admin(current_user):
        query = query.filter(Match.created_by == current_user.id)

    match = query.first()
    if not match:
        raise HTTPException(status_code=404, detail="Match introuvable")
    if match.status == MatchStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Impossible de supprimer un match en cours d'analyse."
        )
    db.delete(match)
    db.commit()
