import pytest
from unittest.mock import patch, MagicMock
from app.models.user import User

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

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_approve_reply_creates_message(client, db_session):
    """Verify that approving a reply creates a message and updates status."""
    token = register_and_login(client, "agent@test.com")
    headers = auth_headers(token)

    # 1. Setup workspace and ticket
    ws_resp = client.post("/api/v1/workspaces/", json={"name": "Approval WS"}, headers=headers)
    assert ws_resp.status_code == 201
    ws_id = ws_resp.json()["id"]
    
    ticket_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/tickets/",
        json={"subject": "Need help", "description": "Please help me"},
        headers=headers
    )
    assert ticket_resp.status_code == 201
    ticket_id = ticket_resp.json()["id"]

    # 2. Trigger suggestion (mocked)
    with patch("app.services.ai_service.genai.GenerativeModel.generate_content") as mock_gen:
        mock_response = MagicMock()
        mock_response.text = "This is a suggestion"
        mock_gen.return_value = mock_response
        
        resp = client.post(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/suggested-reply", headers=headers)
        assert resp.status_code == 200

    # Verify pending status
    ticket_data = client.get(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}", headers=headers).json()
    assert ticket_data["suggested_reply_status"] == "pending"

    # 3. Approve reply
    approve_resp = client.post(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/approve-reply", headers=headers)
    assert approve_resp.status_code == 200
    assert approve_resp.json()["suggested_reply_status"] == "approved"

    # 4. Verify message exists
    msg_resp = client.get(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/messages/", headers=headers)
    assert msg_resp.status_code == 200
    messages = msg_resp.json()
    assert len(messages) == 1
    assert messages[0]["body"] == "This is a suggestion"


def test_reject_reply_updates_status(client, db_session):
    """Verify that rejecting a reply updates the status to 'rejected'."""
    token = register_and_login(client, "rejector@test.com")
    headers = auth_headers(token)

    ws_resp = client.post("/api/v1/workspaces/", json={"name": "Reject WS"}, headers=headers)
    ws_id = ws_resp.json()["id"]
    ticket_resp = client.post(f"/api/v1/workspaces/{ws_id}/tickets/", json={"subject": "Help", "description": "Me"}, headers=headers)
    ticket_id = ticket_resp.json()["id"]

    # 2. Suggestion
    with patch("app.services.ai_service.genai.GenerativeModel.generate_content") as mock_gen:
        mock_response = MagicMock()
        mock_response.text = "Suggest"
        mock_gen.return_value = mock_response
        client.post(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/suggested-reply", headers=headers)

    # 3. Reject
    reject_resp = client.post(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/reject-reply", headers=headers)
    assert reject_resp.status_code == 200
    assert reject_resp.json()["suggested_reply_status"] == "rejected"
    
    # Verify NO message was created
    msg_resp = client.get(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/messages/", headers=headers)
    assert len(msg_resp.json()) == 0


def test_unauthorized_approval_is_forbidden(client, db_session):
    """Verify RBAC: user from another workspace cannot approve."""
    # 1. WS A with Ticket (User A)
    token_a = register_and_login(client, "user_a@test.com")
    headers_a = auth_headers(token_a)
    ws_a = client.post("/api/v1/workspaces/", json={"name": "WS A"}, headers=headers_a).json()
    ticket = client.post(f"/api/v1/workspaces/{ws_a['id']}/tickets/", json={"subject": "A", "description": "B"}, headers=headers_a).json()
    
    # Suggestion
    with patch("app.services.ai_service.genai.GenerativeModel.generate_content") as mock_gen:
        mock_response = MagicMock()
        mock_response.text = "Suggest"
        mock_gen.return_value = mock_response
        client.post(f"/api/v1/workspaces/{ws_a['id']}/tickets/{ticket['id']}/suggested-reply", headers=headers_a)

    # 2. User B (login)
    token_b = register_and_login(client, "user_b_unauth@test.com")
    headers_b = auth_headers(token_b)
    
    # 3. Try approve Ticket in WS A with User B token
    bad_resp = client.post(
        f"/api/v1/workspaces/{ws_a['id']}/tickets/{ticket['id']}/approve-reply",
        headers=headers_b
    )
    assert bad_resp.status_code == 403
