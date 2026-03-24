"""
Tests for:
  - Message create (success)
  - Message list (success)
  - Forbidden access: non-member cannot create or list messages
  - AuditLog entries created on ticket_create and message_create
"""
import pytest
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.audit_log import AuditLog


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def register_and_login(client, email, password, full_name):
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


def setup_workspace(db, owner_id, member_id=None, member_role="agent"):
    """Create a workspace, add owner as admin (and optionally a second member)."""
    ws = Workspace(name="Test WS", owner_id=owner_id)
    db.add(ws)
    db.commit()
    db.refresh(ws)

    db.add(WorkspaceMember(workspace_id=ws.id, user_id=owner_id, role="admin"))
    if member_id is not None:
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=member_id, role=member_role))
    db.commit()
    return ws


def create_ticket_api(client, ws_id, token, subject="My Ticket"):
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/tickets/",
        json={"subject": subject, "priority": "medium"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ──────────────────────────────────────────────
# Message tests
# ──────────────────────────────────────────────

def test_create_message_success(client, db_session):
    token = register_and_login(client, "msg_user@example.com", "pass123", "Msg User")
    user = db_session.query(User).filter(User.email == "msg_user@example.com").first()
    ws = setup_workspace(db_session, user.id)
    ticket_id = create_ticket_api(client, ws.id, token)

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/tickets/{ticket_id}/messages/",
        json={"body": "Hello, this is a message!"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["body"] == "Hello, this is a message!"
    assert data["ticket_id"] == ticket_id
    assert data["sender_user_id"] == user.id
    assert "id" in data


def test_list_messages_success(client, db_session):
    token = register_and_login(client, "list_msg@example.com", "pass123", "List User")
    user = db_session.query(User).filter(User.email == "list_msg@example.com").first()
    ws = setup_workspace(db_session, user.id)
    ticket_id = create_ticket_api(client, ws.id, token)

    # Post two messages
    for body in ["First message", "Second message"]:
        client.post(
            f"/api/v1/workspaces/{ws.id}/tickets/{ticket_id}/messages/",
            json={"body": body},
            headers=auth_headers(token),
        )

    resp = client.get(
        f"/api/v1/workspaces/{ws.id}/tickets/{ticket_id}/messages/",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    messages = resp.json()
    assert isinstance(messages, list)
    assert len(messages) >= 2
    bodies = [m["body"] for m in messages]
    assert "First message" in bodies
    assert "Second message" in bodies


def test_create_message_forbidden_non_member(client, db_session):
    """A user who is not a workspace member cannot post messages."""
    owner_token = register_and_login(client, "owner_msg@example.com", "pass", "Owner")
    outsider_token = register_and_login(client, "outsider_msg@example.com", "pass", "Outsider")

    owner = db_session.query(User).filter(User.email == "owner_msg@example.com").first()
    ws = setup_workspace(db_session, owner.id)
    ticket_id = create_ticket_api(client, ws.id, owner_token)

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/tickets/{ticket_id}/messages/",
        json={"body": "Sneaky message"},
        headers=auth_headers(outsider_token),
    )
    assert resp.status_code == 403, resp.text


def test_list_messages_forbidden_non_member(client, db_session):
    """A non-member cannot list messages."""
    owner_token = register_and_login(client, "owner_list@example.com", "pass", "Owner2")
    outsider_token = register_and_login(client, "outsider_list@example.com", "pass", "Outsider2")

    owner = db_session.query(User).filter(User.email == "owner_list@example.com").first()
    ws = setup_workspace(db_session, owner.id)
    ticket_id = create_ticket_api(client, ws.id, owner_token)

    resp = client.get(
        f"/api/v1/workspaces/{ws.id}/tickets/{ticket_id}/messages/",
        headers=auth_headers(outsider_token),
    )
    assert resp.status_code == 403, resp.text


# ──────────────────────────────────────────────
# AuditLog tests
# ──────────────────────────────────────────────

def test_audit_log_on_ticket_create(client, db_session):
    """Creating a ticket should produce a ticket_created audit log entry."""
    token = register_and_login(client, "audit_ticket@example.com", "pass", "Audit Ticket")
    user = db_session.query(User).filter(User.email == "audit_ticket@example.com").first()
    ws = setup_workspace(db_session, user.id)
    ticket_id = create_ticket_api(client, ws.id, token, subject="Audited Ticket")

    logs = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == "ticket_created",
            AuditLog.entity_id == ticket_id,
            AuditLog.workspace_id == ws.id,
        )
        .all()
    )
    assert len(logs) == 1
    assert logs[0].actor_user_id == user.id
    assert logs[0].entity_type == "ticket"


def test_audit_log_on_message_create(client, db_session):
    """Creating a message should produce a message_created audit log entry."""
    token = register_and_login(client, "audit_msg@example.com", "pass", "Audit Msg")
    user = db_session.query(User).filter(User.email == "audit_msg@example.com").first()
    ws = setup_workspace(db_session, user.id)
    ticket_id = create_ticket_api(client, ws.id, token)

    resp = client.post(
        f"/api/v1/workspaces/{ws.id}/tickets/{ticket_id}/messages/",
        json={"body": "Audited message"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    message_id = resp.json()["id"]

    logs = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_type == "message_created",
            AuditLog.entity_id == message_id,
            AuditLog.workspace_id == ws.id,
        )
        .all()
    )
    assert len(logs) == 1
    assert logs[0].actor_user_id == user.id
    assert logs[0].entity_type == "message"
