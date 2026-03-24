import pytest
from unittest.mock import patch, MagicMock

# Create a mock response with a .text attribute back with JSON
class MockGeminiResponse:
    def __init__(self, text):
        self.text = text

def test_classify_ticket_no_api_key(db_session):
    """If no API key is set, the service should return None safely."""
    from app.services.ai_service import classify_ticket_with_gemini
    from app.core.config import settings
    
    # Force key to be empty or default
    settings.GEMINI_API_KEY = ""
    res = classify_ticket_with_gemini("Subject", "Body")
    assert res is None

@patch("google.generativeai.GenerativeModel")
@patch("google.generativeai.configure")
def test_classify_ticket_success(mock_configure, mock_model_class, db_session):
    """Test successful structured response breakdown from Gemini."""
    from app.services.ai_service import classify_ticket_with_gemini
    from app.core.config import settings
    
    settings.GEMINI_API_KEY = "dummy-key"
    
    # Configure mock instance
    mock_model_instance = MagicMock()
    mock_model_class.return_value = mock_model_instance
    
    # Set up JSON return text string
    mock_model_instance.generate_content.return_value = MockGeminiResponse(
        '{"priority": "high", "sentiment": "frustrated", "summary": "User needs refund"}'
    )
    
    res = classify_ticket_with_gemini("Billing issue", "I was double charged! Fix this.")
    
    assert res is not None
    assert res.priority == "high"
    assert res.sentiment == "frustrated"
    assert res.summary == "User needs refund"
    
    # Verify configure was called
    mock_configure.assert_called_once_with(api_key="dummy-key")

def test_ai_triage_background_task_integration(client, db_session):
    """
    Test that calling the webhook ingest creates background tasks
    which correctly trigger are able to trigger the real function loop.
    We'll patch classify_ticket_with_gemini to respond immediately.
    """
    from app.models.user import User
    from app.models.workspace import Workspace
    from app.models.audit_log import AuditLog
    
    # Setup workspace
    owner = User(email="triage_owner@ws.com", hashed_password="pw", full_name="O")
    db_session.add(owner)
    db_session.flush()
    
    ws = Workspace(name="Triage WS", owner_id=owner.id, webhook_secret="secret123")
    db_session.add(ws)
    db_session.commit()
    
    with patch("app.services.ai_service.classify_ticket_with_gemini") as mock_classify:
        from app.services.ai_service import TriageResult
        mock_classify.return_value = TriageResult(
            priority="urgent", 
            sentiment="angry", 
            summary="Emergency server outage"
        )
        
        payload = {
            "sender_email": "customer@outage.com",
            "subject": "SERVER IS DOWN",
            "body": "Everything is broken.",
        }
        
        # FastAPI BackgroundTasks are executed SYNCHRONOUSLY by the TestClient 
        # at the END of the request block, so we can check DB side effects immediately!
        resp = client.post(
            f"/api/v1/workspaces/{ws.id}/ingest",
            json=payload,
            headers={"X-Webhook-Secret": "secret123"}
        )
        
        assert resp.status_code == 201
        
        # Verify Background execution made AuditLog
        db_session.expire_all() # Clear caches
        
        audit = db_session.query(AuditLog).filter(
            AuditLog.event_type == "ai_triage_complete"
        ).first()
        
        assert audit is not None
        assert "[AI Classification]" in audit.detail
        assert "angry" in audit.detail
        
        # Check priority changed on the ticket in DB
        from app.models.ticket import Ticket
        ticket = db_session.query(Ticket).filter(Ticket.workspace_id == ws.id).first()
        assert ticket is not None
        assert ticket.priority == "urgent"
