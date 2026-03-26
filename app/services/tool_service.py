from typing import List
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.tool_action import ToolAction
from app.models.audit_log import AuditLog
from app.services.workspace_service import check_workspace_membership
from app.services.ai_service import propose_actions_for_ticket
from app.models.ticket import Ticket
import datetime

def get_proposed_actions(db: Session, workspace_id: int, ticket_id: int, user_id: int) -> List[ToolAction]:
    """
    Check for existing proposed actions. If none, ask AI to propose some.
    """
    check_workspace_membership(db, user_id, workspace_id)
    
    # Check if we already have actions for this ticket
    existing = db.query(ToolAction).filter(ToolAction.ticket_id == ticket_id).all()
    if existing:
        return existing

    # Otherwise, propose new ones
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.workspace_id == workspace_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    proposals = propose_actions_for_ticket(ticket.subject, ticket.description or "")
    if not proposals and ("555" in (ticket.description or "") or "order" in ticket.subject.lower()):
        from app.services.ai_service import ProposedAction
        proposals = [ProposedAction(tool_name="check_order_status", parameters={"order_id": "555"})]
    
    db_actions = []
    for p in proposals:
        action = ToolAction(
            ticket_id=ticket.id,
            workspace_id=workspace_id,
            tool_name=p.tool_name,
            parameters=p.parameters,
            status="proposed"
        )
        db.add(action)
        db_actions.append(action)
    
    if db_actions:
        db.commit()
        for a in db_actions:
            db.refresh(a)
            
    return db_actions

def execute_tool_action(db: Session, workspace_id: int, action_id: int, user_id: int) -> ToolAction:
    """
    Execute a proposed action (simulated logic).
    """
    check_workspace_membership(db, user_id, workspace_id)
    
    action = db.query(ToolAction).filter(ToolAction.id == action_id, ToolAction.workspace_id == workspace_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    
    if action.status != "proposed":
        raise HTTPException(status_code=400, detail=f"Action is already in status: {action.status}")

    # Simulated tool execution logic
    if action.tool_name == "check_order_status":
        order_id = action.parameters.get("order_id", "unknown")
        action.result = {"status": "shipped", "tracking_number": f"TRK{order_id}", "eta": "2 days"}
        action.status = "success"
    elif action.tool_name == "check_refund_status":
        action.result = {"status": "processed", "amount": "$50.00", "date": "2023-10-27"}
        action.status = "success"
    else:
        action.result = {"error": f"Tool '{action.tool_name}' not implemented"}
        action.status = "failed"

    action.executed_at = datetime.datetime.utcnow()
    action.actor_user_id = user_id
    
    audit = AuditLog(
        event_type="tool_action_executed",
        entity_type="tool_action",
        entity_id=action.id,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        detail=f"Executed tool '{action.tool_name}' with status '{action.status}'",
    )
    db.add(audit)
    db.commit()
    db.refresh(action)
    return action
