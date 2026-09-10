"""add judge-visible learning features

Revision ID: c4a7d9e28f31
Revises: 9f0c3a74b2e1
Create Date: 2026-07-30 14:20:00

"""
from alembic import op
import sqlalchemy as sa


revision = "c4a7d9e28f31"
down_revision = "9f0c3a74b2e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','passed','failed','revised')",
            name="ck_agent_run_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_agent_runs_task_type"),
            ["task_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_agent_runs_user_id"),
            ["user_id"],
            unique=False,
        )

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=60), nullable=False),
        sa.Column("action", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','passed','failed','revised','skipped')",
            name="ck_agent_step_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "sequence",
            name="uq_agent_step_run_sequence",
        ),
    )
    with op.batch_alter_table("agent_steps", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_agent_steps_run_id"),
            ["run_id"],
            unique=False,
        )

    op.create_table(
        "remediation_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("target_knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("path_version_id", sa.Integer(), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("initial_mastery", sa.Float(), nullable=True),
        sa.Column("target_mastery", sa.Float(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('ready','active','completed','adjusted')",
            name="ck_remediation_plan_status",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["path_version_id"],
            ["learning_path_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_knowledge_point_id"],
            ["knowledge_points.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("remediation_plans", schema=None) as batch_op:
        for column in (
            "agent_run_id",
            "path_version_id",
            "target_knowledge_point_id",
            "user_id",
        ):
            batch_op.create_index(
                batch_op.f(f"ix_remediation_plans_{column}"),
                [column],
                unique=False,
            )

    op.create_table(
        "remediation_plan_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["learning_path_nodes.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["remediation_plans.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id",
            "step_order",
            name="uq_remediation_plan_step_order",
        ),
    )
    with op.batch_alter_table("remediation_plan_steps", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_remediation_plan_steps_node_id"),
            ["node_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_remediation_plan_steps_plan_id"),
            ["plan_id"],
            unique=False,
        )

    op.create_table(
        "adaptive_exams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("result_id", sa.Integer(), nullable=True),
        sa.Column("agent_run_id", sa.Integer(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("goal", sa.String(length=30), nullable=False),
        sa.Column("difficulty", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("blueprint_json", sa.JSON(), nullable=False),
        sa.Column("quiz_json", sa.JSON(), nullable=True),
        sa.Column("pre_mastery_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "goal IN ('diagnosis','reinforcement','mock','comprehensive')",
            name="ck_adaptive_exam_goal",
        ),
        sa.CheckConstraint(
            "status IN ('blueprint','ready','in_progress','completed')",
            name="ck_adaptive_exam_status",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["quiz_results.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("adaptive_exams", schema=None) as batch_op:
        for column in ("agent_run_id", "course_id", "result_id", "user_id"):
            batch_op.create_index(
                batch_op.f(f"ix_adaptive_exams_{column}"),
                [column],
                unique=False,
            )


def downgrade():
    with op.batch_alter_table("adaptive_exams", schema=None) as batch_op:
        for column in reversed(("agent_run_id", "course_id", "result_id", "user_id")):
            batch_op.drop_index(batch_op.f(f"ix_adaptive_exams_{column}"))
    op.drop_table("adaptive_exams")

    with op.batch_alter_table("remediation_plan_steps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_remediation_plan_steps_plan_id"))
        batch_op.drop_index(batch_op.f("ix_remediation_plan_steps_node_id"))
    op.drop_table("remediation_plan_steps")

    with op.batch_alter_table("remediation_plans", schema=None) as batch_op:
        for column in reversed((
            "agent_run_id",
            "path_version_id",
            "target_knowledge_point_id",
            "user_id",
        )):
            batch_op.drop_index(
                batch_op.f(f"ix_remediation_plans_{column}")
            )
    op.drop_table("remediation_plans")

    with op.batch_alter_table("agent_steps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_agent_steps_run_id"))
    op.drop_table("agent_steps")

    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_agent_runs_user_id"))
        batch_op.drop_index(batch_op.f("ix_agent_runs_task_type"))
    op.drop_table("agent_runs")
