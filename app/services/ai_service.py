import google.generativeai as genai
from pydantic import BaseModel, Field
from app.core.config import settings

class TriageResult(BaseModel):
    """
    Structured response model for Gemini to populate during ticket triage.
    """
    priority: str = Field(
        ..., 
        description="The priority of the ticket: 'low', 'medium', 'high', or 'urgent'"
    )
    sentiment: str = Field(
        ..., 
        description="Brief description of user sentiment (e.g., 'frustrated', 'neutral', 'satisfied')"
    )
    summary: str = Field(
        ..., 
        description="A concise 1-sentence summary of the core issue"
    )

def classify_ticket_with_gemini(subject: str, body: str) -> TriageResult | None:
    """
    Calls the Gemini Structured Output API to categorize & prioritize a ticket.
    Returns TriageResult or None if key is missing or call fails.
    """
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_key_here":
        # Missing key, fail gracefully to maintain job execution flow
        return None

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        # Using Gemini 1.5 Flash as default for classification speed/cost
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt = f"""
        You are an automated IT Support Triage agent.
        Analyze the following incoming ticket and provide structured classification data.

        Subject: {subject}
        Body: {body}
        """

        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=TriageResult,
                temperature=0.1 # Low temperature for accurate structure
            )
        )
        
        # The structured framework from Google automatically deserializes JSON into Pydantic models with model.generate_content
        # depending on SDK version. To be perfectly safe, parse it with Pydantic from response.text
        import json
        data = json.loads(response.text)
        return TriageResult(**data)

    except Exception:
        # Avoid crashing background task, return None to fallback
        return None
