from app.models.user import User, PlanType, UserRole
from app.models.club import Club
from app.models.match import Match, MatchStatus, MatchType
from app.models.player import Player
from app.models.notification import Notification, NotificationType  # notification.py — avec FK user_id
from app.models.club_member import ClubMember, MemberRole, InviteStatus
from app.models.club_invite import ClubInvite, ClubInviteStatus
from app.models.game_plan import GamePlan
from app.models.training_session import TrainingSession, Attendance
from app.models.match_sheet import MatchSheet, MatchSheetPlayer, MatchSheetSub
from app.models.player_profile import PlayerEvaluation, PlayerNote, PlayerObjective

__all__ = [
    "User",
    "Club",
    "Match",
    "Player",
    "Notification",
    "ClubMember",
    "ClubInvite",
    "PlanType",
    "UserRole",
    "MemberRole",
    "InviteStatus",
    "ClubInviteStatus",
    "GamePlan",
    "MatchStatus",
    "MatchType",
    "NotificationType",
    # Module 1 — Présences
    "TrainingSession",
    "Attendance",
    # Module 2 — Feuille de match
    "MatchSheet",
    "MatchSheetPlayer",
    "MatchSheetSub",
    # Module 3 — Profil joueur enrichi
    "PlayerEvaluation",
    "PlayerNote",
    "PlayerObjective",
]
