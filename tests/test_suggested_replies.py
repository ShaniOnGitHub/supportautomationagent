"""
Tests for the Suggested Reply feature.
Covers: success path (with mocked Gemini), workspace isolation (forbidden), and 404.
"""
import pytest
from unittest.mock import patch
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.audit_log import AuditLog
from app.models.ticket import Ticket


# ── Helpers ──────────────────────────────────────────────────────────────────

def register_and_login(client, email, password="pass123", full_name="Test"):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    return resp.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def setup_workspace_with_admin(db, email, client):
    """Register user, create workspace, add as admin, return (token, user, workspace)."""
    token = register_and_login(client, email)
    user = db.query(User).filter(User.email == email).first()
    ws = Workspace(name=f"WS for {email}", owner_id=user.id)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin"))
    db.commit()
    return token, user, ws


def create_ticket(client, ws_id, token, subject="Late order", description="My order is late."):
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/tickets/",
        json={"subject": subject, "description": description, "priority": "medium"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    return resp.json()


# ── Tests ─────────────────────────────────────────────────────────────────────

@patch("app.services.ai_service.generate_suggested_reply")
def test_generate_suggested_reply_success(mock_generate, client, db_session):
    """
    Happy path: endpoint calls AI, stores reply on ticket, writes audit log.
    Gemini is mocked so the test is fully offline.
    """
    mock_generate.return_value = (
        "Thank you for reaching out. We are looking into your order and will update you shortly."
    )

    token, user, ws = setup_workspace_with_admin(db_session, "sr_success@example.com", client)
    ticket = create_ticket(client, ws.id, token)

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/tickets/{ticket['id']}/suggested-reply",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["suggested_reply"] is not None
    assert "order" in data["suggested_reply"].lower()

    # Verify DB is updated
    db_session.expire_all()
    db_ticket = db_session.query(Ticket).filter(Ticket.id == ticket["id"]).first()
    assert db_ticket.suggested_reply == mock_generate.return_value

    # Audit log must exist
    audit = db_session.query(AuditLog).filter(
        AuditLog.event_type == "suggested_reply_generated",
        AuditLog.entity_id == ticket["id"],
    ).first()
    assert audit is not None
    assert "reply stored" in audit.detail


@patch("app.services.ai_service.generate_suggested_reply")
def test_generate_suggested_reply_ai_unavailable(mock_generate, client, db_session):
    """
    When AI is unavailable (returns None), the endpoint still succeeds,
    stores None on the ticket, and writes an audit log noting unavailability.
    """
    mock_generate.return_value = None

    token, user, ws = setup_workspace_with_admin(db_session, "sr_unavailable@example.com", client)
    ticket = create_ticket(client, ws.id, token, subject="Broken product")

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/tickets/{ticket['id']}/suggested-reply",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["suggested_reply"] is None

    # Audit log should still be written
    db_session.expire_all()
    audit = db_session.query(AuditLog).filter(
        AuditLog.event_type == "suggested_reply_generated",
        AuditLog.entity_id == ticket["id"],
    ).first()
    assert audit is not None
    assert "AI unavailable" in audit.detail


def test_generate_suggested_reply_wrong_workspace_is_forbidden(client, db_session):
    """
    A user who is NOT a member of the ticket's workspace cannot trigger reply generation.
    """
    # Owner creates workspace and ticket
    token_owner, _, ws = setup_workspace_with_admin(db_session, "sr_owner@example.com", client)
    ticket = create_ticket(client, ws.id, token_owner)

    # Outsider registers (different workspace entirely)
    token_outsider = register_and_login(client, "sr_outsider@example.com")
    outsider = db_session.query(User).filter(User.email == "sr_outsider@example.com").first()
    other_ws = Workspace(name="Other WS", owner_id=outsider.id)
    db_session.add(other_ws)
    db_session.commit()
    db_session.refresh(other_ws)
    db_session.add(WorkspaceMember(workspace_id=other_ws.id, user_id=outsider.id, role="admin"))
    db_session.commit()

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/tickets/{ticket['id']}/suggested-reply",
        headers=auth_headers(token_outsider),
    )
    assert resp.status_code == 403


def test_generate_suggested_reply_ticket_not_found(client, db_session):
    """
    404 is returned when the ticket doesn't exist in the workspace.
    """
    token, _, ws = setup_workspace_with_admin(db_session, "sr_404@example.com", client)

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/tickets/999999/suggested-reply",
        headers=auth_headers(token),
    )
    assert resp.status_code == 404


def test_generate_suggested_reply_unauthenticated(client, db_session):
    """
    Ensure the endpoint is protected — no token → 401.
    """
    resp = client.post("/api/v1/workspaces/1/tickets/1/suggested-reply")
    assert resp.status_code == 401
