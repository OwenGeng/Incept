"""Authorization policy for the independently owned Video Production domain.

This module is intentionally framework-free so HTTP routes, durable jobs and
MCP tools share the exact same owner/delegated-operator decision.  It does not
grant a project viewer a hidden write path: only the project owner or an
explicitly trusted workspace operator may access a project by id.
"""

from app.incept.models import Role, User


# Managers and administrators are accountable workspace operators.  They may
# recover, inspect and modify a team project when production continuity needs
# it; ordinary users may only access projects they created.
VIDEO_PRODUCTION_OPERATOR_ROLES = frozenset({Role.manager, Role.admin})


def can_access_video_production(*, owner_id: str, user: User) -> bool:
    """Return whether ``user`` may read or mutate this project.

    The same rule deliberately governs reads and mutations.  Any future
    reviewer-only role must be introduced here with a separate action policy,
    rather than being silently admitted through a string comparison at a route.
    """

    return user.id == owner_id or user.role in VIDEO_PRODUCTION_OPERATOR_ROLES


def can_list_workspace_video_productions(user: User) -> bool:
    """Return whether ``user`` may list projects they do not own."""

    return user.role in VIDEO_PRODUCTION_OPERATOR_ROLES
