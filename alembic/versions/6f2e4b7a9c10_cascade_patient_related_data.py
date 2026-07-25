"""cascade patient related data

Revision ID: 6f2e4b7a9c10
Revises: 9c100473a68a
Create Date: 2026-07-24

"""

from typing import Sequence, Union

from alembic import op


revision: str = "6f2e4b7a9c10"
down_revision: Union[str, Sequence[str], None] = "9c100473a68a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """진료기록 삭제 시 X-ray와 AI 분석 결과를 함께 삭제합니다."""

    op.drop_constraint(
        "xray_images_ibfk_1",
        "xray_images",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_xray_images_record_id_medical_records",
        "xray_images",
        "medical_records",
        ["record_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "ai_analysis_results_ibfk_1",
        "ai_analysis_results",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_ai_analysis_results_record_id_medical_records",
        "ai_analysis_results",
        "medical_records",
        ["record_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """진료기록 외래키를 연쇄 삭제가 없는 상태로 되돌립니다."""

    op.drop_constraint(
        "fk_xray_images_record_id_medical_records",
        "xray_images",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "xray_images_ibfk_1",
        "xray_images",
        "medical_records",
        ["record_id"],
        ["id"],
    )

    op.drop_constraint(
        "fk_ai_analysis_results_record_id_medical_records",
        "ai_analysis_results",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "ai_analysis_results_ibfk_1",
        "ai_analysis_results",
        "medical_records",
        ["record_id"],
        ["id"],
    )
