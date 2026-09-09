"""add judge_calibration tables

Persist an LLM-judge calibration run (Phase 6, CP 6.2): the judge's identity /
config metadata (never credentials) and aggregate agreement metrics on
``judge_calibration``, one row per scored labeled example on
``judge_calibration_case``. Standalone -- no experiment/project FK, since
calibration is separate from release gating.

Revision ID: 3d8994607d70
Revises: 80db0ccf0fa9
Create Date: 2026-09-09 16:23:50.096785

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d8994607d70"
down_revision: Union[str, Sequence[str], None] = "80db0ccf0fa9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "judge_calibration",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "judge_provider",
            sa.Enum(
                "openai", "anthropic", "ollama", name="provider_name", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("judge_model", sa.String(length=200), nullable=False),
        sa.Column("judge_name", sa.String(length=200), nullable=False),
        sa.Column("judge_temperature", sa.Float(), nullable=False),
        sa.Column("rubric_id", sa.String(length=64), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("scored", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("agreements", sa.Integer(), nullable=False),
        sa.Column("agreement_rate", sa.Float(), nullable=True),
        sa.Column("true_positives", sa.Integer(), nullable=False),
        sa.Column("true_negatives", sa.Integer(), nullable=False),
        sa.Column("false_positives", sa.Integer(), nullable=False),
        sa.Column("false_negatives", sa.Integer(), nullable=False),
        sa.Column("precision", sa.Float(), nullable=True),
        sa.Column("recall", sa.Float(), nullable=True),
        sa.Column("f1", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "judge_temperature >= 0.0",
            name=op.f("ck_judge_calibration_judge_temperature_nonneg"),
        ),
        sa.CheckConstraint(
            "total >= 0 AND scored >= 0 AND failures >= 0",
            name=op.f("ck_judge_calibration_counts_nonneg"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_judge_calibration")),
    )
    op.create_table(
        "judge_calibration_case",
        sa.Column("calibration_id", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("human_pass", sa.Boolean(), nullable=False),
        sa.Column("judge_pass", sa.Boolean(), nullable=True),
        sa.Column("judge_score", sa.Float(), nullable=True),
        sa.Column("judge_reasoning", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(judge_pass IS NULL) = (error IS NOT NULL)",
            name=op.f("ck_judge_calibration_case_error_iff_judge_failed"),
        ),
        sa.ForeignKeyConstraint(
            ["calibration_id"],
            ["judge_calibration.id"],
            name=op.f("fk_judge_calibration_case_calibration_id_judge_calibration"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "calibration_id", "position", name=op.f("pk_judge_calibration_case")
        ),
    )
    op.create_index(
        op.f("ix_judge_calibration_case_calibration_id"),
        "judge_calibration_case",
        ["calibration_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_judge_calibration_case_calibration_id"),
        table_name="judge_calibration_case",
    )
    op.drop_table("judge_calibration_case")
    op.drop_table("judge_calibration")
