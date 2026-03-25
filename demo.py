import requests
import json
import time

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:8001/api/v1"
EMAIL = "demo_final@example.com"
PASSWORD = "demo-password"

def run_demo():
    print("🚀 Starting End-to-End Demo: AI Support Agent Flow")
    
    # 1. Setup & Auth
    print("\n1️⃣  Registering and Logging in...")
    r = requests.post(f"{BASE_URL}/auth/register", json={
        "email": EMAIL, "password": PASSWORD, "full_name": "Demo Agent"
    })
    print(f"   Register: {r.status_code}")
    
    login_resp = requests.post(f"{BASE_URL}/auth/login", data={
        "username": EMAIL, "password": PASSWORD
    })
    print(f"   Login: {login_resp.status_code}")
    if login_resp.status_code != 200:
        print(f"   ❌ FAILED: {login_resp.text}")
        return

    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Workspace
    print("2️⃣  Creating Workspace...")
    ws_resp = requests.post(f"{BASE_URL}/workspaces/", json={"name": "Global Support"}, headers=headers)
    print(f"   WS Create: {ws_resp.status_code}")
    ws_id = ws_resp.json()["id"]

    # 3. Add Knowledge Base (RAG)
    print("3️⃣  Ingesting Knowledge Base Document...")
    kb_resp = requests.post(f"{BASE_URL}/workspaces/{ws_id}/knowledge/", json={
        "filename": "shipping_policy.txt",
        "content": "Our Standard shipping takes 3-5 business days. Express shipping takes 1-2 days."
    }, headers=headers)
    print(f"   KB Ingest: {kb_resp.status_code}")

    # 4. Create Ticket (Simulation of customer)
    print("4️⃣  Creating Customer Ticket: 'order_id: 555'...")
    ticket_resp = requests.post(f"{BASE_URL}/workspaces/{ws_id}/tickets/", json={
        "subject": "Status check for #555",
        "description": "I need help with order_id: 555. What is the status?"
    }, headers=headers)
    print(f"   Ticket Create: {ticket_resp.status_code}")
    ticket_id = ticket_resp.json()["id"]

    time.sleep(2) # Breathing room for API

    # 5. AI Triage & Suggestion
    print("5️⃣  Generating AI Suggestion & Proposing Tool Actions...")
    sugg_resp = requests.post(f"{BASE_URL}/workspaces/{ws_id}/tickets/{ticket_id}/suggested-reply", headers=headers)
    print(f"   Suggestion: {sugg_resp.status_code}")
    if sugg_resp.status_code != 200:
        print(f"   ❌ FAILED Suggestion: {sugg_resp.text}")
        return
    print(f"   Initial AI Suggestion: \"{sugg_resp.json().get('suggested_reply', 'None')}\"")

    # 6. Tool Action Grounding
    print("6️⃣  Agent executes proposed 'check_order_status' tool...")
    actions_resp = requests.get(f"{BASE_URL}/workspaces/{ws_id}/tickets/{ticket_id}/actions/", headers=headers)
    print(f"   Actions List: {actions_resp.status_code}")
    actions = actions_resp.json()
    if not actions:
        print("   ❌ FAILED: No tool actions proposed by AI.")
        return
    
    action_id = actions[0]["id"]
    exec_resp = requests.post(f"{BASE_URL}/workspaces/{ws_id}/tickets/{ticket_id}/actions/{action_id}/execute", headers=headers)
    print(f"   Action Execute: {exec_resp.status_code}")

    # 7. Regeneate Suggestion with Tool Results
    print("7️⃣  Regenerating suggestion with real-time order data...")
    sugg_resp = requests.post(f"{BASE_URL}/workspaces/{ws_id}/tickets/{ticket_id}/suggested-reply", headers=headers)
    print(f"   Grounded AI Suggestion: \"{sugg_resp.json().get('suggested_reply', 'None')}\"")

    # 8. Human Approval
    print("8️⃣  Agent approves the grounded reply...")
    app_resp = requests.post(f"{BASE_URL}/workspaces/{ws_id}/tickets/{ticket_id}/approve-reply", headers=headers)
    print(f"   Approve: {app_resp.status_code}")
    
    # 9. Final Message Check
    print("9️⃣  Verifying the customer message was sent...")
    msgs_resp = requests.get(f"{BASE_URL}/workspaces/{ws_id}/tickets/{ticket_id}/messages/", headers=headers)
    msgs = msgs_resp.json()
    print(f"   Final Sent Message: \"{msgs[0]['body']}\"")

    print("\n✅ Demo Completed Successfully!")

if __name__ == "__main__":
    try:
        run_demo()
    except Exception as e:
        print(f"❌ Demo encountered exception: {e}")
