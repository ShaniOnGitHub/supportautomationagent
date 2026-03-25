from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class KnowledgeIngest(BaseModel):
    filename: str
    content: str
    
    model_config = ConfigDict(extra="forbid")

class DocumentResponse(BaseModel):
    id: int
    filename: str
    workspace_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
