# Support Automation Agent

AI powered multi tenant support system that helps teams manage tickets, generate grounded reply suggestions, propose useful actions, and keep humans in control before anything is sent to customers.

## Problem
Support teams often handle repetitive requests manually. Agents read messages, classify issues, search policies, draft replies, and decide next actions by hand. This slows response time, increases inconsistency, and raises operational cost.

This project solves that by combining ticketing, AI triage, document grounded suggestions, tool based enrichment, and approval workflows in one backend system.

## What it does
- Manages support tickets and message threads
- Supports multiple workspaces with strict data isolation
- Uses JWT auth and role based access control
- Generates AI triage such as category and priority
- Creates AI suggested replies for tickets
- Grounds suggestions using company knowledge through RAG
- Proposes useful actions such as checking order status
- Requires human approval before final customer facing replies
- Records audit logs for key actions

## Tech Stack
- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- pgvector
- Gemini API
- Pytest

## Core Flow
1. A support ticket is created
2. AI analyzes the issue and assigns triage data
3. Relevant knowledge base content is retrieved
4. AI generates a grounded suggested reply
5. The system may propose useful actions based on ticket context
6. Tool results are added back into the reply context
7. A human approves, edits, or rejects the draft
8. Approved replies become real messages

## Verification
- 68 automated tests passed
- Verified on SQLite for tests
- Verified on PostgreSQL for runtime flow
- End to end demo includes ticket creation, knowledge ingestion, AI suggestion, tool execution, grounded regeneration, approval, and final message sending

## Run locally
```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```
