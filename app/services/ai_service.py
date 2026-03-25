import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import List, Optional
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
        return None

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        
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
                temperature=0.1
            )
        )
        
        if not response or not response.text:
            return None

        import json
        try:
            data = json.loads(response.text)
            return TriageResult(**data)
        except (json.JSONDecodeError, ValueError):
            return None

    except Exception as e:
        print(f"AI Triage Error: {e}")
        return None


def generate_suggested_reply(subject: str, description: str, context: str = "") -> str | None:
    """
    Calls Gemini to draft a polite suggested reply for the support agent.
    If context is provided, it grounds the response in company docs.
    """
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_key_here":
        return None

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")

        rag_prompt = ""
        if context:
            rag_prompt = f"""
Use the following documentation context to ground your answer. 
If the answer is in the context, use it. If not, give a general polite response.
Always include a brief citation if you used the context (e.g., "[Source: Company Policy]").

Context:
{context}
"""

        prompt = f"""You are a professional customer support agent.
{rag_prompt}

Draft a brief, polite reply to the following customer support ticket.
Be empathetic, concise (2-4 sentences), and do NOT make specific promises you cannot keep.
Do NOT include a subject line. Output only the reply body.

Subject: {subject}
Customer message: {description or 'No description provided.'}
"""
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.3,
            ),
        )
        if response and hasattr(response, "text") and response.text:
            return response.text.strip()
        return None

    except Exception as e:
        print(f"AI Suggestion Error: {e}")
        return None


def generate_embeddings(text: str, task_type: str = "retrieval_document") -> list[float] | None:
    """
    Generate vector embeddings for the given text using Gemini.
    """
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_key_here":
        return None

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content=text,
            task_type=task_type
        )
        # Handle both dict and object response formats
        if isinstance(result, dict):
            return result.get("embedding")
        if hasattr(result, "embedding"):
            return result.embedding
        return None

    except Exception as e:
        print(f"AI Embedding Error: {e}")
        return None

class ProposedAction(BaseModel):
    tool_name: str = Field(..., description="The name of the tool, e.g., 'check_order_status'")
    parameters: dict = Field(..., description="JSON parameters, e.g., {'order_id': '555'}")

class ProposedActionsList(BaseModel):
    actions: List[ProposedAction]

def propose_actions_for_ticket(subject: str, body: str) -> List[ProposedAction]:
    """
    Analyzes ticket content and proposes relevant tool actions.
    """
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_key_here":
        return []

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # Using 1.5-flash for more stable instruction following in this MVP
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt = f"""
        Analyze the following ticket and return a JSON object with a list of utility tool actions.
        Available tools:
        - check_order_status: parameters: {'order_id': '...'}
        - check_refund_status: parameters: {'order_id': '...'}

        If 'order_id' or an order number is mentioned (e.g. #555), you MUST propose 'check_order_status'.
        
        Ticket:
        Subject: {subject}
        Body: {body}
        
        Return JSON in this EXACT format:
        {{ "actions": [ {{ "tool_name": "...", "parameters": {{ "order_id": "..." }} }} ] }}
        """

        print(f"AI Proposing Actions for Ticket: {subject}")
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        
        if not response or not response.text:
            print("AI Proposed Actions: Empty response from Gemini")
            return []

        import json
        try:
            print(f"AI Gemini Raw Reply: {response.text}")
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            actions = [ProposedAction(**a) for a in data.get("actions", [])]
            print(f"AI Proposed {len(actions)} actions")
            return actions
        except Exception as e:
            print(f"AI Tool Proposal Parsing Error: {e} | Raw: {response.text}")
            return []

    except Exception as e:
        print(f"AI Tool Proposal Error: {e}")
        return []
