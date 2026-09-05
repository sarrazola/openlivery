"""Clients carry an industry code and a business type; agents lose the duplicate fields.

The client used to hold free-form prose (a description and a general
context) that overlapped with the agent's brief, and the agent held a
description that never reached the model plus a goal that repeated its
instructions. The client now identifies the business with two catalog codes
(``industry`` and ``business_type``, see ``app.industries``), plus free
words for the kind of business when the catalog only offers "other", and
every word about what the business does lives on the agent. The agent also
records the language of its prompt's headings (``prompt_language``).

Data moves rather than disappears: each client's general context and each
agent's manual context are appended to the agent's key info and policies
(``brief_policies``), and each agent's brief goal is appended to its
instructions. Descriptions were never part of the prompt
and are dropped. Free-text industries cannot be mapped to codes and are
cleared; the client picks one from the catalog next time it is edited.

Revision ID: 0033_client_identity
Revises: 0032_widget_channels
"""

from alembic import op
import sqlalchemy as sa


revision = "0033_client_identity"
down_revision = "0032_widget_channels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("business_type", sa.String(length=80), nullable=False, server_default=""))
    op.add_column("clients", sa.Column("business_custom", sa.String(length=120), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("prompt_language", sa.String(length=5), nullable=False, server_default="es"))

    op.execute(
        """
        UPDATE agents a
        SET brief_policies = btrim(concat_ws(E'\\n\\n', nullif(btrim(a.brief_policies), ''), nullif(btrim(c.general_context), ''), nullif(btrim(a.manual_context), '')))
        FROM clients c
        WHERE c.id = a.client_id AND (btrim(c.general_context) <> '' OR btrim(a.manual_context) <> '')
        """
    )
    op.execute(
        """
        UPDATE agents
        SET instructions = btrim(concat_ws(E'\\n\\n', nullif(btrim(instructions), ''), btrim(brief_goal)))
        WHERE btrim(brief_goal) <> ''
        """
    )
    op.execute("UPDATE clients SET industry = ''")

    op.drop_column("clients", "description")
    op.drop_column("clients", "general_context")
    op.drop_column("agents", "description")
    op.drop_column("agents", "brief_goal")
    op.drop_column("agents", "manual_context")


def downgrade() -> None:
    op.drop_column("agents", "prompt_language")
    op.add_column("agents", sa.Column("manual_context", sa.Text(), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("brief_goal", sa.Text(), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    op.add_column("clients", sa.Column("general_context", sa.Text(), nullable=False, server_default=""))
    op.add_column("clients", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    op.drop_column("clients", "business_custom")
    op.drop_column("clients", "business_type")
