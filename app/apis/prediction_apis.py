import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permissions
from app.core.db.databases import async_get_db
from app.models.users import DepartmentEnum, RoleEnum
from app.schemas.prediction import (
    AIAnalysisData,
    AIPredictionResponse,
    ModelKey,
)
from app.services.prediction_service import (
    MedicalRecordNotFoundError,
    PredictionFailedError,
    PredictionQueueUnavailableError,
    PredictionResultTimeoutError,
    XrayImageNotFoundError,
    enqueue_prediction_and_wait,
    get_prediction_results,
)

logger = logging.getLogger(__name__)

#####################################################
# 1. 라우터 선언
#####################################################
router = APIRouter(
    prefix="/prediction_api", 
    tags=["prediction"],
)

#####################################################
# 2. API Endpoints 구현
#####################################################

# 신규 모델 추론의 최대 처리 시간
PREDICTION_TIMEOUT_SECONDS = 60

# 예측 API 구현
@router.post(
    "/v1/medical-records/{record_id}/predict",
    response_model=AIPredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="X-ray 폐렴 예측",
)
async def predict_pneumonia(
    record_id: Annotated[
        int,
        Path(ge=1, description="예측할 진료기록 ID"),
    ],
    model_key: Annotated[
        ModelKey,
        Query(description="실행할 폐렴 예측 모델"),
    ],
    db: AsyncSession = Depends(async_get_db),
    current_user=Depends(
        require_permissions(
            allowed_roles=(RoleEnum.STAFF,),
            allowed_departments=(
                DepartmentEnum.MEDICAL,
                DepartmentEnum.DEV,
                DepartmentEnum.RESEARCH,
            ),
        )
    ),
) -> AIPredictionResponse:
    """
    진료기록에 등록된 X-ray로 폐렴 여부를 예측한다.

    동일한 진료기록과 동일한 모델의 저장 결과가 있으면
    모델을 다시 실행하지 않고 기존 결과를 반환한다.
    """

    try:
        analysis, cached = await enqueue_prediction_and_wait(
            db=db,
            record_id=record_id,
            model_key=model_key.value,
            timeout_seconds=PREDICTION_TIMEOUT_SECONDS,
        )

    except MedicalRecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 진료기록을 찾을 수 없습니다.",
        ) from exc

    except XrayImageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="예측에 사용할 X-ray 이미지가 없습니다.",
        ) from exc

    except PredictionFailedError as exc:
        logger.exception(
            "AI 폐렴 예측 모델 실행 실패: record_id=%s, model_key=%s",
            record_id,
            model_key.value,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "AI 예측 모델을 사용할 수 없습니다. "
                "잠시 후 다시 시도해주세요."
            ),
        ) from exc

    except PredictionQueueUnavailableError as exc:
        logger.exception(
            "AI 예측 Redis 작업 큐 연결 실패: record_id=%s, model_key=%s",
            record_id,
            model_key.value,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 예측 작업 큐를 사용할 수 없습니다.",
        ) from exc

    except PredictionResultTimeoutError as exc:
        logger.warning(
            "AI 폐렴 예측 제한 시간 초과: record_id=%s, model_key=%s",
            record_id,
            model_key.value,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                "AI 예측 처리 시간이 초과되었습니다. "
                "잠시 후 다시 시도해주세요."
            ),
        ) from exc

    except Exception as exc:
        logger.exception(
            "AI 폐렴 예측 결과 처리 실패: record_id=%s, model_key=%s",
            record_id,
            model_key.value,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI 예측 결과를 처리하는 중 오류가 발생했습니다.",
        ) from exc

    # ORM 객체를 공통 응답 스키마로 변환한 뒤 cached 필드를 추가한다.
    analysis_data = AIAnalysisData.model_validate(analysis)

    return AIPredictionResponse(
        **analysis_data.model_dump(),
        cached=cached,
    )

# 예측 결과 조회 API 구현
@router.get(
    "/v1/medical-records/{record_id}/analyses",
    response_model=list[AIAnalysisData],
    status_code=status.HTTP_200_OK,
    summary="저장된 폐렴 예측 결과 조회",
)
async def get_medical_record_analyses(
    record_id: Annotated[
        int,
        Path(ge=1, description="조회할 진료기록 ID"),
    ],
    db: AsyncSession = Depends(async_get_db),
    current_user=Depends(
        require_permissions(
            allowed_roles=(RoleEnum.STAFF,),
            allowed_departments=(
                DepartmentEnum.MEDICAL,
                DepartmentEnum.DEV,
                DepartmentEnum.RESEARCH,
            ),
        )
    ),
) -> list[AIAnalysisData]:
    """
    진료기록에 저장된 AI 폐렴 예측 결과를 최신순으로 반환한다.

    이 API에서는 AI 모델을 실행하지 않는다.
    저장된 결과가 없으면 빈 배열을 반환한다.
    """

    try:
        analyses = await get_prediction_results(
            db=db,
            record_id=record_id,
        )

    except MedicalRecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 진료기록을 찾을 수 없습니다.",
        ) from exc

    except Exception as exc:
        logger.exception(
            "AI 폐렴 예측 결과 조회 실패: record_id=%s",
            record_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI 예측 결과를 조회하는 중 오류가 발생했습니다.",
        ) from exc

    return [
        AIAnalysisData.model_validate(analysis)
        for analysis in analyses
    ]
