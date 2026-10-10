"""Role checks. Services take `actor` as a required keyword: a `User`, or `None` when the
system itself calls (the WhatsApp agent, the matching, the tick). A forgotten actor is a
`TypeError`, never a silent escalation (ADR 0017)."""

from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


def require_role(actor, *roles: str) -> None:
    if actor is None:
        return
    if getattr(actor, "role", None) not in roles:
        raise PermissionDenied(f"Requires role: {', '.join(roles)}")


class HasAnyRole(BasePermission):
    """Default for the API: authenticated and in one of the role groups. A user without a role
    (for example the admin superuser) gets 403 instead of the manager's view of the data."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.role in ("manager", "sales", "production"))


class HasRole(BasePermission):
    roles: tuple[str, ...] = ()

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.role in self.roles)


class IsManager(HasRole):
    roles = ("manager",)


class IsManagerOrProduction(HasRole):
    roles = ("manager", "production")


class IsManagerOrSales(HasRole):
    roles = ("manager", "sales")
