from datetime import datetime  # DB의 DATETIME 컬럼 타입

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String  # Python에서 사용하는 날짜 객체
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.databases import Base

from app.core.db.models import TimestampMixin

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.medical_records import MedicalRecord


class XrayImages(Base, TimestampMixin):
    __tablename__ = "xray_images"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement= True
    )
    record_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "medical_records.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True
    )
    # 회원 탈퇴 시 DB에서 회원 정보 삭제를 위해 수정 (x-ray 정보는 유지)
    uploader_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete='SET NULL',
        ),
        nullable=True,
        index=True
    )
    image_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    shooting_datetime: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )
    
    # MedicalRecord 테이블과 연결
     
    medical_record: Mapped["MedicalRecord"] = relationship(
    back_populates="xray_images",
)
