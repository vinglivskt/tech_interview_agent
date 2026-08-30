"""Scope external feature sessions by user.

Revision ID: 0002_scope_sessions_user
Revises: 0001_init_user_stats
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_scope_sessions_user"
down_revision: str | Sequence[str] | None = "0001_init_user_stats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_feature_sessions_feature_external", "feature_sessions", type_="unique")
    op.create_unique_constraint(
        "uq_feature_sessions_user_feature_external",
        "feature_sessions",
        ["user_id", "feature", "external_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_feature_sessions_user_feature_external", "feature_sessions", type_="unique")
    op.create_unique_constraint(
        "uq_feature_sessions_feature_external",
        "feature_sessions",
        ["feature", "external_id"],
    )
