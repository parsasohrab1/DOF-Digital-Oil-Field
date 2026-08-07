"""Add secure command workflow columns to commands table.

Adds the columns needed to persist the 2FA + digital-twin-simulation
workflow state on the `commands` row instead of an in-memory dict.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_secure_command_workflow"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commands",
        sa.Column(
            "stage", sa.String(length=30), nullable=False, server_default="requested"
        ),
    )
    op.add_column(
        "commands", sa.Column("two_fa_verified_at", sa.DateTime(), nullable=True)
    )
    op.add_column("commands", sa.Column("simulation_result", sa.JSON(), nullable=True))
    op.add_column("commands", sa.Column("approval_notes", sa.Text(), nullable=True))
    op.add_column(
        "commands",
        sa.Column("critical", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("commands", "critical")
    op.drop_column("commands", "approval_notes")
    op.drop_column("commands", "simulation_result")
    op.drop_column("commands", "two_fa_verified_at")
    op.drop_column("commands", "stage")
