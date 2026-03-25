import datetime
import os
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from app.core.database import Base

def get_embedding_type():
    """
    Returns the appropriate SQLAlchemy type for embeddings.
    Uses Vector(3072) for Postgres and JSON for SQLite (tests).
    """
    if os.getenv("TESTING") == "1":
        from sqlalchemy import JSON
        return JSON
    
    from pgvector.sqlalchemy import Vector
    return Vector(3072)

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    # Gemini text-embedding-004 uses 768 dimensions, gemini-embedding-001 uses 3072
    embedding = Column(get_embedding_type(), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
