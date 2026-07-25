from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.databases import Base
from app.core.db.models import TimestampMixin

if TYPE_CHECKING:
    from app.models.medical_records import MedicalRecord


class AIAnalysisResult(Base, TimestampMixin):
    __tablename__ = "ai_analysis_results"

    __table_args__ = (
        UniqueConstraint(
            "record_id",
            "ai_model",
            name="uq_ai_analysis_record_model",
        ),
        {"comment": "AI 분석 결과 저장 테이블"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="기본 키",
    )

    record_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "medical_records.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        comment="진료 기록 ID",
    )
    is_pneumonia: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="폐렴 진단 여부",
    )

    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="AI 예측 신뢰도(백분율)",
    )

    heatmap_url: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="AI가 판별한 병변 표시 이미지 URL",
    )

    heatmap_model: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Grad-CAM 생성에 사용한 대표 모델",
    )

    ai_model: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="AI 예측 모델명",
    )

    medical_record: Mapped["MedicalRecord"] = relationship(
        back_populates="ai_analysis_results",
    )
