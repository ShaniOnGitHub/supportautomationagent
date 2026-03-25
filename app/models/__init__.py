# Import all models here so Alembic can discover them
from app.models.ticket import Ticket  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.workspace import Workspace, WorkspaceMember  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.job import Job  # noqa: F401
from app.models.knowledge_base import Document, DocumentChunk  # noqa: F401
from app.models.tool_action import ToolAction  # noqa: F401
