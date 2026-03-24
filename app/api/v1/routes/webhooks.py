from fastapi import APIRouter, Depends, HTTPException, status, Header, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.workspace import Workspace
from app.models.user import User
from app.models.ticket import Ticket
from app.models.audit_log import AuditLog
from app.models.message import Message
from app.schemas.webhook import TicketIngestRequest, TicketIngestResponse
from app.services.job_service import enqueue_job, execute_job

router = APIRouter()

# AI triage function
def ai_triage(db: Session, payload: dict):
    from app.services.ai_service import classify_ticket_with_gemini
    ticket_id = payload.get("ticket_id")
    if not ticket_id:
        return

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        return

    result = classify_ticket_with_gemini(ticket.subject, ticket.description or "")
    if result:
        # 1. Update Priority if AI classification was successful
        ticket.priority = result.priority.lower()

        # 2. Add an AuditLog explaining the AI logic
        audit = AuditLog(
            event_type="ai_triage_complete",
            entity_type="ticket",
            entity_id=ticket.id,
            workspace_id=ticket.workspace_id,
            actor_user_id=ticket.created_by_user_id,
            detail=f"[AI Classification] Sentiment: {result.sentiment}. Summary: {result.summary}",
        )
        db.add(audit)
        db.commit()

@router.post("/{workspace_id}/ingest", response_model=TicketIngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_ticket(
    workspace_id: int,
    payload: TicketIngestRequest,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(..., description="The secret token for the workspace webhook"),
    db: Session = Depends(get_db),
):
    """
    Ingest a new ticket from an external source (e.g., email or Zapier webhook).
    Authenticates via the X-Webhook-Secret header.
    Auto-provisions a guest user if the sender_email is new.
    """
    # 1. Authenticate via Webhook Secret
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    if not workspace.webhook_secret or workspace.webhook_secret != x_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # 2. Auto-provision or find the user
    user = db.query(User).filter(User.email == payload.sender_email).first()
    if not user:
        # Create a "Guest" user. We use a dummy password that can't be logged into.
        user = User(
            email=payload.sender_email,
            hashed_password="!guest",
            is_active=True,
            full_name=payload.sender_email.split("@")[0]
        )
        db.add(user)
        db.flush() # Get user ID
        
        # We DO NOT automatically add them to the WorkspaceMember table,
        # because they are an external customer, not an internal agent/viewer.

    # 3. Create the Ticket
    ticket = Ticket(
        subject=payload.subject,
        description=payload.body, # Store full body in description for the ticket view
        priority=payload.priority,
        workspace_id=workspace_id,
        created_by_user_id=user.id,
    )
    db.add(ticket)
    db.flush()

    # 4. Create the initial Message (acting as the email thread start)
    message = Message(
        body=payload.body,
        ticket_id=ticket.id,
        sender_user_id=user.id
    )
    db.add(message)

    # 5. Audit Log
    audit = AuditLog(
        event_type="ticket_ingested",
        entity_type="ticket",
        entity_id=ticket.id,
        workspace_id=workspace_id,
        actor_user_id=user.id,
        detail=f"Ticket '{ticket.subject}' ingested via webhook from {payload.sender_email}",
    )
    db.add(audit)
    
    # 6. Enqueue Background AI Triage
    job = enqueue_job(
        db=db, 
        name="ai_triage", 
        payload={"ticket_id": ticket.id}, 
        workspace_id=workspace_id, 
        actor_user_id=user.id
    )
    db.commit()
    db.refresh(ticket)
    
    # Pass a dynamically generated session factory bound to the current engine.
    # This ensures background tasks use the same database connection as the request
    # (crucial for overridden test environments using in-memory SQLite).
    from sqlalchemy.orm import sessionmaker
    engine_bind = db.get_bind()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine_bind)
    
    background_tasks.add_task(execute_job, factory, job.id, ai_triage)
    
    return TicketIngestResponse(ticket=ticket, job_id=job.id)
