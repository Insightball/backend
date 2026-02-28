from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import uuid

from app.database import get_db
from app.models import Match, MatchStatus, MatchType, User, PlanType, Club
from app.dependencies import get_current_user

router = APIRouter()

# ─────────────────────────────────────────────
# QUOTAS PAR PLAN
# ─────────────────────────────────────────────
PLAN_QUOTAS = {
    PlanType.COACH: 4,    # 4 matchs / mois
    PlanType.CLUB: 12,    # 12 matchs / mois
}

TRIAL_MATCH_LIMIT = 1   # 1 match gratuit


# ─────────────────────────────────────────────
# HELPERS QUOTA
# ─────────────────────────────────────────────

def get_billing_period(user: User):
    """
    Retourne (start, end) du cycle de facturation Stripe.
    Peuplé via webhooks — si absent, fallback sur mois calendaire.
    """
    if user.current_period_start and user.current_period_end:
        return user.current_period_start, user.current_period_end
    # Fallback mois calendaire (ne devrait pas arriver en prod)
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        end = start.replace(year=now.year + 1, month=1)
    else:
        end = start.replace(month=now.month + 1)
    return start, end


def check_and_consume_quota(user: User, db: Session) -> None:
    """
    Vérifie que l'utilisateur peut créer un nouveau match.
    Lève une HTTPException 402 si le quota est dépassé.

    Ordre de priorité STRICT :
    1. Superadmin → pas de quota
    2. Pas de plan → bloqué
    3. stripe_subscription_id présent ET trial_ends_at futur → 1 match trial
    4. stripe_subscription_id présent ET trial expiré → quota cycle Stripe
    5. Pas de stripe_subscription_id + trial_ends_at futur → 1 match trial
    6. Sinon → NO_SUBSCRIPTION
    """
    # 1. Superadmin
    if user.is_superadmin:
        return

    # 2. Pas de plan
    if not user.plan:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="NO_ACTIVE_PLAN"
        )

    # 3. ── Abonnement Stripe actif ────────────────────────────────────
    if user.stripe_subscription_id:
        now = datetime.utcnow()
        if user.trial_ends_at and now < user.trial_ends_at:
            # Encore en trial — 1 match offert
            if user.trial_match_used:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="TRIAL_EXHAUSTED"
                )
            # Match trial disponible → consommer atomiquement
            updated = db.query(User).filter(
                User.id == user.id,
                User.trial_match_used == False
            ).update({"trial_match_used": True})
            db.commit()
            if updated == 0:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="TRIAL_EXHAUSTED"
                )
            return

        # Trial expiré → quota cycle Stripe
        quota = PLAN_QUOTAS.get(user.plan, PLAN_QUOTAS[PlanType.COACH])
        start, end = get_billing_period(user)
        club_id = _get_solo_club_id(user, db)
        # Exclure le match trial : ne compter que les matchs créés après fin trial
        trial_cutoff = user.trial_ends_at or start
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
                    "plan": user.plan.value if hasattr(user.plan, 'value') else user.plan,
                    "quota": quota,
                    "used": count,
                    "resets_at": end.isoformat() + "Z",
                    "message": f"Quota atteint ({quota} matchs). Renouvellement le {end.strftime('%d/%m/%Y')}."
                }
            )
        return

    # 4. ── Cas TRIAL : pas de stripe_subscription_id ─────────────────
    now = datetime.utcnow()
    if user.trial_ends_at and now < user.trial_ends_at:
        updated = db.query(User).filter(
            User.id == user.id,
            User.trial_match_used == False
        ).update({"trial_match_used": True})
        db.commit()
        if updated == 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="TRIAL_EXHAUSTED"
            )
        return

    # 5. Aucun sub, pas de trial actif
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail="NO_SUBSCRIPTION"
    )


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


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

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
    matches = (
        db.query(Match)
        .filter(Match.club_id == club_id)
        .order_by(Match.date.desc())
        .all()
    )
    return matches


@router.get("/quota")
async def get_quota_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Source de vérité pour le quota affiché dans le dashboard.
    Utilise le cycle de facturation Stripe (current_period_start/end),
    pas le mois calendaire.
    """
    now = datetime.utcnow()

    # ── Abonnement Stripe présent ──────────────────────────────────────
    if current_user.stripe_subscription_id:
        is_trialing = (
            current_user.trial_ends_at is not None
            and now < current_user.trial_ends_at
        )
        if is_trialing:
            return {
                "plan": "TRIAL",
                "quota": TRIAL_MATCH_LIMIT,
                "used": 1 if current_user.trial_match_used else 0,
                "remaining": 0 if current_user.trial_match_used else 1,
                "resets_at": None,
            }

        # Quota cycle Stripe
        quota = PLAN_QUOTAS.get(current_user.plan, PLAN_QUOTAS[PlanType.COACH])
        start, end = get_billing_period(current_user)
        club_id = _get_solo_club_id(current_user, db)
        trial_cutoff = current_user.trial_ends_at or start
        used = db.query(Match).filter(
            Match.club_id == club_id,
            Match.created_at >= start,
            Match.created_at < end,
            Match.created_at >= trial_cutoff,
        ).count()
        plan_label = current_user.plan.value if hasattr(current_user.plan, 'value') else current_user.plan
        return {
            "plan": plan_label,
            "quota": quota,
            "used": used,
            "remaining": max(0, quota - used),
            "resets_at": end.isoformat() + "Z",
        }

    # ── Pas de stripe_subscription_id ─────────────────────────────────
    if current_user.trial_ends_at and now < current_user.trial_ends_at:
        return {
            "plan": "TRIAL",
            "quota": TRIAL_MATCH_LIMIT,
            "used": 1 if current_user.trial_match_used else 0,
            "remaining": 0 if current_user.trial_match_used else 1,
            "resets_at": None,
        }

    # Aucun sub, aucun trial actif
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
    match = db.query(Match).filter(
        Match.id == match_id,
        Match.club_id == club_id,
    ).first()
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
    match = db.query(Match).filter(
        Match.id == match_id,
        Match.club_id == club_id,
    ).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match introuvable")
    if match.status == MatchStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Impossible de supprimer un match en cours d'analyse."
        )
    db.delete(match)
    db.commit()
