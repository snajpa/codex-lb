"""index the cost-backfill scan on its leading predicate (MySQL port branch)

The backfill page is

    SELECT ... FROM request_logs
    WHERE id > 0 AND cost_usd IS NULL AND model_source_id IS NULL
      AND (model_source_kind IS NULL OR model_source_kind = 'subscription')
      AND input_tokens IS NOT NULL AND (output_tokens IS NOT NULL OR reasoning_tokens IS NOT NULL)
    ORDER BY id LIMIT 200 FOR UPDATE

and it was measured at 7.1 s on the production instance. The existing
``idx_logs_missing_cost (model_source_id, id)`` leads with a column the predicate
does not constrain first, so the plan walked 289 381 rows to find the 12 036 that
need costing. Leading with ``cost_usd`` — the predicate that is true of exactly those
rows — narrows it: 709 ms -> 56 ms on a production-shaped staging database, still a
range scan ordered by ``id`` for the paging and the ``FOR UPDATE`` lock.

Revision ID: 20260926_040000_add_request_logs_cost_backfill_index
Revises: 20260926_030000_add_request_logs_facet_indexes
Create Date: 2026-09-26
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260926_040000_add_request_logs_cost_backfill_index"
down_revision = "20260926_030000_add_request_logs_facet_indexes"
branch_labels = None
depends_on = None

_NAME = "idx_logs_cost_backfill"
_COLUMNS = ["cost_usd", "model_source_id", "id"]


def upgrade() -> None:
    op.create_index(_NAME, "request_logs", _COLUMNS, unique=False, if_not_exists=True)


def downgrade() -> None:
    op.drop_index(_NAME, table_name="request_logs", if_exists=True)
