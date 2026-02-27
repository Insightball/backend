from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
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
TRIAL_DAY_LIMIT   = 7   # 7 jours max


# ─────────────────────────────────────────────
# HELPERS QUOTA
# ─────────────────────────────────────────────

def get_current_month_range():
    """Retourne le début et la fin du mois courant en UTC."""
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Fin du mois : premier jour du mois suivant
    if now.month == 12:
        end = start.replace(year=now.year + 1, month=1)
    else:
        end = start.replace(month=now.month + 1)
    return start, end


def check_and_consume_quota(user: User, db: Session) -> None:
    """
    Vérifie que l'utilisateur peut créer un nouveau match.
    Lève une HTTPException 429 si le quota est dépassé.
    Gère aussi le cas trial (1 match gratuit sans abonnement).
    """
    # Superadmin : pas de quota
    if user.is_superadmin:
        return

    # Utilisateur sans plan actif → on bloque (sécurité)
    if not user.plan:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="NO_ACTIVE_PLAN"
        )

    # ── Cas TRIAL ──────────────────────────────────────
    # Un user sans abonnement actif a droit à :
    #   - 1 match gratuit (trial_match_used)
    #   - ET une fenêtre de 7 jours (trial_ends_at)
    # La première condition atteinte bloque.
    if not user.stripe_subscription_id:
        now = datetime.utcnow()

        # Initialiser trial_ends_at à la première visite
        if user.trial_ends_at is None:
            user.trial_ends_at = now + timedelta(days=TRIAL_DAY_LIMIT)
            db.flush()

        # Condition 1 : match déjà consommé
        if user.trial_match_used:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="TRIAL_EXHAUSTED"
            )

        # Condition 2 : période expirée
        if now > user.trial_ends_at:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="TRIAL_EXPIRED"
            )

        # OK — consommer le match trial
        user.trial_match_used = True
        return

    # ── Cas CLUB : quota mensuel 12 ───────────────────
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

    # ── Cas COACH : quota mensuel ──────────────────────
    if user.plan == PlanType.COACH:
        quota = PLAN_QUOTAS[PlanType.COACH]
        start, end = get_current_month_range()

        # On compte les matchs créés ce mois-ci rattachés à ce user
        # Le match porte un club_id ; pour un COACH solo on filtre via created_by_user_id
        # ou via le club solo. On utilise ici une convention : le coach solo a un club
        # dont l'id == user.id (voir _get_or_create_solo_club).
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

    # Cherche un club solo existant
    solo_club = db.query(Club).filter(Club.id == user.id).first()
    if not solo_club:
        solo_club = Club(
            id=user.id,
            name=f"Coach — {user.name}",
            quota_matches=PLAN_QUOTAS[PlanType.COACH],
        )
        db.add(solo_club)
        db.flush()

    # Rattache le user à ce club pour les prochains appels
    user.club_id = solo_club.id
    db.flush()

    return solo_club.id


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_match(
    payload: dict,  # À remplacer par un Pydantic schema MatchCreate
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
    # Trial
    if not current_user.stripe_subscription_id:
        now = datetime.utcnow()
        trial_ends = current_user.trial_ends_at
        days_left = max(0, (trial_ends - now).days) if trial_ends else TRIAL_DAY_LIMIT
        return {
            "plan": "TRIAL",
            "quota": TRIAL_MATCH_LIMIT,
            "used": 1 if current_user.trial_match_used else 0,
            "remaining": 0 if current_user.trial_match_used else 1,
            "trial_ends_at": trial_ends.isoformat() + "Z" if trial_ends else None,
            "trial_days_left": days_left,
            "resets_at": None,
        }

    # CLUB
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

    # COACH
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

    # On ne supprime pas un match en cours de traitement
    if match.status == MatchStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Impossible de supprimer un match en cours d'analyse."
        )

    db.delete(match)
    db.commit()
