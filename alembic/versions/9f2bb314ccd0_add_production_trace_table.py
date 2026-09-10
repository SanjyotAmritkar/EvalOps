"""add production_trace table

Persist one real interaction captured from a running AI system (Phase 8,
CP 8.1): which project and system version produced it, the ``input`` sent and
``output`` returned, an optional ``reference_output``, optional latency / cost /
error observations, and caller-supplied ``trace_metadata`` (never headers,
cookies, environment, or credentials). A leaf table -- it references a project
and a system version but owns no children and is not yet referenced by any
other table. ``project_id`` / ``system_version_id`` / ``created_at`` are
indexed for per-project, per-version, and recency reads.

Revision ID: 9f2bb314ccd0
Revises: 3d8994607d70
Create Date: 2026-09-09 18:42:44.597405

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9f2bb314ccd0"
down_revision: Union[str, Sequence[str], None] = "3d8994607d70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "production_trace",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("system_version_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("reference_output", sa.Text(), nullable=True),
        sa.Column(
            "trace_metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "origin",
            sa.Enum("production", name="trace_origin", native_enum=False),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cost_usd IS NULL OR cost_usd >= 0.0",
            name=op.f("ck_production_trace_cost_usd_nonneg"),
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0.0",
            name=op.f("ck_production_trace_latency_ms_nonneg"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_production_trace_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["system_version_id"],
            ["system_version.id"],
            name=op.f("fk_production_trace_system_version_id_system_version"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_production_trace")),
    )
    op.create_index(
        op.f("ix_production_trace_created_at"),
        "production_trace",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_production_trace_project_id"),
        "production_trace",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_production_trace_system_version_id"),
        "production_trace",
        ["system_version_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_production_trace_system_version_id"), table_name="production_trace"
    )
    op.drop_index(op.f("ix_production_trace_project_id"), table_name="production_trace")
    op.drop_index(op.f("ix_production_trace_created_at"), table_name="production_trace")
    op.drop_table("production_trace")
