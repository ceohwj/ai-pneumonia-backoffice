from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authorization import require_permissions
from app.core.db.databases import async_get_db
from app.core.timeout import TimeoutRoute
from app.models.email_jobs import EmailJob, EmailJobStatus
from app.models.medical_records import MedicalRecord
from app.models.users import DepartmentEnum, RoleEnum, User
from app.schemas.email import EmailJobResponse
from app.tasks import send_email

router = APIRouter(
    prefix="/email_api",
    tags=["email"],
    route_class=TimeoutRoute,
)

email_permission = require_permissions(
    allowed_departments=(
        DepartmentEnum.MEDICAL,
        DepartmentEnum.DEV,
        DepartmentEnum.RESEARCH,
    ),
    allowed_roles=(RoleEnum.STAFF,),
)

admin_email_permission = require_permissions(
    allowed_departments=(DepartmentEnum.DEV,),
    allowed_roles=(RoleEnum.ADMIN,),
    admin_bypass=False,
)


@router.post(
    "/v1/medical-records/{record_id}/email-jobs",
    response_model=EmailJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="AI 예측 결과 이메일 작업 생성 API",
)
async def create_email_job(
    record_id: Annotated[int, Path(ge=1)],
    db: AsyncSession = Depends(async_get_db),
    current_user: User = Depends(email_permission),
) -> EmailJobResponse:
    result = await db.execute(
        select(MedicalRecord)
        .options(
            selectinload(MedicalRecord.patient),
            selectinload(MedicalRecord.ai_analysis_results),
        )
        .where(MedicalRecord.id == record_id)
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="진료기록을 찾을 수 없습니다.",
        )
    if not record.patient.email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="환자 이메일을 먼저 등록해 주세요.",
        )
    if not record.ai_analysis_results:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="전송할 AI 예측 결과가 없습니다.",
        )

    task_id = str(uuid4())
    email_job = EmailJob(
        task_id=task_id,
        record_id=record.id,
        requested_by=current_user.id,
        recipient_email=record.patient.email,
        subject=(
            f"[AI Health] {record.patient.name} 환자 "
            "AI 폐렴 예측 결과"
        ),
    )
    db.add(email_job)

    try:
        await db.commit()
        await db.refresh(email_job)
        send_email.apply_async(
            args=(email_job.id,),
            task_id=task_id,
            queue="email_queue",
        )
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="이메일 작업 저장 중 오류가 발생했습니다.",
        ) from exc
    except Exception as exc:
        email_job.status = EmailJobStatus.FAILURE
        email_job.error_message = "작업 큐 연결에 실패했습니다."
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="이메일 작업 큐에 연결할 수 없습니다.",
        ) from exc

    return EmailJobResponse.model_validate(email_job)


@router.get(
    "/v1/admin/email-jobs",
    response_model=list[EmailJobResponse],
    summary="관리자 이메일 전송 로그 목록 조회 API",
)
async def get_admin_email_jobs(
    query: str | None = Query(
        default=None,
        max_length=255,
        description="수신 이메일 또는 제목 검색",
    ),
    job_status: EmailJobStatus | None = Query(
        default=None,
        alias="status",
        description="이메일 작업 상태 필터",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(async_get_db),
    _current_user: User = Depends(admin_email_permission),
) -> list[EmailJobResponse]:
    statement = select(EmailJob)

    if query:
        keyword = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                EmailJob.recipient_email.ilike(keyword),
                EmailJob.subject.ilike(keyword),
            )
        )

    if job_status:
        statement = statement.where(
            EmailJob.status == job_status
        )

    statement = (
        statement
        .order_by(EmailJob.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(statement)
    return list(result.scalars().all())


@router.get(
    "/v1/email-jobs/{email_job_id}",
    response_model=EmailJobResponse,
    summary="이메일 작업 상태 조회 API",
)
async def get_email_job(
    email_job_id: Annotated[int, Path(ge=1)],
    db: AsyncSession = Depends(async_get_db),
    _current_user: User = Depends(email_permission),
) -> EmailJobResponse:
    email_job = await db.get(EmailJob, email_job_id)
    if email_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="이메일 작업을 찾을 수 없습니다.",
        )

    return EmailJobResponse.model_validate(email_job)
