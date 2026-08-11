"""SQLAlchemy models. Importing this package registers every table on
`Base.metadata` (used by Alembic autogenerate and test schema creation)."""

from ..db.base import Base
from .admin_audit import AdminAudit
from .chat import Conversation, ConversationMember, Message
from .cs2 import Cs2Match
from .demo_simulation import SimulatedMatch
from .dispute import Dispute
from .feature_flag import FeatureFlag
from .linked_account import LinkedAccount
from .live import LiveSnapshot
from .notification import Notification
from .play import Match, MatchPlayer, QueueTicket
from .pools import SoloEntry, SoloPool
from .push import PushSubscription
from .risk import RiskFlag
from .skill import MetricModel, RawPayload
from .social import Challenge, Friendship
from .tournaments import Tournament, TournamentEntry
from .user import User
from .wallet import LedgerEntry, Limit, PlatformLedgerEntry, Wallet

__all__ = [
    "Base",
    "AdminAudit",
    "Conversation",
    "ConversationMember",
    "Dispute",
    "Message",
    "FeatureFlag",
    "User",
    "Wallet",
    "LedgerEntry",
    "PlatformLedgerEntry",
    "Limit",
    "LinkedAccount",
    "LiveSnapshot",
    "MetricModel",
    "RawPayload",
    "QueueTicket",
    "Match",
    "MatchPlayer",
    "Notification",
    "SoloPool",
    "SoloEntry",
    "PushSubscription",
    "Tournament",
    "TournamentEntry",
    "RiskFlag",
    "Friendship",
    "Challenge",
    "SimulatedMatch",
    "Cs2Match",
]
