"""
Tests for the external inbound webhook route for ticket ingestion.
"""
from app.models.user import User
from app.models.workspace import Workspace
from app.models.ticket import Ticket
from app.models.message import Message


import uuid

def setup_workspace_with_secret(db_session):
    unique_id = uuid.uuid4().hex[:8]
    ws = Workspace(
        name=f"Webhook WS {unique_id}", 
        owner_id=1, 
        webhook_secret=f"super-secret-{unique_id}"
    )
    # create dummy owner
    owner = User(email=f"owner_{unique_id}@ws.com", hashed_password="pw", full_name="O")
    db_session.add(owner)
    db_session.flush()
    ws.owner_id = owner.id
    db_session.add(ws)
    db_session.commit()
    db_session.refresh(ws)
    return ws, ws.webhook_secret


def test_ingest_ticket_new_user(client, db_session):
    """
    📚 Method: Auto-provisioning Guest integration
    A completely unknown email creates a new guest user, a ticket, and a message.
    """
    ws, secret = setup_workspace_with_secret(db_session)
    
    payload = {
        "sender_email": "new.customer@external.com",
        "subject": "Help with billing",
        "body": "I was double charged.",
    }
    
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/ingest",
        json=payload,
        headers={"X-Webhook-Secret": secret}
    )
    
    assert resp.status_code == 201
    data = resp.json()
    assert data["ticket"]["subject"] == "Help with billing"
    assert data["ticket"]["workspace_id"] == ws.id
    
    # 1. Check user was auto-provisioned
    new_user = db_session.query(User).filter(User.email == "new.customer@external.com").first()
    assert new_user is not None
    assert new_user.id == data["ticket"]["created_by_user_id"]
    assert new_user.hashed_password == "!guest"
    
    # 2. Check message was created
    msg = db_session.query(Message).filter(Message.ticket_id == data["ticket"]["id"]).first()
    assert msg is not None
    assert msg.body == "I was double charged."


def test_ingest_ticket_existing_user(client, db_session):
    """
    📚 Method: Existing user mapping
    If the email already exists in our system, the ticket is just mapped to them.
    No new user is created.
    """
    ws, secret = setup_workspace_with_secret(db_session)
    
    # Pre-create an existing user
    unique_ext = str(uuid.uuid4().hex[:6])
    existing_user = User(email=f"existing_{unique_ext}@customer.com", hashed_password="realpassword", full_name="Real")
    db_session.add(existing_user)
    db_session.commit()
    
    payload = {
        "sender_email": existing_user.email,
        "subject": "Another ticket",
        "body": "Hello again.",
    }
    
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/ingest",
        json=payload,
        headers={"X-Webhook-Secret": secret}
    )
    
    assert resp.status_code == 201
    assert resp.json()["ticket"]["created_by_user_id"] == existing_user.id
    
    # Ensure no duplicate user was created
    user_count = db_session.query(User).filter(User.email == existing_user.email).count()
    assert user_count == 1


def test_ingest_ticket_invalid_secret(client, db_session):
    """
    📚 Method: Webhook Auth boundary
    Sending a request with a missing or wrong secret must fail with 401.
    """
    ws, secret = setup_workspace_with_secret(db_session)
    
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/ingest",
        json={"sender_email": "a@b.com", "subject": "S", "body": "B"},
        headers={"X-Webhook-Secret": "WRONG"}
    )
    assert resp.status_code == 401
    
    # Missing header entirely
    resp_missing = client.post(
        f"/api/v1/workspaces/{ws.id}/ingest",
        json={"sender_email": "a@b.com", "subject": "S", "body": "B"},
    )
    assert resp_missing.status_code == 422 # FastAPI required header validation gives 422
