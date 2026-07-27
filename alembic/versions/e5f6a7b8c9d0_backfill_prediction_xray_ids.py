"""backfill prediction xray image ids

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE ai_analysis_results AS analysis
        JOIN (
            SELECT id, record_id
            FROM (
                SELECT
                    id,
                    record_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY record_id
                        ORDER BY shooting_datetime DESC, id DESC
                    ) AS rn
                FROM xray_images
            ) AS ranked_xrays
            WHERE rn = 1
        ) AS latest_xray
            ON latest_xray.record_id = analysis.record_id
        SET analysis.xray_image_id = latest_xray.id
        WHERE analysis.xray_image_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ai_analysis_results SET xray_image_id = NULL"
    )
