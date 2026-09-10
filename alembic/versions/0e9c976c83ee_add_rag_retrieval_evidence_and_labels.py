"""add RAG retrieval evidence and labels

Phase 9 (CP 9.1), additive and backward-compatible:

* ``dataset_case.expected_retrieval_ids`` -- JSON string list, the ground-truth
  relevant document/chunk ids for RAG retrieval evaluators. Empty for every
  existing (non-RAG) case and for promoted-trace cases.
* ``evaluation_run.retrieval`` -- JSON list of ``{doc_id, content, rank, score}``
  objects an external RAG system reported for that execution. Empty for every
  existing text-only run.

Both are ``NOT NULL`` with a server default of ``[]`` so the columns backfill
cleanly on a populated database; the ORM always supplies ``[]`` explicitly.

Revision ID: 0e9c976c83ee
Revises: 9f2bb314ccd0
Create Date: 2026-09-09 21:06:17.459749

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0e9c976c83ee"
down_revision: Union[str, Sequence[str], None] = "9f2bb314ccd0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "dataset_case",
        sa.Column(
            "expected_retrieval_ids",
            _JSON,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "evaluation_run",
        sa.Column(
            "retrieval",
            _JSON,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("evaluation_run", "retrieval")
    op.drop_column("dataset_case", "expected_retrieval_ids")
