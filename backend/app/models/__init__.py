"""SQLAlchemy compatibility mappings."""

from app.models.auth import Permission, Role, User, role_permissions
from app.models.base import Base
from app.models.organization import Organization

__all__ = ["Base", "Organization", "Permission", "Role", "User", "role_permissions"]
