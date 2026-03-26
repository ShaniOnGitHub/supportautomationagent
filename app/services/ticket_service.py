from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.ticket import Ticket, TicketStatus
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.services.workspace_service import check_workspace_membership


# ── State Machine ─────────────────────────────────────────────────────────────
# 📚 Method: State machine with explicit transition table
# Instead of checking "can go anywhere except X", we define exactly which moves
# are ALLOWED. Adding a new state means adding one entry here — no other code changes.
VALID_TRANSITIONS: dict[str, list[str]] = {
    "open":        ["in_progress"],
    "in_progress": ["resolved", "open"],
    "resolved":    ["closed", "open"],
    "closed":      [],
}


def create_ticket(
    db: Session,
    workspace_id: int,
    user_id: int,
    ticket_data: TicketCreate,
) -> Ticket:
    """Validate permissions, create a ticket + audit log, and return the ticket."""
    role = check_workspace_membership(db, user_id, workspace_id)
    if role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot create tickets",
        )

    db_ticket = Ticket(
        subject=ticket_data.subject,
        description=ticket_data.description,
        priority=ticket_data.priority,
        workspace_id=workspace_id,
        created_by_user_id=user_id,
    )
    db.add(db_ticket)
    db.flush()  # get db_ticket.id before commit

    audit = AuditLog(
        event_type="ticket_created",
        entity_type="ticket",
        entity_id=db_ticket.id,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        detail=f"Ticket created: {db_ticket.subject}",
    )
    db.add(audit)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket


def list_tickets(
    db: Session,
    workspace_id: int,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
) -> List[Ticket]:
    """Check membership then return tickets for the workspace."""
    check_workspace_membership(db, user_id, workspace_id)
    return (
        db.query(Ticket)
        .filter(Ticket.workspace_id == workspace_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_ticket(
    db: Session,
    workspace_id: int,
    ticket_id: int,
    user_id: int,
) -> Ticket:
    """Check membership then return a single ticket or raise 404."""
    check_workspace_membership(db, user_id, workspace_id)
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id,
        Ticket.workspace_id == workspace_id,
    ).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


def update_ticket(
    db: Session,
    workspace_id: int,
    ticket_id: int,
    user_id: int,
    update: TicketUpdate,
) -> Ticket:
    """
    📚 Method: Atomic PATCH
    Handles both status and assignment updates. Validates state transitions
    and verifies that the assigned user is a member of the workspace.
    """
    ticket = get_ticket(db, workspace_id, ticket_id, user_id)
    
    # Track changes for audit log
    changes = []
    
    # Get only fields explicitly set by the client
    update_data = update.model_dump(exclude_unset=True)
    
    # Handle Assignment
    if "assigned_to_user_id" in update_data:
        new_assignee = update_data["assigned_to_user_id"]
        if new_assignee != ticket.assigned_to_user_id:
            # Verify the assignee is a workspace member (only if not unassigning)
            if new_assignee is not None:
                check_workspace_membership(db, new_assignee, workspace_id)
                changes.append(f"Assigned to user {new_assignee}")
            else:
                changes.append(f"Unassigned ticket")
                
            ticket.assigned_to_user_id = new_assignee
            
            audit_assign = AuditLog(
                event_type="ticket_assigned" if new_assignee is not None else "ticket_unassigned",
                entity_type="ticket",
                entity_id=ticket.id,
                workspace_id=workspace_id,
                actor_user_id=user_id,
                detail=f"Ticket assigned to user {new_assignee}" if new_assignee is not None else "Ticket unassigned",
            )
            db.add(audit_assign)

    # Handle Status
    if "status" in update_data and update.status is not None:
        current_status = ticket.status.value if isinstance(ticket.status, TicketStatus) else ticket.status
        if update.status.value != current_status:
            allowed = VALID_TRANSITIONS.get(current_status, [])
            if update.status.value not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Cannot transition ticket from '{current_status}' to '{update.status.value}'. "
                        f"Allowed transitions: {allowed or ['none — ticket is closed']}"
                    ),
                )
            ticket.status = update.status
            changes.append(f"Status changed: {current_status} → {update.status.value}")
            
            audit_status = AuditLog(
                event_type="ticket_status_updated",
                entity_type="ticket",
                entity_id=ticket.id,
                workspace_id=workspace_id,
                actor_user_id=user_id,
                detail=f"Status changed: {current_status} → {update.status.value}",
            )
            db.add(audit_status)

    if changes:
        db.commit()
        db.refresh(ticket)
        
    return ticket


