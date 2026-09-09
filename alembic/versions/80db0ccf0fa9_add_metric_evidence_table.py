"""add metric_evidence table

Per-metric paired-bootstrap statistical evidence for an EvaluationResult
(Phase 5, CP 5.2). A flat child table of ``evaluation_result``, like
``metric_comparison``; the three SampleSummary value objects (baseline /
candidate / paired-delta) are flattened onto ``*_mean`` / ``*_median`` /
``*_stdev`` columns.

Revision ID: 80db0ccf0fa9
Revises: dab5fa89c47d
Create Date: 2026-09-08 23:54:22.883980

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "80db0ccf0fa9"
down_revision: Union[str, Sequence[str], None] = "dab5fa89c47d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "metric_evidence",
        sa.Column("evaluation_result_id", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("n_pairs", sa.Integer(), nullable=False),
        sa.Column("baseline_mean", sa.Float(), nullable=False),
        sa.Column("baseline_median", sa.Float(), nullable=False),
        sa.Column("baseline_stdev", sa.Float(), nullable=False),
        sa.Column("candidate_mean", sa.Float(), nullable=False),
        sa.Column("candidate_median", sa.Float(), nullable=False),
        sa.Column("candidate_stdev", sa.Float(), nullable=False),
        sa.Column("paired_delta_mean", sa.Float(), nullable=False),
        sa.Column("paired_delta_median", sa.Float(), nullable=False),
        sa.Column("paired_delta_stdev", sa.Float(), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("relative_change", sa.Float(), nullable=True),
        sa.Column("confidence_level", sa.Float(), nullable=False),
        sa.Column("ci_low", sa.Float(), nullable=True),
        sa.Column("ci_high", sa.Float(), nullable=True),
        sa.Column("ci_excludes_zero", sa.Boolean(), nullable=False),
        sa.Column("insufficient_evidence", sa.Boolean(), nullable=False),
        sa.Column("dropped_provider_failures", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("resamples", sa.Integer(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('binary', 'continuous')",
            name=op.f("ck_metric_evidence_kind_known"),
        ),
        sa.CheckConstraint(
            "confidence_level > 0.0 AND confidence_level < 1.0",
            name=op.f("ck_metric_evidence_confidence_level_unit"),
        ),
        sa.CheckConstraint(
            "dropped_provider_failures >= 0",
            name=op.f("ck_metric_evidence_dropped_nonneg"),
        ),
        sa.CheckConstraint("n_pairs >= 0", name=op.f("ck_metric_evidence_n_pairs_nonneg")),
        sa.ForeignKeyConstraint(
            ["evaluation_result_id"],
            ["evaluation_result.id"],
            name=op.f("fk_metric_evidence_evaluation_result_id_evaluation_result"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "evaluation_result_id", "metric", name=op.f("pk_metric_evidence")
        ),
        sa.UniqueConstraint(
            "evaluation_result_id",
            "position",
            name=op.f("uq_metric_evidence_evaluation_result_id_position"),
        ),
    )
    op.create_index(
        op.f("ix_metric_evidence_evaluation_result_id"),
        "metric_evidence",
        ["evaluation_result_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_metric_evidence_evaluation_result_id"), table_name="metric_evidence"
    )
    op.drop_table("metric_evidence")
