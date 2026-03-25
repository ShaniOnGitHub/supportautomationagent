import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from app.core.database import Base

class ToolAction(Base):
    __tablename__ = "tool_actions"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    
    tool_name = Column(String(100), nullable=False)
    parameters = Column(JSON, nullable=True) # e.g. {"order_id": "12345"}
    
    # Statuses: proposed, success, failed
    status = Column(String(50), default="proposed", nullable=False)
    result = Column(JSON, nullable=True) # e.g. {"status": "shipped", "eta": "tomorrow"}
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # The agent who executed it
