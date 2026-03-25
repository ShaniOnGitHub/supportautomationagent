from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.api import deps
from app.core.database import get_db
from app.models.user import User
from app.schemas.knowledge import KnowledgeIngest, DocumentResponse
from app.services import knowledge_service
from app.services.workspace_service import check_workspace_membership

router = APIRouter()

@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def ingest_knowledge(
    workspace_id: int,
    ingest: KnowledgeIngest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Ingest a document into the workspace's knowledge base.
    Chunks the text and generates embeddings for semantic search.
    """
    # Verify membership (Admin/Agent)
    role = check_workspace_membership(db, current_user.id, workspace_id)
    if role == "viewer":
        raise HTTPException(status_code=403, detail="Viewers cannot ingest knowledge")
        
    return knowledge_service.ingest_document(
        db, workspace_id, ingest.filename, ingest.content
    )

@router.get("/", response_model=List[DocumentResponse])
def list_knowledge(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List all documents in the workspace knowledge base."""
    check_workspace_membership(db, current_user.id, workspace_id)
    from app.models.knowledge_base import Document
    return db.query(Document).filter(Document.workspace_id == workspace_id).all()
