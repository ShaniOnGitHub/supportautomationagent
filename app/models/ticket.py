import datetime
import enum

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum

from app.core.database import Base


class TicketStatus(str, enum.Enum):
    """
    📚 Method: SQLAlchemy Enum
    Inheriting from both str and enum.Enum makes each member a real string,
    so JSON serialisation (FastAPI/Pydantic) works without extra config.
    SQLAlchemy maps this to a DB-level ENUM (Postgres) or CHECK constraint (SQLite).
    """
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TicketStatus), nullable=False, default=TicketStatus.open)
    priority = Column(String(50), nullable=False, default="medium")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    suggested_reply = Column(Text, nullable=True)
    # Statuses: pending, approved, rejected
    suggested_reply_status = Column(String, nullable=True)