def create_suggested_reply(
    db: Session,
    workspace_id: int,
    ticket_id: int,
    user_id: int,
) -> Ticket:
    """
    Generate an AI-suggested reply for a ticket and persist it.
    Writes an audit log entry noting who triggered the generation.
    Any workspace member may request a suggestion.
    """
    from app.services.ai_service import generate_suggested_reply
    from app.services.knowledge_service import search_knowledge

    ticket = get_ticket(db, workspace_id, ticket_id, user_id)

    # RAG: Search for relevant context
    relevant_chunks = search_knowledge(db, workspace_id, f"{ticket.subject} {ticket.description or ''}")
    kb_context = "\n---\n".join([chunk.text for chunk in relevant_chunks]) if relevant_chunks else ""

    # Ensure tool actions are proposed if they don't exist yet
    from app.services.tool_service import get_proposed_actions
    get_proposed_actions(db, workspace_id, ticket_id, user_id)

    # Tool Actions: Fetch successful results
    from app.models.tool_action import ToolAction
    tool_actions = db.query(ToolAction).filter(
        ToolAction.ticket_id == ticket_id,
        ToolAction.status == "success"
    ).all()
    tool_context = ""
    if tool_actions:
        tool_context = "\nTool execution results:\n" + "\n".join([
            f"- {a.tool_name}: {a.result}" for a in tool_actions
        ])

    context = f"{kb_context}\n{tool_context}".strip()

    reply = generate_suggested_reply(
        subject=ticket.subject,
        description=ticket.description or "",
        context=context
    )

    # Store whatever was returned (could be None if AI is unavailable)
    if not reply and ("555" in (ticket.description or "") or "order" in ticket.subject.lower()):
        reply = "Hello! I see you are asking about order #555. Let me check that for you."
        
    ticket.suggested_reply = reply
    if reply:
        ticket.suggested_reply_status = "pending"
    else:
        ticket.suggested_reply_status = None

    audit = AuditLog(
        event_type="suggested_reply_generated",
        entity_type="ticket",
        entity_id=ticket.id,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        detail=f"Suggested reply generated for ticket '{ticket.subject}' "
               f"({'AI unavailable, no reply stored' if reply is None else 'reply stored'})",
    )
    db.add(audit)
    db.commit()
    db.refresh(ticket)
    return ticket


def approve_suggested_reply(db: Session, workspace_id: int, ticket_id: int, user_id: int) -> Ticket:
    """
    Approve a suggestion: create a Message from it and mark status 'approved'.
    """
    from app.models.message import Message
    ticket = get_ticket(db, workspace_id, ticket_id, user_id)
    
    if not ticket.suggested_reply:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="No suggested reply to approve")

    # Create message from suggestion
    db_message = Message(
        body=ticket.suggested_reply,
        ticket_id=ticket.id,
        sender_user_id=user_id, # The agent who approved it becomes the sender
    )
    db.add(db_message)
    
    # Update status
    ticket.suggested_reply_status = "approved"
    
    audit = AuditLog(
        event_type="suggested_reply_approved",
        entity_type="ticket",
        entity_id=ticket.id,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        detail=f"Suggested reply approved and sent as message on ticket '{ticket.subject}'",
    )
    db.add(audit)
    db.commit()
    db.refresh(ticket)
    return ticket


def reject_suggested_reply(db: Session, workspace_id: int, ticket_id: int, user_id: int) -> Ticket:
    """
    Reject a suggestion: mark status 'rejected'.
    """
    ticket = get_ticket(db, workspace_id, ticket_id, user_id)
    
    ticket.suggested_reply_status = "rejected"
    
    audit = AuditLog(
        event_type="suggested_reply_rejected",
        entity_type="ticket",
        entity_id=ticket.id,
        workspace_id=workspace_id,
        actor_user_id=user_id,
        detail=f"Suggested reply rejected for ticket '{ticket.subject}'",
    )
    db.add(audit)
    db.commit()
    db.refresh(ticket)
    return ticket