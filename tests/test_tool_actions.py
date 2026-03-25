import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def auth_data(client):
    email = "tool_tester@test.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": "pass", "full_name": "Tool Tester"})
    resp = client.post("/api/v1/auth/login", data={"username": email, "password": "pass"})
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    ws_resp = client.post("/api/v1/workspaces/", json={"name": "Tool WS"}, headers=headers)
    ws_id = ws_resp.json()["id"]
    return headers, ws_id

def test_ai_proposes_tool_actions(client, db_session, auth_data):
    """Verify AI proposes the correct tool when an order ID is present."""
    headers, ws_id = auth_data
    
    ticket_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/tickets/",
        json={"subject": "Where is my order #12345?", "description": "It's late."},
        headers=headers
    )
    ticket_id = ticket_resp.json()["id"]

    # Mock AI proposal
    with patch("app.services.ai_service.genai.GenerativeModel.generate_content") as mock_gen:
        mock_response = MagicMock()
        # Mocking the JSON response format
        mock_response.text = '{"actions": [{"tool_name": "check_order_status", "parameters": {"order_id": "12345"}}]}'
        mock_gen.return_value = mock_response
        
        # This call should trigger get_proposed_actions
        actions_resp = client.get(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/actions/", headers=headers)
        assert actions_resp.status_code == 200
        actions = actions_resp.json()
        assert len(actions) == 1
        assert actions[0]["tool_name"] == "check_order_status"
        assert actions[0]["parameters"]["order_id"] == "12345"

def test_execute_and_verify_suggestion_grounding(client, db_session, auth_data):
    """Verify tool execution result is included in AI suggestion context."""
    headers, ws_id = auth_data
    
    ticket_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/tickets/",
        json={"subject": "Order status", "description": "Order #999"},
        headers=headers
    )
    ticket_id = ticket_resp.json()["id"]

    # 1. Propose action (mocked)
    with patch("app.services.ai_service.genai.GenerativeModel.generate_content") as mock_gen:
        mock_response = MagicMock()
        mock_response.text = '{"actions": [{"tool_name": "check_order_status", "parameters": {"order_id": "999"}}]}'
        mock_gen.return_value = mock_response
        client.get(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/actions/", headers=headers)

    # Get the action ID
    actions = client.get(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/actions/", headers=headers).json()
    action_id = actions[0]["id"]

    # 2. Execute action
    exec_resp = client.post(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/actions/{action_id}/execute", headers=headers)
    assert exec_resp.status_code == 200
    assert exec_resp.json()["status"] == "success"

    # 3. Trigger suggestion and verify context was passed
    # We patch generate_suggested_reply to inspect the 'context' argument
    with patch("app.services.ai_service.generate_suggested_reply") as mock_sugg:
        mock_sugg.return_value = "Grounding test"
        client.post(f"/api/v1/workspaces/{ws_id}/tickets/{ticket_id}/suggested-reply", headers=headers)
        
        args, kwargs = mock_sugg.call_args
        context = kwargs.get("context", "")
        assert "Tool execution results:" in context
        assert "check_order_status" in context
        assert "TRK999" in context 
