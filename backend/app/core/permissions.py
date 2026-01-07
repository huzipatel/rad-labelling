"""Role-based access control and permissions."""
from enum import Enum
from typing import List
from functools import wraps
from fastapi import HTTPException, status


class UserRole(str, Enum):
    """User roles in the system."""
    LABELLER = "labeller"
    LABELLING_MANAGER = "labelling_manager"
    ADMIN = "admin"


# Permission definitions
PERMISSIONS = {
    UserRole.LABELLER: [
        "view_assigned_tasks",
        "complete_labelling",
        "view_own_progress",
        "take_snapshot",
    ],
    UserRole.LABELLING_MANAGER: [
        "view_assigned_tasks",
        "complete_labelling",
        "view_own_progress",
        "take_snapshot",
        "upload_spreadsheets",
        "enhance_data",
        "assign_tasks",
        "bulk_assign_tasks",
        "view_all_tasks",
        "view_all_progress",
        "view_labeller_performance",
        "export_data",
        "configure_label_fields",
        "remote_assist",
    ],
    UserRole.ADMIN: [
        "view_assigned_tasks",
        "complete_labelling",
        "view_own_progress",
        "take_snapshot",
        "upload_spreadsheets",
        "enhance_data",
        "assign_tasks",
        "bulk_assign_tasks",
        "view_all_tasks",
        "view_all_progress",
        "view_labeller_performance",
        "export_data",
        "configure_label_fields",
        "remote_assist",
        "manage_users",
        "create_managers",
        "view_system_settings",
        "manage_system_settings",
    ],
}


def has_permission(role: UserRole, permission: str) -> bool:
    """Check if a role has a specific permission."""
    return permission in PERMISSIONS.get(role, [])


def get_permissions(role: UserRole) -> List[str]:
    """Get all permissions for a role."""
    return PERMISSIONS.get(role, [])


def require_role(allowed_roles: List[UserRole]):
    """Decorator to require specific roles for an endpoint."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # The actual role check is done in the dependency
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def check_role_access(user_role: str, required_roles: List[UserRole]) -> bool:
    """Check if user role is in the list of required roles."""
    try:
        role = UserRole(user_role)
        return role in required_roles
    except ValueError:
        return False


def require_permission(permission: str, user_role: str) -> None:
    """Raise exception if user doesn't have required permission."""
    try:
        role = UserRole(user_role)
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission} required"
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid user role"
        )


class RoleChecker:
    """Dependency class for role-based access control."""
    
    def __init__(self, allowed_roles: List[UserRole]):
        self.allowed_roles = allowed_roles
    
    def __call__(self, user_role: str) -> bool:
        if not check_role_access(user_role, self.allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return True


# Pre-configured role checkers
allow_labeller = RoleChecker([UserRole.LABELLER, UserRole.LABELLING_MANAGER, UserRole.ADMIN])
allow_manager = RoleChecker([UserRole.LABELLING_MANAGER, UserRole.ADMIN])
allow_admin = RoleChecker([UserRole.ADMIN])

