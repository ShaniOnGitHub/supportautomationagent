from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from app.api import deps
from app.core.database import get_db
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketUpdate, TicketResponse
from app.services import ticket_service

router = APIRouter()


@router.post("/", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(
    workspace_id: int,
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return ticket_service.create_ticket(db, workspace_id, current_user.id, ticket)


@router.get("/", response_model=List[TicketResponse])
def read_tickets(
    workspace_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return ticket_service.list_tickets(db, workspace_id, current_user.id, skip, limit)


@router.get("/{ticket_id}", response_model=TicketResponse)
def read_ticket(
    workspace_id: int,
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    return ticket_service.get_ticket(db, workspace_id, ticket_id, current_user.id)


@router.patch("/{ticket_id}", response_model=TicketResponse)
def update_ticket(
    workspace_id: int,
    ticket_id: int,
    update: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    📚 Method: Atomic PATCH
    Handles partial updates for status and assigned_to_user_id.
    """
    return ticket_service.update_ticket(
        db, workspace_id, ticket_id, current_user.id, update
    )


@router.post("/{ticket_id}/suggested-reply", response_model=TicketResponse)
def request_suggested_reply(
    workspace_id: int,
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Trigger AI generation of a suggested reply for the given ticket.
    Persists the result on the ticket and writes an audit log entry.
    Returns the updated ticket (with suggested_reply populated).
    """
    return ticket_service.create_suggested_reply(
        db, workspace_id, ticket_id, current_user.id
    )


@router.post("/{ticket_id}/approve-reply", response_model=TicketResponse)
def approve_suggested_reply(
    workspace_id: int,
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Approve the current suggested reply.
    This creates a message on the ticket and marks the suggestion as approved.
    """
    return ticket_service.approve_suggested_reply(
        db, workspace_id, ticket_id, current_user.id
    )


@router.post("/{ticket_id}/reject-reply", response_model=TicketResponse)
def reject_suggested_reply(
    workspace_id: int,
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Reject the current suggested reply.
    This marks the suggestion as rejected.
    """
    return ticket_service.reject_suggested_reply(
        db, workspace_id, ticket_id, current_user.id
    )
