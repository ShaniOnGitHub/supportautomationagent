from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from app.api import deps
from app.core.database import get_db
from app.models.user import User
from app.schemas.tool_action import ToolActionResponse
from app.services import tool_service

router = APIRouter()

@router.get("/", response_model=List[ToolActionResponse])
def list_proposed_actions(
    workspace_id: int,
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    List all tool actions proposed for this ticket.
    If none exist, the AI will analyze the ticket and propose new ones.
    """
    return tool_service.get_proposed_actions(db, workspace_id, ticket_id, current_user.id)

@router.post("/{action_id}/execute", response_model=ToolActionResponse)
def execute_tool_action(
    workspace_id: int,
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Execute a proposed tool action.
    """
    return tool_service.execute_tool_action(db, workspace_id, action_id, current_user.id)
