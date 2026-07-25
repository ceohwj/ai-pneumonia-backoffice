"""add patient email and background email jobs

Revision ID: a8f1c2d3e4b5
Revises: 6f2e4b7a9c10
Create Date: 2026-07-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a8f1c2d3e4b5"
down_revision: Union[str, Sequence[str], None] = "6f2e4b7a9c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=True,
            comment="AI 예측 결과 수신 이메일",
        ),
    )
    op.create_table(
        "email_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=50), nullable=False, comment="Celery 작업 ID"),
        sa.Column("record_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True, comment="이메일 전송 요청 사용자 ID"),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "STARTED",
                "SUCCESS",
                "RETRY",
                "FAILURE",
                name="email_job_status",
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("retry_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("result_message", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["medical_records.id"],
            name="fk_email_jobs_record_id_medical_records",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_email_jobs_requested_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_email_jobs_task_id"),
    )
    op.create_index("ix_email_jobs_record_id", "email_jobs", ["record_id"])
    op.create_index("ix_email_jobs_requested_by", "email_jobs", ["requested_by"])


def downgrade() -> None:
    op.drop_index("ix_email_jobs_requested_by", table_name="email_jobs")
    op.drop_index("ix_email_jobs_record_id", table_name="email_jobs")
    op.drop_table("email_jobs")
    op.drop_column("patients", "email")
