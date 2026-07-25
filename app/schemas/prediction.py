from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ModelKey(str, Enum):
    MODEL_1 = "model_1"
    MODEL_3 = "model_3"


class AIAnalysisData(BaseModel):
    """DB에 저장된 AI 폐렴 예측 결과."""
    #DB에 저장된 결과 목록 반환
    id: int = Field(..., description="AI 분석 결과 ID")
    record_id: int = Field(..., description="진료기록 ID")
    is_pneumonia: bool = Field(..., description="폐렴 판정 여부")
    confidence: float = Field(
        ...,
        ge=0,
        le=100,
        description="최종 판정 클래스의 신뢰도(백분율)",
    )
    heatmap_url: str | None = Field(
        default=None,
        description="앙상블 Grad-CAM 이미지 조회 URL",
    )
    heatmap_model: str | None = Field(
        default=None,
        description="Heatmap 생성 모델 또는 방식",
    )
    ai_model: str = Field(..., description="폐렴 예측 모델명")
    created_at: datetime = Field(..., description="AI 분석 결과 생성 일시")

    model_config = ConfigDict(from_attributes=True)


class AIPredictionResponse(AIAnalysisData):
    """POST 예측 API 응답."""

    cached: bool = Field(
        ...,
        description="기존 저장 결과 재사용 여부",
    )
