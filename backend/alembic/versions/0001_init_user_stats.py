"""init user stats schema

Revision ID: 0001_init_user_stats
Revises:
Create Date: 2026-08-30

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_init_user_stats"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Перечисления для PostgreSQL
    feature_enum = postgresql.ENUM("chat", "quiz", "sobes", "design", name="feature_enum", create_type=True)
    feature_enum.create(op.get_bind(), checkfirst=True)
    answer_cat_enum = postgresql.ENUM("correct", "partial", "incorrect", name="answer_category_enum", create_type=True)
    answer_cat_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "feature_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("feature", postgresql.ENUM(name="feature_enum", create_type=False), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("level", sa.String(32), nullable=True),
        sa.Column("extra", postgresql.JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("feature", "external_id", name="uq_feature_sessions_feature_external"),
    )
    op.create_index("ix_feature_sessions_user_id", "feature_sessions", ["user_id"])
    op.create_index("ix_feature_sessions_feature", "feature_sessions", ["feature"])

    op.create_table(
        "quiz_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "session_pk",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feature_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("user_answer", sa.Text, nullable=False),
        sa.Column("correct_answer", sa.Text, nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False),
        sa.Column("category", postgresql.ENUM(name="answer_category_enum", create_type=False), nullable=False),
        sa.Column("explanation", sa.Text, nullable=False, server_default=""),
        sa.Column("level", sa.String(32), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_quiz_answers_user_id", "quiz_answers", ["user_id"])
    op.create_index("ix_quiz_answers_category", "quiz_answers", ["category"])
    op.create_index("ix_quiz_answers_session_pk", "quiz_answers", ["session_pk"])

    op.create_table(
        "sobes_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "session_pk",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feature_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("topic", sa.String(64), nullable=False),
        sa.Column("user_answer", sa.Text, nullable=False),
        sa.Column("reference_answer", sa.Text, nullable=False, server_default=""),
        sa.Column("score_percent", sa.Integer, nullable=False),
        sa.Column("is_counted", sa.Boolean, nullable=False),
        sa.Column("category", postgresql.ENUM(name="answer_category_enum", create_type=False), nullable=False),
        sa.Column("techlead_explanation", sa.Text, nullable=False, server_default=""),
        sa.Column("covered_points", sa.JSON, nullable=True),
        sa.Column("missed_points", sa.JSON, nullable=True),
        sa.Column("level", sa.String(32), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sobes_answers_user_id", "sobes_answers", ["user_id"])
    op.create_index("ix_sobes_answers_category", "sobes_answers", ["category"])
    op.create_index("ix_sobes_answers_topic", "sobes_answers", ["topic"])
    op.create_index("ix_sobes_answers_session_pk", "sobes_answers", ["session_pk"])

    op.create_table(
        "design_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "session_pk",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feature_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("scenario_id", sa.String(128), nullable=False),
        sa.Column("step_id", sa.String(128), nullable=False),
        sa.Column("step_title", sa.String(256), nullable=False, server_default=""),
        sa.Column("user_answer", sa.Text, nullable=False),
        sa.Column("score_percent", sa.Integer, nullable=False),
        sa.Column("rubric", postgresql.JSONB, nullable=True),
        sa.Column("category", postgresql.ENUM(name="answer_category_enum", create_type=False), nullable=False),
        sa.Column("covered_points", sa.JSON, nullable=True),
        sa.Column("missed_points", sa.JSON, nullable=True),
        sa.Column("techlead_explanation", sa.Text, nullable=False, server_default=""),
        sa.Column("hint_used", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("level", sa.String(32), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_design_answers_user_id", "design_answers", ["user_id"])
    op.create_index("ix_design_answers_category", "design_answers", ["category"])
    op.create_index("ix_design_answers_session_pk", "design_answers", ["session_pk"])

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "session_pk",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feature_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("session_key", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_messages_user_id", "chat_messages", ["user_id"])
    op.create_index("ix_chat_messages_session_key", "chat_messages", ["session_key"])
    op.create_index("ix_chat_messages_session_pk", "chat_messages", ["session_pk"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_pk", table_name="chat_messages")
    op.drop_index("ix_chat_messages_session_key", table_name="chat_messages")
    op.drop_index("ix_chat_messages_user_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("ix_design_answers_session_pk", table_name="design_answers")
    op.drop_index("ix_design_answers_category", table_name="design_answers")
    op.drop_index("ix_design_answers_user_id", table_name="design_answers")
    op.drop_table("design_answers")

    op.drop_index("ix_sobes_answers_session_pk", table_name="sobes_answers")
    op.drop_index("ix_sobes_answers_topic", table_name="sobes_answers")
    op.drop_index("ix_sobes_answers_category", table_name="sobes_answers")
    op.drop_index("ix_sobes_answers_user_id", table_name="sobes_answers")
    op.drop_table("sobes_answers")

    op.drop_index("ix_quiz_answers_session_pk", table_name="quiz_answers")
    op.drop_index("ix_quiz_answers_category", table_name="quiz_answers")
    op.drop_index("ix_quiz_answers_user_id", table_name="quiz_answers")
    op.drop_table("quiz_answers")

    op.drop_index("ix_feature_sessions_feature", table_name="feature_sessions")
    op.drop_index("ix_feature_sessions_user_id", table_name="feature_sessions")
    op.drop_table("feature_sessions")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS answer_category_enum")
    op.execute("DROP TYPE IF EXISTS feature_enum")
