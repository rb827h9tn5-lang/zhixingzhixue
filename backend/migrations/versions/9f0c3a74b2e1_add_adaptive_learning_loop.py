"""add adaptive learning closed loop

Revision ID: 9f0c3a74b2e1
Revises: 1ddb543ec69b
Create Date: 2026-07-30 11:30:00

"""
from alembic import op
import sqlalchemy as sa


revision = "9f0c3a74b2e1"
down_revision = "1ddb543ec69b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_path_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), nullable=True),
        sa.Column("reason_event_id", sa.Integer(), nullable=True),
        sa.Column("replanning_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["learning_path_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["path_id"], ["learning_paths.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path_id", "version_number", name="uq_learning_path_version"),
    )
    with op.batch_alter_table("learning_path_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_learning_path_versions_path_id"),
            ["path_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learning_path_versions_reason_event_id"),
            ["reason_event_id"],
            unique=False,
        )

    op.create_table(
        "learning_path_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path_version_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=True),
        sa.Column("node_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("difficulty", sa.String(length=30), nullable=False),
        sa.Column("mastery_before", sa.Float(), nullable=True),
        sa.Column("mastery_target", sa.Float(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("node_type", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "node_type IN ('normal','review','remediation','assessment')",
            name="ck_learning_path_node_type",
        ),
        sa.CheckConstraint(
            "status IN ('locked','ready','learning','completed','remediation')",
            name="ck_learning_path_node_status",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["path_version_id"],
            ["learning_path_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "path_version_id",
            "node_order",
            name="uq_learning_path_node_order",
        ),
    )
    with op.batch_alter_table("learning_path_nodes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_learning_path_nodes_knowledge_point_id"),
            ["knowledge_point_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_learning_path_nodes_path_version_id"),
            ["path_version_id"],
            unique=False,
        )

    op.create_table(
        "learning_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=220), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=True),
        sa.Column("path_id", sa.Integer(), nullable=True),
        sa.Column("path_version_id", sa.Integer(), nullable=True),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("question_id", sa.String(length=120), nullable=True),
        sa.Column("assessment_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=60), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ("
            "'question_correct','question_wrong','question_partial','assessment_complete',"
            "'hint_request','resource_open','resource_complete','node_open','node_complete',"
            "'code_run','code_error','tutor_help','replan_trigger'"
            ")",
            name="ck_learning_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["quiz_results.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["node_id"], ["learning_path_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["path_id"], ["learning_paths.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["path_version_id"],
            ["learning_path_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "event_key", name="uq_learning_event_user_key"),
    )
    with op.batch_alter_table("learning_events", schema=None) as batch_op:
        for column in (
            "assessment_id",
            "created_at",
            "event_type",
            "knowledge_point_id",
            "node_id",
            "path_id",
            "path_version_id",
            "resource_id",
            "user_id",
        ):
            batch_op.create_index(
                batch_op.f(f"ix_learning_events_{column}"),
                [column],
                unique=False,
            )

    op.create_table(
        "user_knowledge_mastery",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("mastery_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("alpha", sa.Float(), nullable=False),
        sa.Column("beta", sa.Float(), nullable=False),
        sa.Column("evidence_weight", sa.Float(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("wrong_count", sa.Integer(), nullable=False),
        sa.Column("partial_count", sa.Integer(), nullable=False),
        sa.Column("hint_count", sa.Integer(), nullable=False),
        sa.Column("assessment_count", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_event_id"],
            ["learning_events.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "knowledge_point_id",
            name="uq_user_knowledge_mastery_user_point",
        ),
    )
    with op.batch_alter_table("user_knowledge_mastery", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_user_knowledge_mastery_knowledge_point_id"),
            ["knowledge_point_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_user_knowledge_mastery_user_id"),
            ["user_id"],
            unique=False,
        )

    op.create_table(
        "mastery_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mastery_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("old_score", sa.Float(), nullable=False),
        sa.Column("new_score", sa.Float(), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["learning_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["mastery_id"],
            ["user_knowledge_mastery.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mastery_id", "event_id", name="uq_mastery_evidence_event"),
    )
    with op.batch_alter_table("mastery_evidence", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mastery_evidence_event_id"),
            ["event_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_mastery_evidence_mastery_id"),
            ["mastery_id"],
            unique=False,
        )

    op.create_table(
        "node_resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("personalization_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["learning_path_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "resource_id", name="uq_node_resource"),
    )
    with op.batch_alter_table("node_resources", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_node_resources_node_id"),
            ["node_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_node_resources_resource_id"),
            ["resource_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("node_resources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_node_resources_resource_id"))
        batch_op.drop_index(batch_op.f("ix_node_resources_node_id"))
    op.drop_table("node_resources")

    with op.batch_alter_table("mastery_evidence", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mastery_evidence_mastery_id"))
        batch_op.drop_index(batch_op.f("ix_mastery_evidence_event_id"))
    op.drop_table("mastery_evidence")

    with op.batch_alter_table("user_knowledge_mastery", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_knowledge_mastery_user_id"))
        batch_op.drop_index(
            batch_op.f("ix_user_knowledge_mastery_knowledge_point_id")
        )
    op.drop_table("user_knowledge_mastery")

    with op.batch_alter_table("learning_events", schema=None) as batch_op:
        for column in reversed((
            "assessment_id",
            "created_at",
            "event_type",
            "knowledge_point_id",
            "node_id",
            "path_id",
            "path_version_id",
            "resource_id",
            "user_id",
        )):
            batch_op.drop_index(batch_op.f(f"ix_learning_events_{column}"))
    op.drop_table("learning_events")

    with op.batch_alter_table("learning_path_nodes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_learning_path_nodes_path_version_id"))
        batch_op.drop_index(batch_op.f("ix_learning_path_nodes_knowledge_point_id"))
    op.drop_table("learning_path_nodes")

    with op.batch_alter_table("learning_path_versions", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_learning_path_versions_reason_event_id")
        )
        batch_op.drop_index(batch_op.f("ix_learning_path_versions_path_id"))
    op.drop_table("learning_path_versions")
