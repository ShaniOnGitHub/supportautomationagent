from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class ToolActionBase(BaseModel):
    tool_name: str
    parameters: Optional[dict] = None

class ToolActionCreate(ToolActionBase):
    pass

class ToolActionResponse(ToolActionBase):
    id: int
    ticket_id: int
    workspace_id: int
    status: str
    result: Optional[dict] = None
    created_at: datetime
    executed_at: Optional[datetime] = None
    actor_user_id: Optional[int] = None

    class Config:
        from_attributes = True
