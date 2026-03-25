import pytest
from unittest.mock import patch, MagicMock
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.knowledge_base import Document, DocumentChunk

# ── Helpers ──────────────────────────────────────────────────────────────────

def register_and_login(client, email):
    client.post("/api/v1/auth/register", json={"email": email, "password": "pass", "full_name": "Test"})
    resp = client.post("/api/v1/auth/login", data={"username": email, "password": "pass"})
    return resp.json()["access_token"]

def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}

def setup_workspace(db, email, client):
    token = register_and_login(client, email)
    user = db.query(User).filter(User.email == email).first()
    ws = Workspace(name="RAG WS", owner_id=user.id)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin"))
    db.commit()
    return token, user, ws

# ── Tests ─────────────────────────────────────────────────────────────────────

@patch("app.services.knowledge_service.generate_embeddings")
def test_ingest_knowledge(mock_embed, client, db_session):
    """Verify that document ingestion chunks text and stores embeddings."""
    mock_embed.return_value = [0.1] * 768
    token, user, ws = setup_workspace(db_session, "ingest@test.com", client)

    payload = {
        "filename": "policy.txt",
        "content": "Refunds are allowed within 14 days of purchase. Only for unused items."
    }
    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/knowledge/",
        json=payload,
        headers=auth_headers(token)
    )
    assert resp.status_code == 201
    assert resp.json()["filename"] == "policy.txt"

    # Check DB
    db_session.expire_all()
    doc = db_session.query(Document).filter(Document.workspace_id == ws.id).first()
    assert doc is not None
    chunk = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).first()
    assert chunk is not None
    assert "Refunds" in chunk.text

@patch("app.services.knowledge_service.generate_embeddings")
@patch("app.services.ai_service.generate_suggested_reply")
def test_rag_suggested_reply(mock_generate, mock_embed, client, db_session):
    """
    End-to-end RAG test:
    1. Ingest a specific policy.
    2. Create a relevant ticket.
    3. Trigger a suggested reply.
    4. Verify the suggestion (mocked) would have received the right context.
    """
    # 1. Setup
    token, user, ws = setup_workspace(db_session, "rag@test.com", client)
    
    # Mock embeddings to always return the same vector for simplicity
    mock_embed.return_value = [0.5] * 768
    
    # Ingest policy
    client.post(
        f"/api/v1/workspaces/{ws.id}/knowledge/",
        json={"filename": "refund.txt", "content": "THE REFUND POLICY IS EXACTLY 14 DAYS."},
        headers=auth_headers(token)
    )

    # 2. Create ticket
    ticket_resp = client.post(
        f"/api/v1/workspaces/{ws.id}/tickets/",
        json={"subject": "Refund request", "description": "Can I get a refund for my order?"},
        headers=auth_headers(token)
    )
    ticket_id = ticket_resp.json()["id"]

    # 3. Trigger suggested reply
    # We mock the suggested reply function directly to return a string
    mock_generate.return_value = "Based on our policy, you have 14 days. [Source: Company Policy]"

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/tickets/{ticket_id}/suggested-reply",
        headers=auth_headers(token)
    )

    # 4. Assertions
    assert resp.status_code == 200
    data = resp.json()
    assert "14 days" in data["suggested_reply"]
    
    # Verify that mock_generate was called (this proves the pipeline executed)
    assert mock_generate.called
    # Check that context was passed as a keyword argument
    kwargs_sent = mock_generate.call_args[1]
    assert "THE REFUND POLICY IS EXACTLY 14 DAYS" in kwargs_sent["context"]
