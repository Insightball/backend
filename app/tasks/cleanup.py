"""
app/tasks/cleanup.py
Purge définitive des comptes supprimés après 30 jours
À appeler via un cron job Render (scheduled job) ou APScheduler
"""
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, Match
from app.models.club_member import ClubMember


def purge_deleted_accounts():
    """Supprime définitivement les comptes dont deleted_at > 30 jours"""
    db: Session = SessionLocal()
    try:
        expired_users = db.query(User).filter(
            User.deleted_at != None,
            User.recovery_token_expires < datetime.utcnow()
        ).all()

        count = 0
        for user in expired_users:
            print(f"🗑️  Purge définitive : {user.email} (supprimé le {user.deleted_at})")

            # Supprimer les membres club associés
            db.query(ClubMember).filter(
                (ClubMember.user_id == user.id) | (ClubMember.invited_by == user.id)
            ).delete()

            # Supprimer les matchs
            db.query(Match).filter(Match.user_id == user.id).delete()

            db.delete(user)
            count += 1

        db.commit()
        print(f"✅ Purge terminée : {count} compte(s) supprimé(s) définitivement")
        return count

    except Exception as e:
        db.rollback()
        print(f"❌ Erreur purge : {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    purge_deleted_accounts()
