"""Board roles and what each one may do. Checked on the server for every route."""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    CHAIR = "chair"
    TREASURER = "treasurer"
    MEMBER = "member"


class Permission(str, Enum):
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_FINANCIALS = "view_financials"
    MANAGE_FINANCIALS = "manage_financials"  # upload statements, enter figures, approve extracted figures
    MANAGE_DONATIONS = "manage_donations"  # add, edit, import, export donation records; track acknowledgments
    VIEW_DONOR_DATA = "view_donor_data"
    MANAGE_EVENTS = "manage_events"
    WRITE_REFLECTIONS = "write_reflections"
    RUN_AGENTS = "run_agents"
    MANAGE_USERS = "manage_users"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.CHAIR: frozenset(Permission),
    Role.TREASURER: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_FINANCIALS,
            Permission.MANAGE_FINANCIALS,
            Permission.VIEW_DONOR_DATA,
            Permission.MANAGE_DONATIONS,
            Permission.MANAGE_EVENTS,
            Permission.WRITE_REFLECTIONS,
            Permission.RUN_AGENTS,
        }
    ),
    # Board members plan events and share reflections, but never see donor or
    # financial records.
    Role.MEMBER: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.MANAGE_EVENTS,
            Permission.WRITE_REFLECTIONS,
            Permission.RUN_AGENTS,
        }
    ),
}


def permissions_for(role: str) -> frozenset[Permission]:
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return frozenset()


def has_permission(role: str, permission: Permission) -> bool:
    return permission in permissions_for(role)
