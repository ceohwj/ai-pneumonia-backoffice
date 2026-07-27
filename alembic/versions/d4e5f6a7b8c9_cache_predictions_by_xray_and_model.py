"""cache predictions by xray image and model

Revision ID: d4e5f6a7b8c9
Revises: a8f1c2d3e4b5
Create Date: 2026-07-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "a8f1c2d3e4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "ai_analysis_results"
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    foreign_keys = {
        foreign_key["name"]
        for foreign_key in inspector.get_foreign_keys(table_name)
    }
    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
    }

    if "xray_image_id" not in columns:
        op.add_column(
            table_name,
            sa.Column(
                "xray_image_id",
                sa.BigInteger(),
                nullable=True,
                comment="예측에 사용한 X-Ray 이미지 ID",
            ),
        )
    if "ix_ai_analysis_results_xray_image_id" not in indexes:
        op.create_index(
            "ix_ai_analysis_results_xray_image_id",
            table_name,
            ["xray_image_id"],
        )
    if "ix_ai_analysis_results_record_id" not in indexes:
        # MySQL 외래키가 기존 복합 유니크 인덱스에 의존하지 않게 한다.
        op.create_index(
            "ix_ai_analysis_results_record_id",
            table_name,
            ["record_id"],
        )
    if "fk_ai_analysis_results_xray_image_id_xray_images" not in foreign_keys:
        op.create_foreign_key(
            "fk_ai_analysis_results_xray_image_id_xray_images",
            table_name,
            "xray_images",
            ["xray_image_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "uq_ai_analysis_record_model" in unique_constraints:
        op.drop_constraint(
            "uq_ai_analysis_record_model",
            table_name,
            type_="unique",
        )
    if "uq_ai_analysis_xray_model" not in unique_constraints:
        op.create_unique_constraint(
            "uq_ai_analysis_xray_model",
            table_name,
            ["xray_image_id", "ai_model"],
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ai_analysis_xray_model",
        "ai_analysis_results",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_ai_analysis_record_model",
        "ai_analysis_results",
        ["record_id", "ai_model"],
    )
    op.drop_constraint(
        "fk_ai_analysis_results_xray_image_id_xray_images",
        "ai_analysis_results",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_ai_analysis_results_xray_image_id",
        table_name="ai_analysis_results",
    )
    op.drop_column("ai_analysis_results", "xray_image_id")
