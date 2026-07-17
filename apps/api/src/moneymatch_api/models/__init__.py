"""SQLAlchemy models. Importing this package registers every table on
`Base.metadata` (used by Alembic autogenerate and test schema creation)."""

from ..db.base import Base
from .admin_audit import AdminAudit
from .feature_flag import FeatureFlag
from .linked_account import LinkedAccount
from .notification import Notification
from .play import Match, MatchPlayer, QueueTicket
from .pools import SoloEntry, SoloPool
from .risk import RiskFlag
from .skill import MetricModel, RawPayload
from .social import Challenge, Friendship
from .tournaments import Tournament, TournamentEntry
from .user import User
from .wallet import LedgerEntry, Limit, PlatformLedgerEntry, Wallet

__all__ = [
    "Base",
    "AdminAudit",
    "FeatureFlag",
    "User",
    "Wallet",
    "LedgerEntry",
    "PlatformLedgerEntry",
    "Limit",
    "LinkedAccount",
    "MetricModel",
    "RawPayload",
    "QueueTicket",
    "Match",
    "MatchPlayer",
    "Notification",
    "SoloPool",
    "SoloEntry",
    "Tournament",
    "TournamentEntry",
    "RiskFlag",
    "Friendship",
    "Challenge",
]
