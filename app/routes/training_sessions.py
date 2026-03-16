"""Routes — Séances d'entraînement et présences (Module 1)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from pydantic import BaseModel
from datetime import date, timedelta
from typing import Optional, List
import uuid

from app.database import get_db
from app.dependencies import get_current_user
from app.models.training_session import TrainingSession, Attendance
from app.models.player import Player
from app.models.club_member import ClubMember, InviteStatus

router = APIRouter()


# ── Helper : catégorie gérée (même pattern que matches/players) ──

def _get_managed_category(db: Session, user) -> Optional[str]:
    """Retourne la catégorie du coach membre club, ou None si DS/coach solo."""
    if not user.club_id or user.stripe_subscription_id:
        return None
    member = db.query(ClubMember).filter(
        ClubMember.club_id == user.club_id,
        ClubMember.user_id == user.id,
        ClubMember.status == InviteStatus.ACCEPTED.value
    ).first()
    return member.category if member else None


# ── Schemas ──────────────────────────────────

class SessionCreate(BaseModel):
    category: Optional[str] = "Seniors"
    date: date
    session_type: str = "entrainement"
    start_time: str = "19:00"
    duration_minutes: int = 90
    notes: Optional[str] = None
    theme: Optional[str] = None


class AttendanceEntry(BaseModel):
    player_id: str
    status: str = "present"
    absence_reason: Optional[str] = None


class AttendanceBatch(BaseModel):
    entries: List[AttendanceEntry]


# ══════════════════════════════════════════════
# SÉANCES
# ══════════════════════════════════════════════

@router.post("")
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Créer une séance d'entraînement."""
    managed = _get_managed_category(db, user)
    category = managed or payload.category

    session = TrainingSession(
        id=f"ts-{uuid.uuid4()}",
        user_id=user.id,
        club_id=getattr(user, "club_id", None),
        category=category,
        date=payload.date,
        session_type=payload.session_type,
        start_time=payload.start_time,
        duration_minutes=payload.duration_minutes,
        notes=payload.notes,
        theme=payload.theme,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_to_dict(db, session)


@router.get("")
def list_sessions(
    month: Optional[int] = None,
    year: Optional[int] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Lister les séances — filtrables par mois et catégorie."""
    managed = _get_managed_category(db, user)

    q = db.query(TrainingSession)

    # Filtre par user ou club
    if getattr(user, "club_id", None):
        q = q.filter(TrainingSession.club_id == user.club_id)
    else:
        q = q.filter(TrainingSession.user_id == user.id)

    # Filtre catégorie
    if managed:
        q = q.filter(TrainingSession.category == managed)
    elif category:
        q = q.filter(TrainingSession.category == category)

    # Filtre mois
    if month and year:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        q = q.filter(TrainingSession.date >= start, TrainingSession.date < end)

    sessions = q.order_by(TrainingSession.date.desc()).all()
    return [_session_to_dict(db, s) for s in sessions]


@router.get("/{session_id}")
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Récupérer une séance par ID."""
    session = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Séance introuvable")
    return _session_to_dict(db, session)


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Supprimer une séance et ses présences."""
    session = db.query(TrainingSession).filter(
        TrainingSession.id == session_id,
        TrainingSession.user_id == user.id
    ).first()
    if not session:
        raise HTTPException(404, "Séance introuvable")
    db.delete(session)
    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════
# PRÉSENCES (POINTAGE)
# ══════════════════════════════════════════════

@router.put("/{session_id}/attendance")
def update_attendance(
    session_id: str,
    payload: AttendanceBatch,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """
    Pointage batch — créer ou mettre à jour les présences d'une séance.
    Upsert : si le joueur a déjà une entrée, on la met à jour.
    """
    session = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Séance introuvable")

    results = []
    for entry in payload.entries:
        # Upsert
        existing = db.query(Attendance).filter(
            Attendance.session_id == session_id,
            Attendance.player_id == entry.player_id
        ).first()

        reason = entry.absence_reason if entry.status != "present" else None

        if existing:
            existing.status = entry.status
            existing.absence_reason = reason
            db.flush()
            att = existing
        else:
            att = Attendance(
                id=f"att-{uuid.uuid4()}",
                session_id=session_id,
                player_id=entry.player_id,
                status=entry.status,
                absence_reason=reason,
            )
            db.add(att)
            db.flush()

        # Enrichir avec le nom du joueur
        player = db.query(Player).filter(Player.id == entry.player_id).first()
        results.append({
            "id": att.id,
            "player_id": att.player_id,
            "player_name": player.name if player else None,
            "player_number": player.number if player else None,
            "status": att.status,
            "absence_reason": att.absence_reason,
        })

    db.commit()
    return results


@router.get("/{session_id}/attendance")
def get_attendance(
    session_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Récupérer les présences d'une séance."""
    attendances = db.query(Attendance).filter(Attendance.session_id == session_id).all()

    results = []
    for att in attendances:
        player = db.query(Player).filter(Player.id == att.player_id).first()
        results.append({
            "id": att.id,
            "player_id": att.player_id,
            "player_name": player.name if player else None,
            "player_number": player.number if player else None,
            "status": att.status,
            "absence_reason": att.absence_reason,
        })
    return results


# ══════════════════════════════════════════════
# STATS JOUEUR
# ══════════════════════════════════════════════

@router.get("/player/{player_id}/stats")
def get_player_attendance_stats(
    player_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Stats de présence d'un joueur — taux, série, absences non justifiées."""
    attendances = db.query(Attendance).join(TrainingSession).filter(
        Attendance.player_id == player_id,
        TrainingSession.user_id == user.id
    ).order_by(TrainingSession.date.desc()).all()

    total = len(attendances)
    present = sum(1 for a in attendances if a.status == "present")
    absent = sum(1 for a in attendances if a.status == "absent")
    excused = sum(1 for a in attendances if a.status == "excused")
    injured = sum(1 for a in attendances if a.status == "injured")
    non_just = sum(1 for a in attendances
                   if a.status == "absent"
                   and a.absence_reason == "non_justifiee")

    # Série en cours (séances consécutives présent, du plus récent)
    streak = 0
    for a in attendances:
        if a.status == "present":
            streak += 1
        else:
            break

    return {
        "player_id": player_id,
        "total_sessions": total,
        "present": present,
        "absent": absent,
        "excused": excused,
        "injured": injured,
        "attendance_rate": round(present / total, 2) if total > 0 else 0.0,
        "current_streak": streak,
        "absences_non_justifiees": non_just,
    }


# ══════════════════════════════════════════════
# VUE CALENDRIER
# ══════════════════════════════════════════════

@router.get("/calendar")
def get_calendar(
    month: int,
    year: int,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Vue calendrier mensuel — jours avec/sans séance."""
    managed = _get_managed_category(db, user)

    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    q = db.query(TrainingSession).filter(
        TrainingSession.date >= start,
        TrainingSession.date < end,
    )
    if getattr(user, "club_id", None):
        q = q.filter(TrainingSession.club_id == user.club_id)
    else:
        q = q.filter(TrainingSession.user_id == user.id)

    cat = managed or category
    if cat:
        q = q.filter(TrainingSession.category == cat)

    sessions = {s.date: s for s in q.all()}

    # Générer tous les jours du mois
    days = []
    current = start
    while current < end:
        s = sessions.get(current)
        if s:
            att_total = db.query(func.count(Attendance.id)).filter(
                Attendance.session_id == s.id
            ).scalar() or 0
            att_present = db.query(func.count(Attendance.id)).filter(
                Attendance.session_id == s.id,
                Attendance.status == "present"
            ).scalar() or 0

            days.append({
                "date": str(current),
                "has_session": True,
                "session_id": s.id,
                "session_type": s.session_type,
                "present_count": att_present,
                "total_count": att_total,
            })
        else:
            days.append({"date": str(current), "has_session": False})
        current += timedelta(days=1)

    return days


# ══════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════

def _session_to_dict(db: Session, session: TrainingSession) -> dict:
    """Convertir une séance en dict avec compteurs de présence."""
    att_total = db.query(func.count(Attendance.id)).filter(
        Attendance.session_id == session.id
    ).scalar() or 0
    att_present = db.query(func.count(Attendance.id)).filter(
        Attendance.session_id == session.id,
        Attendance.status == "present"
    ).scalar() or 0

    return {
        "id": session.id,
        "user_id": session.user_id,
        "club_id": session.club_id,
        "category": session.category,
        "date": str(session.date),
        "session_type": session.session_type,
        "start_time": session.start_time,
        "duration_minutes": session.duration_minutes,
        "notes": session.notes,
        "theme": session.theme,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "player_count": att_total,
        "present_count": att_present,
    }
