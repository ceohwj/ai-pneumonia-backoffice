from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Enum as SQLEnum, SmallInteger, String, func
from sqlalchemy.orm import  Mapped, mapped_column, relationship
from app.core.db.databases import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.medical_records import MedicalRecord
    
class GenderEnum(str, Enum):
    M = "M"
    F = "F"


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(
        BigInteger, 
        primary_key=True, 
        autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(30), 
        nullable=False, 
        comment="환자 성명"
    )
    age: Mapped[int] = mapped_column(
        SmallInteger, 
        nullable=False, 
        comment="나이"
    )
    gender: Mapped[GenderEnum | None] = mapped_column(
        SQLEnum(GenderEnum, name="gender"),
        nullable=True,
        comment="환자 성별",
    )
    phone: Mapped[str] = mapped_column(
        String(11),
        nullable=False,
        comment="환자 연락처, 국내 전화번호로 한정",
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="AI 예측 결과 수신 이메일",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="환자 정보 등록 일시",
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        onupdate=func.now(),
        comment="환자 정보 수정 일시",
    )
    
    # MedicalRecord 테이블과 연결
    medical_records: Mapped[list["MedicalRecord"]] = relationship(
    back_populates="patient",
    cascade="all, delete-orphan",
)
