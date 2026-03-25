from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from app.models.ticket import TicketStatus


class TicketBase(BaseModel):
    subject: str
    description: Optional[str] = None
    priority: str = "medium"


class TicketCreate(TicketBase):
    pass


class TicketUpdate(BaseModel):
    """
    📚 Method: Intentionally narrow schema
    We do NOT inherit from TicketBase here. That would expose subject/description/priority
    on a PATCH — letting clients accidentally overwrite fields they didn't mean to touch.
    A PATCH schema should only contain the field(s) that endpoint controls.
    """
    status: Optional[TicketStatus] = None
    assigned_to_user_id: Optional[int] = None


class TicketResponse(TicketBase):
    id: int
    status: TicketStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    workspace_id: int
    created_by_user_id: int
    assigned_to_user_id: Optional[int] = None
    suggested_reply: Optional[str] = None
    suggested_reply_status: Optional[str] = None

    class Config:
        from_attributes = True

