"""What a portal user may do, by role.

The portal has two roles. ``admin`` can do everything; ``agent`` works the
inbox and nothing else. The API never checks the role name: every guarded
route names a permission key and asks whether the person's role holds it, so
the roles are presets over this catalog. A new feature adds its key here and
decides which presets get it; a future custom role is another way of resolving
the same keys and touches nothing else.

Everything not listed is free for anyone signed in: reading the inbox,
replying, taking a conversation from the AI and handing it back, changing its
status, assigning it, creating contacts and tagging them with existing tags,
and their own availability.
"""

# Delete or archive conversations, alone or in bulk.
INBOX_DELETE = "inbox.delete"
# Import, export, delete, merge and block contacts.
CONTACTS_MANAGE = "contacts.manage"
# Create, rename, recolor and delete tags. Putting an existing tag on a
# contact is free.
TAGS_MANAGE = "tags.manage"
# Create and delete WhatsApp templates. Sending an approved one is free.
TEMPLATES_MANAGE = "templates.manage"
# Create, edit and delete saved replies. Using one is free.
CANNED_MANAGE = "canned.manage"
# Create, edit and delete teams and their membership.
TEAMS_MANAGE = "teams.manage"
# The reports tab.
REPORTS_VIEW = "reports.view"

PERMISSIONS: tuple[str, ...] = (
    INBOX_DELETE,
    CONTACTS_MANAGE,
    TAGS_MANAGE,
    TEMPLATES_MANAGE,
    CANNED_MANAGE,
    TEAMS_MANAGE,
    REPORTS_VIEW,
)

ROLES: dict[str, frozenset[str]] = {
    "admin": frozenset(PERMISSIONS),
    "agent": frozenset(),
}
DEFAULT_ROLE = "agent"


def permissions_for(role: str | None) -> frozenset[str]:
    """The keys a role holds. An unknown role holds nothing."""
    return ROLES.get(role or "", frozenset())


def has_permission(role: str | None, key: str) -> bool:
    return key in permissions_for(role)
