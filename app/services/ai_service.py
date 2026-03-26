from google import genai
from google.genai import types
import datetime
import time
from pydantic import BaseModel, Field
from typing import List, Optional
from app.core.config import settings

class TriageResult(BaseModel):
    priority: str = Field(..., description="The priority of the ticket: 'low', 'medium', 'high', or 'urgent'")
    sentiment: str = Field(..., description="Brief description of user sentiment (e.g., 'frustrated', 'neutral', 'satisfied')")
    summary: str = Field(..., description="A concise 1-sentence summary of the core issue")

class ProposedAction(BaseModel):
    tool_name: str = Field(..., description="The name of the tool, e.g., 'check_order_status'")
    parameters: dict = Field(..., description="JSON parameters, e.g., {'order_id': '555'}")

class ProposedActionsList(BaseModel):
    actions: List[ProposedAction]

def _log_error(msg: str):
    with open("error_log.txt", "a") as f:
        f.write(f"{datetime.datetime.now()}: {msg}\n")

def _get_client():
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_key_here":
        return None
    return genai.Client(api_key=settings.GEMINI_API_KEY)

def _call_with_retry(fn, retries=3, delay=10):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            err_str = str(e)
            if "quota" in err_str.lower() or "429" in err_str or "rate" in err_str.lower():
                _log_error(f"Rate limit hit (attempt {attempt+1}), retrying in {delay}s: {e}")
                time.sleep(delay)
            else:
                _log_error(f"AI Error: {e}")
                raise
    return None

def classify_ticket_with_gemini(subject: str, body: str) -> TriageResult | None:
    client = _get_client()
    if not client: return None
    try:
        prompt = f"Analyze this ticket and return JSON: Subject: {subject}\nBody: {body}"
        response = _call_with_retry(lambda: client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TriageResult,
                temperature=0.1
            )
        ))
        if response and response.parsed:
            return response.parsed
        return None
    except Exception as e:
        _log_error(f"AI Triage Error: {e}")
        return None

def generate_suggested_reply(subject: str, description: str, context: str = "") -> str | None:
    client = _get_client()
    if not client: return None
    try:
        rag_prompt = f"\nContext from knowledge base:\n{context}\n" if context else ""
        prompt = f"You are a professional support agent. {rag_prompt}\nSubject: {subject}\nCustomer message: {description}\nDraft a concise, polite reply."
        response = _call_with_retry(lambda: client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3)
        ))
        return response.text.strip() if response and response.text else None
    except Exception as e:
        _log_error(f"AI Suggestion Error: {e}")
        return None

def generate_embeddings(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float] | None:
    client = _get_client()
    if not client: return None
    try:
        res = client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(task_type=task_type)
        )
        return res.embeddings[0].values if res.embeddings else None
    except Exception as e:
        _log_error(f"AI Embedding Error: {e}")
        return None

def propose_actions_for_ticket(subject: str, body: str) -> List[ProposedAction]:
    client = _get_client()
    if not client: return []
    try:
        prompt = f"""
        Analyze the following ticket and return a JSON object with a list of utility tool actions.
        Available tools:
        - check_order_status: parameters: {{"order_id": "..."}}
        - check_refund_status: parameters: {{"order_id": "..."}}

        If 'order_id' or an order number is mentioned (e.g. #555, order_id: 555), you MUST propose 'check_order_status'.
        
        Ticket:
        Subject: {subject}
        Body: {body}
        
        Return JSON in this EXACT format:
        {{"actions": [{{"tool_name": "check_order_status", "parameters": {{"order_id": "555"}}}}]}}
        """
        response = _call_with_retry(lambda: client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1
            )
        ))
        if response and response.text:
            import json
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            actions = [ProposedAction(**a) for a in data.get("actions", [])]
            return actions
        return []
    except Exception as e:
        _log_error(f"AI Tool Proposal Error: {e}")
        return []
