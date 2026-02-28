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

def get_current_month_range():
    """Retourne le début et la fin du mois courant en UTC."""
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
    Lève une HTTPException 402/429 si le quota est dépassé.
    Gère aussi le cas trial (1 match gratuit sans abonnement).
    """
    # Superadmin : pas de quota
    if user.is_superadmin:
        return

    # Utilisateur sans plan actif → on bloque
    if not user.plan:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="NO_ACTIVE_PLAN"
        )

    # ── Pas de CB → bloqué ────────────────────────────────
    if not user.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="NO_SUBSCRIPTION"
        )

    # ── Cas TRIAL ─────────────────────────────────────────
    # trial_ends_at > now → user en période d'essai → 1 match max
    # FIX : UPDATE atomique pour éviter la race condition
    # (deux requêtes simultanées ne peuvent plus toutes les deux passer)
    now = datetime.utcnow()
    if user.trial_ends_at and now < user.trial_ends_at:
        updated = db.query(User).filter(
            User.id == user.id,
            User.trial_match_used == False
        ).update({"trial_match_used": True})
        db.commit()
        if updated == 0:
            # Le flag était déjà True → trial déjà consommé
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="TRIAL_EXHAUSTED"
            )
        return

    # ── Cas CLUB : quota mensuel 12 ───────────────────────
    if user.plan == PlanType.CLUB:
        quota = PLAN_QUOTAS[PlanType.CLUB]
        start, end = get_current_month_range()
        club_id = _get_solo_club_id(user, db)
        count = db.query(Match).filter(
            Match.club_id == club_id,
            Match.created_at >= start,
            Match.created_at < end,
        ).count()
        if count >= quota:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "plan": "CLUB",
                    "quota": quota,
                    "used": count,
                    "resets_at": end.isoformat() + "Z",
                    "message": f"Quota atteint ({quota} matchs/mois). Renouvellement le 1er du mois."
                }
            )
        return

    # ── Cas COACH : quota mensuel 4 ───────────────────────
    if user.plan == PlanType.COACH:
        quota = PLAN_QUOTAS[PlanType.COACH]
        start, end = get_current_month_range()
        count = db.query(Match).filter(
            Match.club_id == _get_solo_club_id(user, db),
            Match.created_at >= start,
            Match.created_at < end,
        ).count()
        if count >= quota:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "plan": "COACH",
                    "quota": quota,
                    "used": count,
                    "resets_at": end.isoformat() + "Z",
                    "message": f"Quota atteint ({quota} matchs/mois). Ton quota se renouvelle le 1er du mois prochain."
                }
            )
        return


def _get_solo_club_id(user: User, db: Session) -> str:
    """
    Un coach sans club rattaché obtient (ou crée) un club solo.
    Convention : club.id == user.id pour rester simple.
    """
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
    """
    Crée un nouveau match.
    - Vérifie le quota avant toute création.
    - Gère le club solo pour les coachs sans club.
    """
    # ── 1. Vérif quota (lève 429/402 si dépassé) ───────
    check_and_consume_quota(current_user, db)

    # ── 2. Résolution du club_id ────────────────────────
    club_id = _get_solo_club_id(current_user, db)

    # ── 3. Création du match ────────────────────────────
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
    """Liste les matchs du club/coach courant."""
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
    Retourne l'état du quota pour le mois courant.
    Utile pour afficher la jauge dans le dashboard.
    """
    if not current_user.stripe_subscription_id:
        return {
            "plan": "TRIAL",
            "quota": TRIAL_MATCH_LIMIT,
            "used": 1 if current_user.trial_match_used else 0,
            "remaining": 0 if current_user.trial_match_used else 1,
            "resets_at": None,
        }

    if current_user.plan == PlanType.CLUB:
        quota = PLAN_QUOTAS[PlanType.CLUB]
        start, end = get_current_month_range()
        club_id = _get_solo_club_id(current_user, db)
        used = db.query(Match).filter(
            Match.club_id == club_id,
            Match.created_at >= start,
            Match.created_at < end,
        ).count()
        return {"plan": "CLUB", "quota": quota, "used": used, "remaining": max(0, quota - used), "resets_at": end.isoformat() + "Z"}

    quota = PLAN_QUOTAS[PlanType.COACH]
    start, end = get_current_month_range()
    club_id = _get_solo_club_id(current_user, db)
    used = db.query(Match).filter(
        Match.club_id == club_id,
        Match.created_at >= start,
        Match.created_at < end,
    ).count()

    return {
        "plan": "COACH",
        "quota": quota,
        "used": used,
        "remaining": max(0, quota - used),
        "resets_at": end.isoformat() + "Z",
    }


@router.get("/{match_id}")
async def get_match(
    match_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Récupère un match — vérifie que l'user y a accès."""
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
    """Supprime un match. Ne rembourse pas le quota (choix volontaire)."""
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
