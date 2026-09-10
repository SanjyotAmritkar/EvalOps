"""add agent tool-call evidence and labels

Phase 9 (CP 9.2), additive and backward-compatible:

* ``evaluation_run.tool_calls`` -- JSON list of
  ``{name, arguments, result, ok, error}`` objects an external agent reported
  for that execution, in order. Empty for every existing text-only / RAG run.
* ``dataset_case.expected_tool_calls`` -- JSON list of ``{name, arguments|null}``
  authored expected tool calls. Empty for every existing case and every
  promoted-trace case.

Both are ``NOT NULL`` with a server default of ``[]`` so the columns backfill
cleanly on a populated database; the ORM always supplies ``[]`` explicitly.

Revision ID: c09d84567ccc
Revises: 0e9c976c83ee
Create Date: 2026-09-09 22:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c09d84567ccc"
down_revision: Union[str, Sequence[str], None] = "0e9c976c83ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "dataset_case",
        sa.Column(
            "expected_tool_calls", _JSON, nullable=False, server_default=sa.text("'[]'")
        ),
    )
    op.add_column(
        "evaluation_run",
        sa.Column("tool_calls", _JSON, nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("evaluation_run", "tool_calls")
    op.drop_column("dataset_case", "expected_tool_calls")
