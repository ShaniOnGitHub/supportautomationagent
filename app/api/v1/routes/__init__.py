from fastapi import APIRouter
from app.api.v1.routes import auth, health, tickets, messages, workspaces, webhooks, knowledge, tools

router = APIRouter()
router.include_router(health.router, tags=["Health"])
router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(workspaces.router, prefix="/workspaces", tags=["Workspaces"])
router.include_router(
    webhooks.router,
    prefix="/workspaces",
    tags=["Webhooks"],
)
router.include_router(
    knowledge.router,
    prefix="/workspaces/{workspace_id}/knowledge",
    tags=["Knowledge"],
)
router.include_router(
    tickets.router,
    prefix="/workspaces/{workspace_id}/tickets",
    tags=["Tickets"],
)
router.include_router(
    messages.router,
    prefix="/workspaces/{workspace_id}/tickets/{ticket_id}/messages",
    tags=["Messages"],
)
router.include_router(
    tools.router,
    prefix="/workspaces/{workspace_id}/tickets/{ticket_id}/actions",
    tags=["Tool Actions"],
)
