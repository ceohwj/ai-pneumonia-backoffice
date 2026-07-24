
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.databases import Base

# 타입검사 및 자동완성을 위한 import
if TYPE_CHECKING:
    from app.models.patients import Patient
    from app.models.ai_analysis_results import AIAnalysisResult
    from app.models.xray_images import XrayImages
    from app.models.email_jobs import EmailJob


class MedicalRecord(Base):
    __tablename__ = "medical_records"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True, # SQLite 환경에서는 autoincrement가 오류 없이 잘 구동된다. 
    )
    patient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    chart_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )
    symptoms: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        onupdate=func.now(),
    )

    # ORM 관계속성으로 테이블 연결 
    # 환자 정보 조회 가능하도록 patient 테이블과 연결
    patient: Mapped["Patient"] = relationship(
        back_populates="medical_records",
    )

    # x-ray 데이터 조회 가능하도록 x-ray image 테이블과 연결
    xray_images: Mapped[list["XrayImages"]] = relationship(    # x-ray 이미지는 환자 1명당 여러장 일 수 있어서 type hint에 list로 
        back_populates="medical_record",
        cascade="all, delete-orphan",
    )

    # ai 분석 결과 조회 가능하도록 ai analysis results 테이블과 연결
    ai_analysis_results: Mapped[list["AIAnalysisResult"]] = relationship(
        back_populates="medical_record",
        cascade="all, delete-orphan",
    )

    email_jobs: Mapped[list["EmailJob"]] = relationship(
        back_populates="medical_record",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
